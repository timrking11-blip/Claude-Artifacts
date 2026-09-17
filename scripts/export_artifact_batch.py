#!/usr/bin/env python3
"""Turn the repo's master file into write batches for the CRM artifact database.

The artifact's database is the master; this repo's data/master/contacts.json
is its committed mirror. After a weekly merge, this script prepares the
writes that push the mirror back into the artifact -- one JSON file per
batch of at most 50 documents, which is the platform's batch ceiling.

A Claude session applies them with the ArtifactData tool:
    ArtifactData(action="batch", url=<artifact>, writes=<contents of one file>)
The files are derived output and are not committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config
from crm.master import load_master
from crm.schema import utcnow

BATCH_LIMIT = 50
CONTACTS_COLLECTION = "contacts"
META_COLLECTION = "meta"
META_DOC = "sync"


def load_last_report() -> dict:
    """Pull the review-queue items out of the most recent changelog entry.

    The changelog is the only place merge results persist between runs, so
    it is parsed rather than re-merged. Only the last section is read.
    """
    if not config.CHANGELOG.exists():
        return {"conflicts_held": [], "ambiguous_matches": []}
    text = config.CHANGELOG.read_text()
    last = text.split("\n## ")[-1]
    conflicts, ambiguous = [], []
    for line in last.splitlines():
        line = line.strip()
        if line.startswith("- CONFLICT HELD"):
            # - CONFLICT HELD `id` `field`: kept 'x', rejected 'y'
            try:
                head, tail = line.split(":", 1)
                parts = head.split("`")
                contact_id, field = parts[1], parts[3]
                kept, rejected = tail.split(", rejected ")
                conflicts.append(
                    {
                        "contact_id": contact_id,
                        "field": field,
                        "kept": kept.replace("kept ", "").strip().strip("'\""),
                        "rejected": rejected.strip().strip("'\""),
                        "source": "sync",
                    }
                )
            except (ValueError, IndexError):
                continue
        elif line.startswith("- AMBIGUOUS MATCH"):
            try:
                cands = line.split("->", 1)[1].split("(")[0]
                candidates = [c.strip(" []'\"") for c in cands.split(",") if c.strip()]
                ambiguous.append({"candidates": candidates})
            except IndexError:
                continue
    return {"conflicts_held": conflicts, "ambiguous_matches": ambiguous}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=config.DATA_DIR / "artifact")
    args = parser.parse_args()

    contacts = load_master()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for stale in args.out_dir.glob("*.json"):
        stale.unlink()

    docs = [c.to_dict() for c in sorted(contacts, key=lambda c: c.contact_id)]
    files = []
    for i in range(0, len(docs), BATCH_LIMIT):
        chunk = docs[i : i + BATCH_LIMIT]
        writes = [
            {"op": "set", "collection": CONTACTS_COLLECTION, "doc_id": d["contact_id"], "data": d}
            for d in chunk
        ]
        path = args.out_dir / f"batch_{i // BATCH_LIMIT:03d}.json"
        path.write_text(json.dumps(writes, indent=2, ensure_ascii=False) + "\n")
        files.append(path)

    report = load_last_report()
    sources = {}
    for c in contacts:
        for s in c.sources:
            sources[s] = sources.get(s, 0) + 1
    meta = {
        "generated_at": utcnow(),
        "count": len(contacts),
        "sources": sources,
        "conflicts_held": report["conflicts_held"],
        "ambiguous_matches": report["ambiguous_matches"],
    }
    meta_path = args.out_dir / "meta_sync.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")

    print(f"{len(docs)} contacts -> {len(files)} batch file(s) in {args.out_dir}")
    print(f"meta doc ({META_COLLECTION}/{META_DOC}) -> {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
