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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .schema import Contact, normalize_domain, normalize_email, normalize_name

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

#: Stored keys and the data layer's view of a contact. Only the push scripts
#: write them (Phase 2 of the architecture blueprint): no page or sync
#: computes a person->organization or CRM->master link at read time.
KEY_FIELDS = ("master_id", "org_id", "provenance", "held")

#: Flag for a contact whose company name matches an account while its domain
#: does not. It is never linked by name; the owner decides.
REVIEW_ORG_FLAG = "review_org"

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_crm_dump(dump_dir: Path, collection: str = CONTACTS_COLLECTION) -> dict[str, dict[str, Any]]:
    """Read a dump made with `ArtifactData list ... out_dir=<dump_dir>`.

    The layout is <dump_dir>/<collection>/<doc_id>.json with the document's fields
    at the top level of each file. The files do NOT carry the document
    version, but the listing that produced them does, and the batch tool
    refuses an unpinned update to an existing document. So the session that
    takes the dump writes <dump_dir>/versions.json ({doc_id: version}) from
    the listing; when it exists, each doc gets a private `_version` and the
    push scripts pin their writes with it. Every write is still an `update`
    (a field merge), never a `set` -- the blast radius is the fields written.

    A second collection (the CRM's `accounts`) reads the same way, with its
    versions in <dump_dir>/versions_<collection>.json; absent, it is empty.
    """
    contacts_dir = dump_dir / collection
    if not contacts_dir.is_dir():
        if collection != CONTACTS_COLLECTION:
            return {}
        contacts_dir = dump_dir
    versions: dict[str, Any] = {}
    vpath = dump_dir / ("versions.json" if collection == CONTACTS_COLLECTION else f"versions_{collection}.json")
    if vpath.exists():
        versions = json.loads(vpath.read_text() or "{}")
    docs: dict[str, dict[str, Any]] = {}
    for path in sorted(contacts_dir.glob("*.json")):
        doc = json.loads(path.read_text() or "{}")
        if isinstance(versions.get(path.stem), int):
            doc["_version"] = versions[path.stem]
        docs[path.stem] = doc
    return docs


def pinned(doc: dict[str, Any], write: dict[str, Any]) -> dict[str, Any]:
    """Attach if_version to a write when the dump knew the document's version."""
    if isinstance(doc.get("_version"), int):
        write["if_version"] = doc["_version"]
    return write


def index_crm_by_email(docs: dict[str, dict[str, Any]]) -> dict[str, str]:
    """normalized email -> doc_id, for the fallback join."""
    out: dict[str, str] = {}
    for doc_id, doc in docs.items():
        email = normalize_email(doc.get("email"))
        if email:
            out.setdefault(email, doc_id)
    return out


@dataclass
class Join:
    """How CRM contacts meet master rows, by stored key only.

    `joined` maps doc_id -> master Contact, through the stored `master_id`
    first and the Apollo id (the doc id) second. An email match is never a
    join: it is listed in `email_only` for scripts/backfill_keys.py to key
    once, with a changelog line, so a changed email cannot silently re-point
    a contact at someone else.
    """

    joined: dict[str, Contact] = field(default_factory=dict)
    how: dict[str, str] = field(default_factory=dict)
    email_only: dict[str, Contact] = field(default_factory=dict)
    #: doc_id -> master_id stored on the doc that names no master row.
    dangling: dict[str, str] = field(default_factory=dict)
    #: doc_id -> (stored master_id, master row the Apollo id points at).
    disagree: dict[str, tuple[str, str]] = field(default_factory=dict)


def join_master(master: list[Contact], docs: dict[str, dict[str, Any]]) -> Join:
    by_id = {c.contact_id: c for c in master if c.contact_id}
    by_apollo = {c.apollo_contact_id: c for c in master if c.apollo_contact_id}
    by_email = {normalize_email(c.email): c for c in master if normalize_email(c.email)}
    crm_emails = index_crm_by_email(docs)
    out = Join()
    for doc_id, doc in docs.items():
        stored = doc.get("master_id")
        via_apollo = by_apollo.get(doc_id)
        if stored:
            rec = by_id.get(stored)
            if rec is None:
                out.dangling[doc_id] = stored
            elif via_apollo is not None and via_apollo.contact_id != stored:
                out.disagree[doc_id] = (stored, via_apollo.contact_id)
            else:
                out.joined[doc_id], out.how[doc_id] = rec, "master_id"
            continue
        if via_apollo is not None:
            out.joined[doc_id], out.how[doc_id] = via_apollo, "apollo_id"
            continue
        email = normalize_email(doc.get("email"))
        if email and email in by_email and crm_emails.get(email) == doc_id:
            out.email_only[doc_id] = by_email[email]
    return out


def org_key(doc: dict[str, Any], accounts: dict[str, dict[str, Any]]) -> tuple[str | None, bool]:
    """(account doc id, needs review) for one contact.

    Linked only on an exact domain match between the contact's website and an
    account's domain. A company name equal to an account's name with a
    different or missing domain is flagged for review and never linked --
    "Acme" must not attach to "Acme Mechanical", and a shared name is not a
    shared company either.
    """
    domain = normalize_domain(doc.get("website"))
    if domain:
        hits = sorted(a_id for a_id, a in accounts.items()
                      if normalize_domain(a.get("domain") or a.get("website")) == domain)
        if hits:
            return hits[0], False
    name = (normalize_name(doc.get("company")) or "").lower()
    if name and any((normalize_name(a.get("name")) or "").lower() == name for a in accounts.values()):
        return None, True
    return None, False


def provenance_view(rec: Contact) -> dict[str, dict[str, Any]]:
    """{field: {value, source, observed_at}} for the CRM drawer's Sources section."""
    out: dict[str, dict[str, Any]] = {}
    for name, prov in sorted((rec.provenance or {}).items()):
        if not isinstance(prov, dict) or not prov.get("source"):
            continue
        value = getattr(rec, name, None)
        if value is None or value == "" or value == []:
            continue
        out[name] = {"value": value, "source": prov["source"], "observed_at": prov.get("observed_at") or ""}
    return out


def provenance_changed(current: Any, new: dict[str, dict[str, Any]]) -> bool:
    """True when a value or source moved. A re-observed date alone is not a change."""
    def shape(p: Any) -> dict[str, tuple[str, str]]:
        if not isinstance(p, dict):
            return {}
        return {k: (json.dumps(v.get("value"), sort_keys=True), v.get("source"))
                for k, v in p.items() if isinstance(v, dict)}
    return shape(current) != shape(new)


def load_review(path: Path) -> dict[str, list[dict[str, Any]]] | None:
    """master contact_id -> held items, from data/master/review.json. None if absent."""
    if not path.exists():
        return None
    raw = json.loads(path.read_text() or "{}")
    out: dict[str, list[dict[str, Any]]] = {}
    for c in raw.get("conflicts_held") or []:
        out.setdefault(c.get("contact_id", ""), []).append(
            {"kind": "conflict", "field": c.get("field"), "kept": c.get("kept"),
             "rejected": c.get("rejected"), "source": c.get("source")})
    for a in raw.get("ambiguous_matches") or []:
        for cid in a.get("candidates") or []:
            out.setdefault(cid, []).append(
                {"kind": "ambiguous", "keys": a.get("keys") or [], "candidates": a.get("candidates") or [],
                 "source": a.get("source")})
    out.pop("", None)
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
