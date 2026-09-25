"""Activity capture (architecture blueprint, tool T2): the scorecard counts what happened, not what was typed.

Sent mail, replies and meetings arrive as rows on a CRM contact's `activity`
list, from Apollo sequence and email events, Gmail, and Google Calendar:

    {ts, type: email | reply | meeting | call, direction: out | in,
     text: the subject or event title only, channel_ref: "<channel>:<id>"}

`channel_ref` makes capture idempotent: a row whose reference the contact
already carries is never added twice, and a row the owner logged by hand on
the same day and type is not duplicated by a captured one. Activity is
append-only (CLAUDE.md): nothing here edits or removes a row.

The Ops refresh's scorecard reads these rows: first touches, replies and
calls booked are counted from activity alone (the Phase 2 gate), never from
the pipeline stage a person set by hand.

Pure planning, like the rest of crm/: a Claude session calls Apollo, Gmail
and Calendar, maps each hit to a row here, and applies the planned updates
with ArtifactData, pinned.
"""

from __future__ import annotations

from typing import Any, Iterable

from .crm_sync import CONTACTS_COLLECTION, pinned, utcnow_iso
from .schema import normalize_email

TYPES = ("email", "reply", "meeting", "call")
DIRECTIONS = ("out", "in")
CHANNELS = ("apollo", "gmail", "gcal")
#: Row text is a subject or an event title. Never a message body.
TEXT_LIMIT = 140


def row(ts: str, kind: str, direction: str, text: str, channel: str, ref_id: str) -> dict[str, Any]:
    """One captured activity row. Raises on a shape the scorecard could miscount."""
    if kind not in TYPES:
        raise ValueError(f"activity type {kind!r} not in {TYPES}")
    if direction not in DIRECTIONS:
        raise ValueError(f"direction {direction!r} not in {DIRECTIONS}")
    if channel not in CHANNELS or not ref_id:
        raise ValueError(f"channel_ref needs a channel in {CHANNELS} and an id")
    text = " ".join((text or "").split())
    if len(text) > TEXT_LIMIT:
        text = text[: TEXT_LIMIT - 1] + "…"
    return {"ts": ts, "type": kind, "direction": direction, "text": text or "(no subject)",
            "channel_ref": f"{channel}:{ref_id}"}


def merge_rows(existing: Iterable[dict[str, Any]] | None, rows: Iterable[dict[str, Any]]) -> tuple[list[dict], int]:
    """(the activity list with new rows appended in time order, how many were added)."""
    current = list(existing or [])
    refs = {a.get("channel_ref") for a in current if a.get("channel_ref")}
    by_hand = {(a.get("type"), str(a.get("ts") or "")[:10]) for a in current if not a.get("channel_ref")}
    added = []
    for r in sorted(rows, key=lambda x: x["ts"]):
        if r["channel_ref"] in refs or (r["type"], r["ts"][:10]) in by_hand:
            continue
        refs.add(r["channel_ref"])
        added.append(r)
    return current + added, len(added)


def plan_capture(docs: dict[str, dict[str, Any]], rows_by_email: dict[str, list[dict[str, Any]]],
                 now: str | None = None) -> list[dict[str, Any]]:
    """Pinned `update` writes that append captured rows. Only `activity` changes.

    Rows are keyed by the other party's email address; a contact is found by
    its own email on the CRM document, the key the mail and the invite carry.
    An address no contact holds is dropped here -- capture never creates a
    contact.
    """
    now = now or utcnow_iso()
    by_email: dict[str, str] = {}
    for doc_id, doc in docs.items():
        email = normalize_email(doc.get("email"))
        if email:
            by_email.setdefault(email, doc_id)
    writes = []
    for email, rows in sorted(rows_by_email.items()):
        doc_id = by_email.get(normalize_email(email) or "")
        if not doc_id:
            continue
        merged, added = merge_rows(docs[doc_id].get("activity"), rows)
        if added:
            writes.append(pinned(docs[doc_id], {"op": "update", "collection": CONTACTS_COLLECTION,
                                                "doc_id": doc_id, "data": {"activity": merged}}))
    return writes


def _is_reply(a: dict[str, Any]) -> bool:
    # A captured inbound message, or a reply pasted through the CRM's "Log reply" button.
    return a.get("type") == "reply" or (a.get("type") == "linkedin" and str(a.get("text", "")).startswith("Reply ("))


def scorecard(docs: dict[str, dict[str, Any]], since: str | None = None) -> dict[str, Any]:
    """First touches, replies and calls booked, counted per contact from activity rows only.

    A first touch is an outbound email (captured or logged by hand); a reply
    is an inbound message or a logged reply; a call booked is a meeting or a
    call. `since` (YYYY-MM-DD) limits the window, e.g. the 60-day plan's start.
    """
    def rows(doc):
        return [a for a in (doc.get("activity") or []) if a.get("type") != "system"
                and (not since or str(a.get("ts") or "")[:10] >= since)]

    touched = replied = booked = 0
    for doc in docs.values():
        acts = rows(doc)
        touched += any(a.get("type") == "email" and a.get("direction", "out") == "out" for a in acts)
        replied += any(_is_reply(a) for a in acts)
        booked += any(a.get("type") in ("meeting", "call") for a in acts)
    return {"first_touches": touched, "replies": replied, "calls_booked": booked,
            "reply_rate": round(replied / touched, 3) if touched else None, "since": since}
