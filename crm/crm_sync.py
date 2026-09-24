"""Shared pieces for talking to the CRM System artifact's database.

Three scripts share these: validate_sync.py, push_enrichment_to_crm.py and
push_proposals_to_crm.py. They all read the same dump layout, decide the same
"proposal-ready" question, and emit the same batch-file shape, so the logic
lives here once and is tested once.

The CRM System artifact keys contact documents by Apollo contact id and owns a
different schema from this repo's Contact record. Nothing here writes to the
database itself -- a Claude session applies the batch files with ArtifactData.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .schema import normalize_email

BATCH_LIMIT = 50
CONTACTS_COLLECTION = "contacts"

#: The proposal_status vocabulary. The CRM page's PSTATUS list must match
#: this exactly; validate_sync.py checks documents against it.
PROPOSAL_STATUSES = ("none", "drafted", "sent", "in_discussion", "accepted", "declined")

#: Flag the enrichment push sets on contacts that pass proposal_ready().
PROPOSAL_READY_FLAG = "proposal_ready"

#: Fields the CRM page and its Apollo sync own. The push scripts must never
#: emit any of these -- stage is the human's, the rest are either the
#: human's or the Monday sync's. Tested.
CRM_OWNED_FIELDS = frozenset({
    "stage", "notes", "next_step", "next_date", "deal_value", "product",
    "apollo_id", "apollo_lists", "apollo_synced_at", "apollo_url",
    "first_name", "last_name", "name", "title", "company", "email", "mobile",
    "segment", "qualified", "origin", "created_at",
})


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_crm_dump(dump_dir: Path) -> dict[str, dict[str, Any]]:
    """Read a dump made with `ArtifactData list ... out_dir=<dump_dir>`.

    The layout is <dump_dir>/contacts/<doc_id>.json with the document's fields
    at the top level of each file. The dump does NOT carry the document
    version, so batch writes built from it cannot be pinned with if_version;
    that is why every write here is an `update` (a field merge) and never a
    `set` -- the blast radius is the fields written, nothing else.
    """
    contacts_dir = dump_dir / CONTACTS_COLLECTION
    if not contacts_dir.is_dir():
        contacts_dir = dump_dir
    docs: dict[str, dict[str, Any]] = {}
    for path in sorted(contacts_dir.glob("*.json")):
        doc = json.loads(path.read_text() or "{}")
        docs[path.stem] = doc
    return docs


def index_crm_by_email(docs: dict[str, dict[str, Any]]) -> dict[str, str]:
    """normalized email -> doc_id, for the fallback join."""
    out: dict[str, str] = {}
    for doc_id, doc in docs.items():
        email = normalize_email(doc.get("email"))
        if email:
            out.setdefault(email, doc_id)
    return out


def proposal_ready(doc: dict[str, Any]) -> bool:
    """The rule the user chose: qualified, reachable, not excluded, touched.

    Every criterion is deliberately about the CRM document alone -- the flag
    must be explainable to someone looking at the contact drawer, and it must
    not depend on enrichment that may not exist yet.
    """
    if doc.get("qualified") is not True:
        return False
    if not normalize_email(doc.get("email")):
        return False
    flags = set(doc.get("flags") or [])
    if flags & {"disqualified", "removed_from_list"}:
        return False
    return any(a.get("type") != "system" for a in (doc.get("activity") or []))


def with_flag(flags: Iterable[str] | None, flag: str, present: bool) -> list[str]:
    """Return the flag list with `flag` added or removed, order preserved."""
    out = [f for f in (flags or []) if f != flag]
    if present:
        out.append(flag)
    return out


def system_activity(existing: Iterable[dict[str, Any]] | None, text: str, ts: str | None = None,
                    kind: str = "system") -> list[dict[str, Any]]:
    """The contact's activity list with one entry appended."""
    return [*(existing or []), {"ts": ts or utcnow_iso(), "type": kind, "text": text}]


def assert_not_owned(data: dict[str, Any]) -> None:
    """Refuse to build a write that touches a CRM-owned field.

    A programming error here would silently overwrite a human's stage or
    notes on the next Monday; failing loudly at plan time is the cheaper
    outcome. `notes` is handled by push_proposals_to_crm, which appends --
    it passes the merged value explicitly and is exempted by name there.
    """
    touched = set(data) & CRM_OWNED_FIELDS
    if touched:
        raise ValueError(f"write touches CRM-owned field(s): {sorted(touched)}")


def write_batches(writes: list[dict[str, Any]], out_dir: Path, prefix: str) -> list[Path]:
    """Split writes into <=50-entry batch files a Claude session can apply.

    Each entry is already a complete ArtifactData batch write:
    {"op": "update", "collection": "contacts", "doc_id": ..., "data": {...}}.
    Stale files with the same prefix are removed first so a re-run cannot
    leave last week's batch lying next to this week's.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob(f"{prefix}_*.json"):
        stale.unlink()
    files: list[Path] = []
    for i in range(0, len(writes), BATCH_LIMIT):
        chunk = writes[i : i + BATCH_LIMIT]
        path = out_dir / f"{prefix}_{i // BATCH_LIMIT:03d}.json"
        path.write_text(json.dumps(chunk, indent=2, ensure_ascii=False) + "\n")
        files.append(path)
    return files
