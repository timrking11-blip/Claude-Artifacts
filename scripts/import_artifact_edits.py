#!/usr/bin/env python3
"""Bring edits made in the CRM artifact back into the repo mirror.

Reads a dump of the artifact's `contacts` collection -- the directory layout
ArtifactData writes with `out_dir`, i.e. <dump>/contacts/<doc_id>.json -- and
merges every field a human edited in the artifact into master as a `manual`
observation. Manual has the highest trust for every field, so these edits
survive the next weekly sync no matter what Apollo or Explorium report.

Only fields whose provenance says `manual` are imported; the rest of each
document is already in master (the artifact was seeded from it) and
re-importing it would just fabricate a second attestation.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config
from crm.master import load_master, save_master, merge_all
from crm.schema import Contact, SOURCE_MANUAL, MERGED_FIELDS

log = logging.getLogger("import_artifact_edits")


def manual_slice(doc: dict) -> tuple[Contact | None, str | None]:
    """Return a sparse Contact of just the manually edited fields, plus the
    latest edit time -- or (None, None) if nothing in the doc was edited."""
    prov = doc.get("provenance") or {}
    edited = {f for f, p in prov.items() if isinstance(p, dict) and p.get("source") == SOURCE_MANUAL}
    if not edited:
        return None, None

    sparse = Contact(contact_id=doc.get("contact_id") or "")
    # Identity keys ride along so the merge can find the record, but they are
    # only *claimed* (and so re-attested) when they were themselves edited.
    for key in ("email", "linkedin_url", "first_name", "last_name", "company_domain"):
        setattr(sparse, key, doc.get(key))
    for f in edited:
        if f in MERGED_FIELDS:
            setattr(sparse, f, doc.get(f))

    latest = max((prov[f].get("observed_at") or "") for f in edited) or None
    return sparse, latest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump_dir", type=Path, help="directory ArtifactData dumped into")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    docs_dir = args.dump_dir / "contacts"
    if not docs_dir.is_dir():
        raise SystemExit(f"{docs_dir} not found -- expected <dump>/contacts/<doc_id>.json")

    master = load_master()
    by_id = {c.contact_id: c for c in master}
    imported = 0

    for path in sorted(docs_dir.glob("*.json")):
        doc = json.loads(path.read_text())
        sparse, observed_at = manual_slice(doc)
        if sparse is None:
            continue
        # Prefer matching by id: the artifact was seeded from master, so the
        # ids line up. Identity keys are the fallback for a record created
        # in the artifact by hand.
        if sparse.contact_id in by_id:
            target = by_id[sparse.contact_id]
            for key in ("email", "linkedin_url", "first_name", "last_name", "company_domain"):
                if not getattr(sparse, key):
                    setattr(sparse, key, getattr(target, key))
        master, report = merge_all(master, [sparse], SOURCE_MANUAL, observed_at)
        by_id = {c.contact_id: c for c in master}
        if report.changed:
            imported += 1
            log.info("%s: %s", sparse.contact_id or path.stem, report.summary())

    log.info("%s record(s) carried manual edits", imported)
    if args.dry_run:
        log.info("dry run: master not written")
        return 0
    save_master(master)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
