#!/usr/bin/env python3
"""Fold both staged sources into the master database and record what changed.

This is the only script that writes data/master/contacts.json. It runs after
both pulls have finished, is safe to re-run, and reports a non-zero exit only
on real failure -- "nothing changed" is a successful week.

Every run also writes one line to data/runlog/ (crm/runlog.py), which the
Monday routine posts to the CRM page's "Last runs" strip. A run that would
create more than crm.runlog.HOLD_OVER contacts does not write master: it
holds, names the contacts, and applies only when re-run with
--allow-created set to that exact count (the workflow's allow_created input).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config, runlog
from crm.master import dedupe_by_vendor_id, load_master, save_master, merge_all, MergeReport
from crm.schema import Contact, SOURCE_APOLLO, SOURCE_EXPLORIUM, SOURCE_LINKEDIN, utcnow

log = logging.getLogger("merge_master")


def load_staging(path: Path) -> tuple[list[Contact], str | None]:
    if not path.exists():
        log.warning("%s does not exist -- skipping that source", path)
        return [], None
    raw = json.loads(path.read_text() or "{}")
    contacts = [Contact.from_dict(r) for r in raw.get("contacts", [])]
    return contacts, raw.get("observed_at")


def write_changelog(reports: list[tuple[str, MergeReport]], total: int, held_note: str | None = None) -> None:
    lines = [f"\n## {utcnow()}\n", f"Master now holds **{total}** contacts.\n"]
    if held_note:
        lines = [f"\n## {utcnow()} -- HELD\n", held_note + "\n"]
    for source, report in reports:
        lines.append(f"- **{source}**: {report.summary()}")
        for change in report.field_changes[:20]:
            lines.append(
                f"  - `{change['contact_id']}` `{change['field']}`: "
                f"{change['from']!r} -> {change['to']!r} ({change['reason']})"
            )
        if len(report.field_changes) > 20:
            lines.append(f"  - ...and {len(report.field_changes) - 20} more")
        for conflict in report.conflicts_held[:10]:
            lines.append(
                f"  - CONFLICT HELD `{conflict['contact_id']}` `{conflict['field']}`: "
                f"kept {conflict['kept']!r}, rejected {conflict['rejected']!r}"
            )
        for amb in report.ambiguous_matches[:10]:
            lines.append(
                f"  - AMBIGUOUS MATCH {amb['keys']} -> {amb['candidates']} "
                "(records left unfused; resolve by hand in the CRM artifact)"
            )
    lines.append("")

    config.CHANGELOG.parent.mkdir(parents=True, exist_ok=True)
    if not config.CHANGELOG.exists():
        config.CHANGELOG.write_text("# CRM master database changelog\n")
    with config.CHANGELOG.open("a") as fh:
        fh.write("\n".join(lines))


def created_names(reports: list[tuple[str, MergeReport]], master: list[Contact]) -> list[str]:
    by_id = {c.contact_id: c for c in master}
    names = []
    for _, report in reports:
        for cid in report.created:
            c = by_id.get(cid)
            if not c:
                continue
            who = " ".join(p for p in (c.first_name, c.last_name) if p) or c.email or cid
            at = c.company_name or c.company_domain
            names.append(f"{who} ({at})" if at else who)
    return names


def run_detail(reports: list[tuple[str, MergeReport]]) -> str:
    return "; ".join(f"{s} {len(r.created)} created, {len(r.updated)} updated, {len(r.unchanged)} unchanged"
                     for s, r in reports)


def _allow_created_default() -> int | None:
    raw = (os.environ.get("ALLOW_CREATED") or "").strip()
    return int(raw) if raw.isdigit() else None


def step_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as fh:
            fh.write(text + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing master or the changelog",
    )
    parser.add_argument(
        "--fail-on-conflict",
        action="store_true",
        help="exit non-zero if any field conflict was held, for stricter CI",
    )
    parser.add_argument(
        "--allow-created",
        type=int,
        default=_allow_created_default(),
        help=f"apply a run that creates more than {runlog.HOLD_OVER} contacts, only if it creates exactly this many",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    master = load_master()
    log.info("loaded %s existing master contacts", len(master))

    reports: list[tuple[str, MergeReport]] = []
    # Apollo first: it is the system of record for who is in the CRM at all.
    # Explorium second: it enriches whatever Apollo established.
    # LinkedIn last and OPTIONAL: there is no automated LinkedIn pull (scraping
    # it breaches their terms), so this file only exists when someone has
    # staged an export by hand. Absent is the normal case, so it is skipped
    # without the "does not exist" warning the required sources earn.
    for source, path, optional in (
        (SOURCE_APOLLO, config.APOLLO_STAGING, False),
        (SOURCE_EXPLORIUM, config.EXPLORIUM_STAGING, False),
        (SOURCE_LINKEDIN, config.LINKEDIN_STAGING, True),
    ):
        if optional and not path.exists():
            continue
        incoming, observed_at = load_staging(path)
        if not incoming:
            continue
        master, report = merge_all(master, incoming, source, observed_at)
        log.info("%s: %s", source, report.summary())
        reports.append((source, report))

    # Self-heal: anything that shares a vendor id is one person. Runs every
    # week so a duplicate can never survive more than one cycle.
    master, folded = dedupe_by_vendor_id(master)
    if folded:
        log.warning("folded %s duplicate record(s) by vendor id: %s", len(folded), folded[:5])

    if not reports:
        log.error(
            "no staged data from any required source -- both pulls must have failed. "
            "Refusing to rewrite master from nothing."
        )
        return 1

    if args.dry_run:
        print(json.dumps({s: r.to_dict() for s, r in reports}, indent=2))
        log.info("dry run: master not written")
        return 0

    created = sum(len(r.created) for _, r in reports)
    updated = sum(len(r.updated) for _, r in reports)
    names = created_names(reports, master)
    now = datetime.now(timezone.utc)
    if runlog.held(created, args.allow_created):
        doc = runlog.entry(
            "Weekly sync", run_detail(reports), created, updated, now, created_names=names,
            check="open each name in Apollo and in the CRM and confirm none is already a contact under another "
                  "email or id (on 21 Sep 2026 all 15 were).",
            on_confirm=f"GitHub → Actions → Weekly CRM sync → Run workflow with allow_created = {created}. "
                       "A different count holds again.")
        runlog.write_file(doc)
        write_changelog(reports, len(master), held_note=doc["line"] + ". Master was not written.")
        log.warning("HELD: %s", doc["line"])
        print(f"::warning title=Weekly sync held::{doc['line']}")
        step_summary(f"### Weekly sync held\n\n{doc['line']}\n\n" + "\n".join(f"- {n}" for n in names[:50])
                     + f"\n\n{doc['on_confirm']}")
        return 0

    save_master(master)
    write_changelog(reports, len(master))
    log.info("wrote %s contacts to %s", len(master), config.MASTER_CONTACTS)
    doc = runlog.entry("Weekly sync", run_detail(reports), created, updated, now, created_names=names,
                       allow_created=args.allow_created)
    runlog.write_file(doc)
    step_summary(f"### Weekly sync\n\n{doc['line']}")

    if args.fail_on_conflict and any(r.conflicts_held for _, r in reports):
        log.error("conflicts were held; failing as requested")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
