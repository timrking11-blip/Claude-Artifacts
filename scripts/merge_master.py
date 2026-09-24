#!/usr/bin/env python3
"""Fold both staged sources into the master database and record what changed.

This is the only script that writes data/master/contacts.json. It runs after
both pulls have finished, is safe to re-run, and reports a non-zero exit only
on real failure -- "nothing changed" is a successful week.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config
from crm.master import load_master, save_master, merge_all, MergeReport
from crm.schema import Contact, SOURCE_APOLLO, SOURCE_EXPLORIUM, SOURCE_LINKEDIN, utcnow

log = logging.getLogger("merge_master")


def load_staging(path: Path) -> tuple[list[Contact], str | None]:
    if not path.exists():
        log.warning("%s does not exist -- skipping that source", path)
        return [], None
    raw = json.loads(path.read_text() or "{}")
    contacts = [Contact.from_dict(r) for r in raw.get("contacts", [])]
    return contacts, raw.get("observed_at")


def write_changelog(reports: list[tuple[str, MergeReport]], total: int) -> None:
    lines = [f"\n## {utcnow()}\n", f"Master now holds **{total}** contacts.\n"]
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

    save_master(master)
    write_changelog(reports, len(master))
    log.info("wrote %s contacts to %s", len(master), config.MASTER_CONTACTS)

    if args.fail_on_conflict and any(r.conflicts_held for _, r in reports):
        log.error("conflicts were held; failing as requested")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
