#!/usr/bin/env python3
"""Store the CRM <-> master keys on both sides, and log what was keyed.

Phase 2 of the architecture blueprint: a link between a CRM contact and its
master row is a stored key, never a match computed when something reads it.

  CRM side     each contact the master holds gets `master_id`. The Apollo id
               (the CRM document id) decides it. A contact that only an email
               connects is keyed here and nowhere else -- once, by name, in
               data/CHANGELOG.md -- so a changed email can never silently
               re-point a contact at someone else.
  Master side  each matched row gets `crm_id`, the CRM document id.

Anything that does not key cleanly is listed and left alone: a stored
master_id naming no row, a stored master_id that disagrees with the Apollo
id, or a master row that two CRM contacts would claim.

Dry run by default. `--write` emits data/artifact/crm/keys_*.json batch files
(a Claude session applies them with ArtifactData batch, pinned), rewrites
master with the crm_id values and appends one CHANGELOG entry. Safe to
re-run: a keyed pair plans nothing.

The session that applies the CRM side writes the run's one line to the CRM
runlog (python3 -m crm.runlog entry), as the Monday push does. When the
enrichment push runs in the same session, its batches carry the same
master_id values: apply one set or the other, since both pin the same
document versions.

    python scripts/backfill_keys.py --crm-dump <dump>            # dry run
    python scripts/backfill_keys.py --crm-dump <dump> --write
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config
from crm.crm_sync import join_master, load_crm_dump, pinned, write_batches
from crm.master import load_master, save_master
from crm.schema import Contact, utcnow


@dataclass
class KeyPlan:
    crm_writes: list[dict[str, Any]] = field(default_factory=list)
    #: master contact_id -> crm doc id to store as crm_id
    master_keys: dict[str, str] = field(default_factory=dict)
    by_apollo: int = 0
    by_email: list[str] = field(default_factory=list)
    already: int = 0
    skipped: list[str] = field(default_factory=list)


def _who(rec: Contact, doc: dict[str, Any]) -> str:
    name = doc.get("name") or " ".join(p for p in (rec.first_name, rec.last_name) if p) or rec.contact_id
    company = doc.get("company") or rec.company_name
    return f"{name} ({company})" if company else name


def plan(master: list[Contact], docs: dict[str, dict[str, Any]]) -> KeyPlan:
    """Pure: what to store on each side. No I/O."""
    j = join_master(master, docs)
    out = KeyPlan()
    pairs: dict[str, list[str]] = {}
    for doc_id, rec in j.joined.items():
        pairs.setdefault(rec.contact_id, []).append(doc_id)
    for doc_id, rec in j.email_only.items():
        pairs.setdefault(rec.contact_id, []).append(doc_id)
    by_id = {c.contact_id: c for c in master}

    for master_id, doc_ids in sorted(pairs.items()):
        rec = by_id[master_id]
        if len(doc_ids) > 1:
            out.skipped.append(f"{rec.contact_id}: claimed by {len(doc_ids)} CRM contacts {sorted(doc_ids)}")
            continue
        doc_id = doc_ids[0]
        doc = docs[doc_id]
        if doc.get("master_id") == master_id:
            out.already += 1
        else:
            out.crm_writes.append(pinned(doc, {"op": "update", "collection": "contacts", "doc_id": doc_id,
                                               "data": {"master_id": master_id}}))
            if doc_id in j.email_only:
                out.by_email.append(f"{_who(rec, doc)} -> {master_id}")
            else:
                out.by_apollo += 1
        if rec.crm_id != doc_id:
            out.master_keys[master_id] = doc_id

    for doc_id, stored in sorted(j.dangling.items()):
        out.skipped.append(f"{doc_id}: stored master_id {stored} names no master row")
    for doc_id, (stored, via) in sorted(j.disagree.items()):
        out.skipped.append(f"{doc_id}: stored master_id {stored} but its Apollo id is master row {via}")
    return out


def changelog_entry(p: KeyPlan, now: str) -> str:
    lines = [f"\n## {now}\n",
             f"- **key backfill** (scripts/backfill_keys.py): {len(p.crm_writes)} CRM contact(s) given master_id "
             f"({p.by_apollo} by Apollo id, {len(p.by_email)} by email), {len(p.master_keys)} master row(s) given "
             f"crm_id, {p.already} already keyed, {len(p.skipped)} left unkeyed."]
    lines += [f"  - keyed by email, once: {w}" for w in p.by_email]
    lines += [f"  - left unkeyed: {s}" for s in p.skipped]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crm-dump", type=Path, required=True, help="ArtifactData out_dir of the CRM contacts")
    parser.add_argument("--master", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=config.CRM_BATCH_DIR)
    parser.add_argument("--write", action="store_true", help="emit batch files, write master and the changelog")
    args = parser.parse_args()

    master = load_master(args.master)
    docs = load_crm_dump(args.crm_dump)
    p = plan(master, docs)
    print(f"master {len(master)} · crm {len(docs)}")
    print(f"CRM master_id to write: {len(p.crm_writes)} ({p.by_apollo} by Apollo id, {len(p.by_email)} by email)"
          f" · already keyed {p.already}")
    print(f"master crm_id to write: {len(p.master_keys)}")
    for line in p.by_email:
        print(f"  by email, once: {line}")
    for line in p.skipped:
        print(f"  UNKEYED {line}")

    if not p.crm_writes and not p.master_keys:
        print("nothing to write")
        return 0
    if not args.write:
        print("dry run -- re-run with --write to emit batch files and write master")
        return 0

    if p.crm_writes:
        files = write_batches(p.crm_writes, args.out_dir, "keys")
        print(f"{len(p.crm_writes)} CRM update(s) -> {len(files)} batch file(s) in {args.out_dir}")
    if p.master_keys:
        for rec in master:
            if rec.contact_id in p.master_keys:
                rec.crm_id = p.master_keys[rec.contact_id]
        save_master(master, args.master)
        print(f"master: crm_id stored on {len(p.master_keys)} row(s)")
    changelog = config.CHANGELOG
    if not changelog.exists():
        changelog.write_text("# CRM master database changelog\n")
    with changelog.open("a") as fh:
        fh.write(changelog_entry(p, utcnow()))
    print(f"changelog: {changelog}")
    print("next: apply the batches pinned, then write the run line, e.g.\n"
          f"  python3 -m crm.runlog entry --run \"Key backfill\" --updated {len(p.crm_writes)} "
          f"--detail \"{len(p.crm_writes)} contacts keyed to master, {len(p.master_keys)} master rows keyed to the CRM\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
