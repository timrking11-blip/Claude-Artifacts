#!/usr/bin/env python3
"""Put composed prequalification proposals into the CRM contact's notes.

Reads every proposal file the account-research agent wrote under
data/proposals/ and a dump of the CRM System's contacts. For each contact the
proposal is for, it plans one `update` that:

  - APPENDS a dated, id-stamped block to `notes` (never overwrites -- notes
    are the human's; this only ever adds to the end),
  - sets proposal_status to "drafted" when it is unset, and never regresses a
    status that has moved on (sent / in_discussion / accepted / declined),
  - fills proposal_scope from the request's first line when empty,
  - records proposal_ref = the proposal id, which is what makes a re-run a
    no-op for contacts that already carry this proposal,
  - carries the founder note (crm/founder_note.py) under the proposal when the
    record has one, so the extenuating criteria travel with the draft.

Contacts are found by the Apollo ids the proposal file carries, then by the
master contact ids it carries, then -- for a request that named a company
but no person -- by company domain against the CRM's website field.

Dry-run by default. `--write` emits data/artifact/crm/proposal_*.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config
from crm.crm_sync import load_crm_dump, pinned, system_activity, utcnow_iso, write_batches
from crm.master import load_master
from crm.schema import Contact, normalize_domain, normalize_email

NOTES_HEADER = "--- Prequalification proposal · {date} · {pid} ---"
#: Statuses a fresh draft must not overwrite.
ADVANCED = {"sent", "in_discussion", "accepted", "declined"}


def load_proposals(proposals_dir: Path) -> list[dict[str, Any]]:
    out = []
    for path in sorted(proposals_dir.glob("*.json")):
        p = json.loads(path.read_text() or "{}")
        if p.get("proposal_id") and p.get("proposal_markdown"):
            p["_path"] = str(path)
            out.append(p)
    return out


def targets_for(proposal: dict[str, Any], master: list[Contact], docs: dict[str, dict]) -> list[str]:
    """CRM doc ids this proposal belongs on, in priority order, no duplicates."""
    found: list[str] = []

    def add(doc_id: str | None) -> None:
        if doc_id and doc_id in docs and doc_id not in found:
            found.append(doc_id)

    for apollo_id in proposal.get("apollo_contact_ids") or []:
        add(apollo_id)

    by_id = {c.contact_id: c for c in master}
    crm_by_email = {normalize_email(d.get("email")): doc_id for doc_id, d in docs.items() if normalize_email(d.get("email"))}
    for cid in proposal.get("contact_ids") or []:
        rec = by_id.get(cid)
        if not rec:
            continue
        add(rec.apollo_contact_id)
        add(crm_by_email.get(normalize_email(rec.email)))

    if not found:
        domain = normalize_domain((proposal.get("account") or {}).get("domain"))
        if domain:
            for doc_id, d in docs.items():
                if normalize_domain(d.get("website")) == domain:
                    add(doc_id)
    return found


def first_line(text: str | None, limit: int = 120) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:limit]
    return ""


def plan(proposals: list[dict[str, Any]], master: list[Contact], docs: dict[str, dict],
         now: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Updates to make, plus a line per proposal saying what happened. Pure."""
    now = now or utcnow_iso()
    date = now[:10]
    writes: list[dict[str, Any]] = []
    log: list[str] = []
    for p in proposals:
        pid = p["proposal_id"]
        ids = targets_for(p, master, docs)
        if not ids:
            log.append(f"{pid}: no CRM contact matched (account {p.get('account', {}).get('name')!r}) -- nothing written")
            continue
        applied = skipped = 0
        for doc_id in ids:
            doc = docs[doc_id]
            if doc.get("proposal_ref") == pid:
                skipped += 1
                continue
            block = NOTES_HEADER.format(date=date, pid=pid) + "\n" + p["proposal_markdown"].strip()
            founder = (p.get("founder_note") or {}).get("text") if isinstance(p.get("founder_note"), dict) else p.get("founder_note")
            if founder:
                block += "\n\nFounder note:\n" + str(founder).strip()
            existing = (doc.get("notes") or "").rstrip()
            data: dict[str, Any] = {
                "notes": (existing + "\n\n" + block) if existing else block,
                "proposal_ref": pid,
                "updated_at": now,
                "activity": system_activity(doc.get("activity"), f"Prequalification proposal drafted ({pid})", ts=now),
            }
            status = doc.get("proposal_status") or "none"
            if status not in ADVANCED:
                data["proposal_status"] = "drafted"
            if not doc.get("proposal_scope"):
                scope = first_line(p.get("request_text")) or first_line(p["proposal_markdown"].replace("#", ""))
                if scope:
                    data["proposal_scope"] = scope
            writes.append(pinned(doc, {"op": "update", "collection": "contacts", "doc_id": doc_id, "data": data}))
            applied += 1
        log.append(f"{pid}: {applied} contact(s) updated, {skipped} already carried it")
    return writes, log


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crm-dump", type=Path, required=True)
    parser.add_argument("--proposals-dir", type=Path, default=config.PROPOSALS_DIR)
    parser.add_argument("--master", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=config.CRM_BATCH_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    proposals = load_proposals(args.proposals_dir)
    if not proposals:
        print(f"no proposals in {args.proposals_dir}; nothing to do")
        return 0
    master = load_master(args.master)
    docs = load_crm_dump(args.crm_dump)
    writes, log = plan(proposals, master, docs)
    for line in log:
        print(f"  {line}")
    if not writes:
        print("nothing to write")
        return 0
    if not args.write:
        print(f"dry run -- {len(writes)} update(s) planned; re-run with --write to emit batch files")
        return 0
    files = write_batches(writes, args.out_dir, "proposal")
    print(f"{len(writes)} update(s) -> {len(files)} batch file(s) in {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
