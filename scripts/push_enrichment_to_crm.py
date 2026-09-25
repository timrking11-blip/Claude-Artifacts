#!/usr/bin/env python3
"""Carry enrichment from the data layer into the CRM, and flag proposal-ready contacts.

Reads master (this repo) and a dump of the CRM System's contacts and accounts,
joins them by stored key (crm.crm_sync.join_master: the contact's master_id,
then its Apollo id -- never its email), and plans one `update` per contact
that would actually change. Three kinds of change, and only three:

  1. Enrichment fields the CRM does not own and does not yet have --
     seniority, industry, employees, technologies, linkedin, city/state.
     A CRM value that already exists is never overwritten.
  2. The `proposal_ready` flag, from crm.crm_sync.proposal_ready().
  3. Stored keys and the data layer's view (crm.crm_sync.KEY_FIELDS):
     master_id, org_id (exact domain match with an account only; a name-only
     match gets the review_org flag instead), provenance, and the held
     conflicts from data/master/review.json. These add no activity entry and
     leave updated_at alone -- the run's line in the CRM runlog records them.

It never emits stage, notes, next step, deal value, product, proposal_*, or
any Apollo-owned field. crm_sync.assert_not_owned() enforces that at plan
time and the test suite checks it. `--keys-only` plans the third kind alone.

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
    KEY_FIELDS,
    PROPOSAL_READY_FLAG,
    REVIEW_ORG_FLAG,
    assert_not_owned,
    join_master,
    load_crm_dump,
    load_review,
    org_key,
    pinned,
    proposal_ready,
    provenance_changed,
    provenance_view,
    system_activity,
    utcnow_iso,
    with_flag,
    write_batches,
)
from crm.master import load_master
from crm.schema import Contact

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


def plan_keys(rec: Contact | None, doc: dict, accounts: dict[str, dict] | None,
              review: dict[str, list[dict]] | None) -> tuple[dict[str, Any], bool | None]:
    """Key fields to write, and whether the contact needs org review (None: unknown).

    `accounts` is None when the dump had no accounts collection: then org_id
    is neither set nor cleared. `review` is None when master has no
    review.json yet: then `held` is left as it is.
    """
    data: dict[str, Any] = {}
    if rec is not None and doc.get("master_id") != rec.contact_id:
        data["master_id"] = rec.contact_id
    review_org = None
    if accounts is not None:
        org_id, review_org = org_key(doc, accounts)
        if org_id and doc.get("org_id") != org_id:
            data["org_id"] = org_id
        elif not org_id and doc.get("org_id") and doc["org_id"] not in accounts:
            data["org_id"] = {"__delete__": True}
    if rec is not None:
        prov = provenance_view(rec)
        if prov and provenance_changed(doc.get("provenance"), prov):
            data["provenance"] = prov
        if review is not None:
            held = review.get(rec.contact_id, [])
            if held != (doc.get("held") or []):
                data["held"] = held
    return data, review_org


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


def plan(master: list[Contact], docs: dict[str, dict], now: str | None = None, *,
         accounts: dict[str, dict] | None = None, review: dict[str, list[dict]] | None = None,
         keys_only: bool = False) -> list[dict[str, Any]]:
    """Every ArtifactData `update` this run would make. Pure; no I/O."""
    now = now or utcnow_iso()
    joined = join_master(master, docs).joined
    writes: list[dict[str, Any]] = []
    for doc_id, doc in docs.items():
        data: dict[str, Any] = {}
        notes: list[str] = []
        rec = joined.get(doc_id)
        flags = list(doc.get("flags") or [])

        keys, review_org = plan_keys(rec, doc, accounts, review)
        data.update(keys)
        if review_org is not None and review_org != (REVIEW_ORG_FLAG in flags):
            flags = with_flag(flags, REVIEW_ORG_FLAG, review_org)

        if not keys_only:
            if rec is not None:
                enrich, sources = plan_enrichment(rec, doc)
                if enrich:
                    data.update(enrich)
                    notes.append(f"Enriched {', '.join(sorted(enrich))} from {', '.join(sources) or 'the data layer'}")
            ready = proposal_ready(doc)
            if ready != (PROPOSAL_READY_FLAG in flags):
                flags = with_flag(flags, PROPOSAL_READY_FLAG, ready)
                notes.append("Marked proposal-ready: qualified, reachable, and touched"
                             if ready else "No longer proposal-ready")

        if flags != list(doc.get("flags") or []):
            data["flags"] = flags
        if not data:
            continue
        assert_not_owned({k: v for k, v in data.items() if k != "flags"})
        if notes:
            data["activity"] = system_activity(doc.get("activity"), "; ".join(notes), ts=now)
            data["updated_at"] = now
        writes.append(pinned(doc, {"op": "update", "collection": "contacts", "doc_id": doc_id, "data": data}))
    return writes


def describe(write: dict[str, Any]) -> str:
    """One line per planned write, for the run's printout."""
    d = write["data"]
    if d.get("activity"):
        return d["activity"][-1]["text"]
    parts = []
    for k in ("master_id", "org_id"):
        if k in d:
            parts.append(f"{k} cleared" if isinstance(d[k], dict) else f"{k} {d[k]}")
    if "provenance" in d:
        parts.append(f"provenance {len(d['provenance'])} field(s)")
    if "held" in d:
        parts.append(f"held {len(d['held'])}")
    if "flags" in d:
        parts.append(f"flags {d['flags']}")
    return "; ".join(parts) or "update"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crm-dump", type=Path, required=True, help="ArtifactData out_dir of the CRM contacts")
    parser.add_argument("--master", type=Path, default=None)
    parser.add_argument("--review", type=Path, default=config.MASTER_REVIEW)
    parser.add_argument("--out-dir", type=Path, default=config.CRM_BATCH_DIR)
    parser.add_argument("--keys-only", action="store_true",
                        help="plan stored keys, provenance and held conflicts only; no enrichment, no proposal flag")
    parser.add_argument("--write", action="store_true", help="emit batch files (default: dry run)")
    args = parser.parse_args()

    master = load_master(args.master)
    docs = load_crm_dump(args.crm_dump)
    accounts = load_crm_dump(args.crm_dump, "accounts") if (args.crm_dump / "accounts").is_dir() else None
    review = load_review(args.review)
    writes = plan(master, docs, accounts=accounts, review=review, keys_only=args.keys_only)
    join = join_master(master, docs)

    def count(key: str) -> int:
        return sum(1 for w in writes if key in w["data"])

    enriched = sum(1 for w in writes if w["data"].get("activity") and any(
        k not in ("flags", "activity", "updated_at", *KEY_FIELDS) for k in w["data"]))
    flagged = sum(1 for w in writes if PROPOSAL_READY_FLAG in (w["data"].get("flags") or [])
                  and PROPOSAL_READY_FLAG not in (docs[w["doc_id"]].get("flags") or []))
    unflagged = sum(1 for w in writes if "flags" in w["data"] and PROPOSAL_READY_FLAG not in w["data"]["flags"]
                    and PROPOSAL_READY_FLAG in (docs[w["doc_id"]].get("flags") or []))
    ready_total = sum(1 for d in docs.values() if proposal_ready(d))
    print(f"master {len(master)} · crm {len(docs)} · joined {len(join.joined)} "
          f"({sum(1 for h in join.how.values() if h == 'master_id')} by master_id, "
          f"{sum(1 for h in join.how.values() if h == 'apollo_id')} by Apollo id) · "
          f"email-only (unkeyed) {len(join.email_only)}")
    print(f"accounts {'not dumped' if accounts is None else len(accounts)} · "
          f"review queue {'absent' if review is None else sum(len(v) for v in review.values())} item(s)")
    print(f"keys: master_id {count('master_id')}, org_id {count('org_id')}, "
          f"provenance {count('provenance')}, held {count('held')}")
    if not args.keys_only:
        print(f"proposal-ready now: {ready_total}  (newly flagged {flagged}, unflagged {unflagged})")
        print(f"enrichment writes: {enriched}")
    for w in writes:
        print(f"  {w['doc_id']}: {describe(w)}")

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
