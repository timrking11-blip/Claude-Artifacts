#!/usr/bin/env python3
"""Prove the enriched data layer and the CRM are intact and in sync.

Runs before anything is pushed anywhere, and in CI after every merge. It has
no credentials and touches no network: master is a file in this repo, and
the CRM is checked from a dump made with ArtifactData.

    python scripts/validate_sync.py                       # master only (CI)
    python scripts/validate_sync.py --crm-dump dump/      # master + CRM + join

Exit 1 on any hard failure. Warnings are printed but do not fail the run.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config
from crm.crm_sync import PROPOSAL_STATUSES, join_master, load_crm_dump
from crm.master import load_master
from crm.schema import KNOWN_SOURCES, normalize_email

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.facts: list[str] = []

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def fact(self, msg: str) -> None:
        self.facts.append(msg)

    @property
    def ok(self) -> bool:
        return not self.failures


def check_master(report: Report, master_path: Path | None = None) -> list:
    contacts = load_master(master_path)
    report.fact(f"master: {len(contacts)} records")
    if not contacts:
        report.fail("master is empty or missing")
        return contacts

    missing_ids = [i for i, c in enumerate(contacts) if not c.contact_id]
    if missing_ids:
        report.fail(f"{len(missing_ids)} master record(s) have no contact_id")

    dup_ids = [k for k, n in Counter(c.contact_id for c in contacts if c.contact_id).items() if n > 1]
    if dup_ids:
        report.fail(f"duplicate contact_id in master: {dup_ids[:5]}")

    dup_apollo = [k for k, n in Counter(c.apollo_contact_id for c in contacts if c.apollo_contact_id).items() if n > 1]
    if dup_apollo:
        report.fail(f"duplicate apollo_contact_id in master: {dup_apollo[:5]}")

    dup_email = [k for k, n in Counter(normalize_email(c.email) for c in contacts if normalize_email(c.email)).items() if n > 1]
    if dup_email:
        report.fail(f"duplicate email in master: {dup_email[:5]}")

    # One CRM document is one person: two master rows keyed to the same CRM
    # contact would make the stored key a guess again.
    dup_crm = [k for k, n in Counter(c.crm_id for c in contacts if c.crm_id).items() if n > 1]
    if dup_crm:
        report.fail(f"duplicate crm_id in master: {dup_crm[:5]}")
    report.fact(f"master: {sum(1 for c in contacts if c.crm_id)} record(s) keyed to a CRM contact (crm_id)")

    # An unknown source is the trust-0 trap: it loses every conflict and is
    # overwritten by anything. Catch it here as well as in the test suite,
    # because a hand-staged file can introduce one that no test sees.
    bad_sources: Counter = Counter()
    for c in contacts:
        for s in c.sources or []:
            if s not in KNOWN_SOURCES:
                bad_sources[s] += 1
        for f, p in (c.provenance or {}).items():
            src = p.get("source") if isinstance(p, dict) else None
            if src not in KNOWN_SOURCES:
                bad_sources[str(src)] += 1
    if bad_sources:
        report.fail(f"provenance names unknown source(s): {dict(bad_sources)} (known: {list(KNOWN_SOURCES)})")

    src_counts: Counter = Counter()
    for c in contacts:
        for p in (c.provenance or {}).values():
            if isinstance(p, dict) and p.get("source"):
                src_counts[p["source"]] += 1
    report.fact(f"master: attributed field values by source: {dict(src_counts) or '{}'}")
    return contacts


def check_crm(report: Report, docs: dict) -> None:
    report.fact(f"crm: {len(docs)} documents")
    if not docs:
        report.fail("CRM dump is empty")
        return
    required = ("stage", "flags", "activity", "notes")
    for doc_id, doc in docs.items():
        for key in required:
            if key not in doc:
                report.fail(f"crm {doc_id}: missing required field {key!r}")
        status = doc.get("proposal_status")
        if status not in (None, "") and status not in PROPOSAL_STATUSES:
            report.fail(f"crm {doc_id}: proposal_status {status!r} not in {PROPOSAL_STATUSES}")
        amount = doc.get("proposal_amount")
        if amount not in (None, "") and not isinstance(amount, (int, float)):
            report.fail(f"crm {doc_id}: proposal_amount {amount!r} is not numeric")
        for key in ("proposal_sent", "proposal_expires", "proposal_replied"):
            v = doc.get(key)
            if v and not ISO_DATE.match(str(v)):
                report.fail(f"crm {doc_id}: {key} {v!r} is not YYYY-MM-DD")
    stages = Counter(d.get("stage") for d in docs.values())
    flags = Counter(f for d in docs.values() for f in (d.get("flags") or []))
    proposals = Counter(d.get("proposal_status") or "none" for d in docs.values())
    report.fact(f"crm: stages {dict(stages)}")
    report.fact(f"crm: flags {dict(flags) or '{}'}")
    report.fact(f"crm: proposal_status {dict(proposals)}")


def check_join(report: Report, contacts: list, docs: dict, min_coverage: float) -> None:
    """The CRM <-> master link, by stored key only (crm.crm_sync.join_master).

    A broken key fails: a stored master_id that names no master row, or one
    that disagrees with the contact's Apollo id. A missing key is only a fact
    -- a contact the Monday sync added this morning has none until the push
    writes it. An email-only match is never a join; it is a warning that
    scripts/backfill_keys.py should key it, once and logged.
    """
    j = join_master(contacts, docs)
    by_master = sum(1 for h in j.how.values() if h == "master_id")
    by_apollo = sum(1 for h in j.how.values() if h == "apollo_id")
    unkeyed_docs = [d for d in docs if d not in j.joined and d not in j.email_only
                    and d not in j.dangling and d not in j.disagree]
    coverage = len(j.joined) / len(docs) if docs else 0.0

    report.fact(f"join: {by_master} by stored master_id, {by_apollo} by Apollo id (master_id not stored yet), "
                f"{len(j.email_only)} by email only (unkeyed), {len(unkeyed_docs)} CRM doc(s) not in master "
                f"-> coverage {coverage:.0%}")
    for doc_id, stored in sorted(j.dangling.items()):
        report.fail(f"crm {doc_id}: stored master_id {stored} names no master row")
    for doc_id, (stored, via) in sorted(j.disagree.items()):
        report.fail(f"crm {doc_id}: stored master_id {stored} disagrees with its Apollo id (master row {via})")
    if j.email_only:
        report.warn(f"{len(j.email_only)} CRM contact(s) match master by email only, never joined: "
                    f"{sorted(j.email_only)[:5]} -- key them with scripts/backfill_keys.py")
    if unkeyed_docs:
        report.warn(f"CRM docs absent from master (first 5): {unkeyed_docs[:5]}")

    in_crm = {rec.contact_id for rec in j.joined.values()}
    only_master = [c.contact_id for c in contacts if c.contact_id not in in_crm
                   and c.contact_id not in {r.contact_id for r in j.email_only.values()}]
    report.fact(f"join: {len(only_master)} master record(s) not in the CRM (expected -- the CRM ingests a subset)")
    stale = sorted(c.contact_id for c in contacts if c.crm_id and c.crm_id not in docs)
    if stale:
        report.warn(f"{len(stale)} master row(s) carry a crm_id naming no CRM contact (re-keyed or removed): {stale[:5]}")
    missing = sum(1 for rec in j.joined.values() if not rec.crm_id)
    if missing:
        report.fact(f"join: {missing} master row(s) in the CRM without crm_id yet (scripts/backfill_keys.py writes it)")
    if coverage < min_coverage:
        report.fail(f"join coverage {coverage:.0%} is below --min-coverage {min_coverage:.0%}")


def run(master_path: Path | None, crm_dump: Path | None, min_coverage: float) -> Report:
    report = Report()
    contacts = check_master(report, master_path)
    if crm_dump is not None:
        docs = load_crm_dump(crm_dump)
        check_crm(report, docs)
        if contacts and docs:
            check_join(report, contacts, docs, min_coverage)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--master", type=Path, default=None, help=f"default {config.MASTER_CONTACTS}")
    parser.add_argument("--crm-dump", type=Path, default=None, help="ArtifactData out_dir of the CRM contacts")
    parser.add_argument("--min-coverage", type=float, default=0.9)
    args = parser.parse_args()

    report = run(args.master, args.crm_dump, args.min_coverage)
    for line in report.facts:
        print(f"  {line}")
    for line in report.warnings:
        print(f"WARN  {line}")
    for line in report.failures:
        print(f"FAIL  {line}")
    print("OK: data layer and CRM are intact" + (" and in sync" if args.crm_dump else "")
          if report.ok else f"FAILED: {len(report.failures)} problem(s)")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
