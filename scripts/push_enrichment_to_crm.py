#!/usr/bin/env python3
"""Carry enrichment from the data layer into the CRM, and flag proposal-ready contacts.

Reads master (this repo) and a dump of the CRM System's contacts, joins them
by Apollo contact id (email as fallback), and plans one `update` per contact
that would actually change. Two kinds of change, and only two:

  1. Enrichment fields the CRM does not own and does not yet have --
     seniority, industry, employees, technologies, linkedin, city/state.
     A CRM value that already exists is never overwritten.
  2. The `proposal_ready` flag, from crm.crm_sync.proposal_ready().

It never emits stage, notes, next step, deal value, product, proposal_*, or
any Apollo-owned field. crm_sync.assert_not_owned() enforces that at plan
time and the test suite checks it.

Dry-run by default. `--write` emits data/artifact/crm/enrich_*.json, which a
Claude session applies with ArtifactData(action="batch", writes=<file>).
Today the enrichment half carries nothing -- Explorium has no credits and no
LinkedIn file is staged -- so a run only computes flags. That is by design:
the pipe exists so the first week that has data needs no new code.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config
from crm.crm_sync import (
    PROPOSAL_READY_FLAG,
    assert_not_owned,
    index_crm_by_email,
    load_crm_dump,
    pinned,
    proposal_ready,
    system_activity,
    utcnow_iso,
    with_flag,
    write_batches,
)
from crm.master import load_master
from crm.schema import Contact, normalize_email

#: master field -> CRM field. Only filled when the CRM field is empty.
ENRICH_FIELDS = (
    ("seniority", "seniority"),
    ("industry", "industry"),
    ("employee_count", "employees"),
    ("technologies", "technologies"),
    ("linkedin_url", "linkedin"),
)


def _empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == 0


def _join(master: list[Contact], docs: dict[str, dict]) -> dict[str, Contact]:
    """doc_id -> master Contact, by apollo id first, then normalised email."""
    by_apollo = {c.apollo_contact_id: c for c in master if c.apollo_contact_id}
    by_email = {normalize_email(c.email): c for c in master if normalize_email(c.email)}
    crm_emails = index_crm_by_email(docs)
    out: dict[str, Contact] = {}
    for doc_id, doc in docs.items():
        if doc_id in by_apollo:
            out[doc_id] = by_apollo[doc_id]
            continue
        email = normalize_email(doc.get("email"))
        if email and email in by_email and crm_emails.get(email) == doc_id:
            out[doc_id] = by_email[email]
    return out


def plan_enrichment(rec: Contact, doc: dict) -> tuple[dict[str, Any], list[str]]:
    """Fields to write and the sources they came from. Empty if nothing new."""
    data: dict[str, Any] = {}
    sources: set[str] = set()
    for m_field, c_field in ENRICH_FIELDS:
        value = getattr(rec, m_field, None)
        if _empty(value) or not _empty(doc.get(c_field)):
            continue
        # The CRM stores employees as a string ("11"); keep that shape.
        data[c_field] = str(value) if c_field == "employees" else value
        src = (rec.provenance or {}).get(m_field, {}).get("source")
        if src:
            sources.add(src)
    # location -> city/state only when the CRM has neither. "City, ST" only;
    # anything else is not confidently splittable and is left alone.
    if _empty(doc.get("city")) and _empty(doc.get("state")) and rec.location and ", " in rec.location:
        city, _, state = rec.location.rpartition(", ")
        if city and 1 < len(state) <= 3:
            data["city"], data["state"] = city.strip(), state.strip().upper()
            src = (rec.provenance or {}).get("location", {}).get("source")
            if src:
                sources.add(src)
    return data, sorted(sources)


def plan(master: list[Contact], docs: dict[str, dict], now: str | None = None) -> list[dict[str, Any]]:
    """Every ArtifactData `update` this run would make. Pure; no I/O."""
    now = now or utcnow_iso()
    joined = _join(master, docs)
    writes: list[dict[str, Any]] = []
    for doc_id, doc in docs.items():
        data: dict[str, Any] = {}
        notes: list[str] = []

        rec = joined.get(doc_id)
        if rec is not None:
            enrich, sources = plan_enrichment(rec, doc)
            if enrich:
                data.update(enrich)
                notes.append(f"Enriched {', '.join(sorted(enrich))} from {', '.join(sources) or 'the data layer'}")

        ready = proposal_ready(doc)
        has_flag = PROPOSAL_READY_FLAG in (doc.get("flags") or [])
        if ready != has_flag:
            data["flags"] = with_flag(doc.get("flags"), PROPOSAL_READY_FLAG, ready)
            notes.append("Marked proposal-ready: qualified, reachable, and touched"
                         if ready else "No longer proposal-ready")

        if not data:
            continue
        assert_not_owned({k: v for k, v in data.items() if k != "flags"})
        data["activity"] = system_activity(doc.get("activity"), "; ".join(notes), ts=now)
        data["updated_at"] = now
        writes.append(pinned(doc, {"op": "update", "collection": "contacts", "doc_id": doc_id, "data": data}))
    return writes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crm-dump", type=Path, required=True, help="ArtifactData out_dir of the CRM contacts")
    parser.add_argument("--master", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=config.CRM_BATCH_DIR)
    parser.add_argument("--write", action="store_true", help="emit batch files (default: dry run)")
    args = parser.parse_args()

    master = load_master(args.master)
    docs = load_crm_dump(args.crm_dump)
    writes = plan(master, docs)

    enriched = sum(1 for w in writes if any(k not in ("flags", "activity", "updated_at") for k in w["data"]))
    flagged = sum(1 for w in writes if PROPOSAL_READY_FLAG in (w["data"].get("flags") or []))
    unflagged = sum(1 for w in writes if "flags" in w["data"] and PROPOSAL_READY_FLAG not in w["data"]["flags"])
    ready_total = sum(1 for d in docs.values() if proposal_ready(d))
    print(f"master {len(master)} · crm {len(docs)} · joined {len(_join(master, docs))}")
    print(f"proposal-ready now: {ready_total}  (newly flagged {flagged}, unflagged {unflagged})")
    print(f"enrichment writes: {enriched}")
    for w in writes:
        text = w["data"]["activity"][-1]["text"]
        print(f"  {w['doc_id']}: {text}")

    if not writes:
        print("nothing to write")
        return 0
    if not args.write:
        print(f"dry run -- {len(writes)} update(s) planned; re-run with --write to emit batch files")
        return 0
    files = write_batches(writes, args.out_dir, "enrich")
    print(f"{len(writes)} update(s) -> {len(files)} batch file(s) in {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
