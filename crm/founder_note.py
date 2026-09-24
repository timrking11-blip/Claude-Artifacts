"""The note to the founder: extenuating criteria a button run must surface.

A composition run from the Intake page drafts and files a prequalification
proposal without anyone reading the CRM first. This module is the reader.
Given the run manifest, the run state the deterministic legs produced, and a
dump of the CRM System's contacts, it lists what the founder should know
before that proposal goes anywhere.

Two severities:

  HOLD  -- the proposal is drafted and filed, but the run ends `needs_founder`
           and proposal_status stays `drafted`. Something about this account
           needs the founder's decision (pricing was asked for, a proposal
           already went out, an open deal exists, ...).
  Note  -- for information; the run ends `done`.

Every criterion is deterministic and explainable from the documents alone, so
it is tested one by one in tests/test_founder_note.py. Judgement calls the
composer makes (request outside the practice, unrealistic deadline) arrive
separately as `composer_flags` and are appended as HOLD lines by
scripts/compose_account.py finalize.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .crm_sync import proposal_ready
from .schema import normalize_domain

STATUS_DONE = "done"
STATUS_NEEDS_FOUNDER = "needs_founder"

#: Money or pricing in the *request*. The proposal writer already refuses
#: money in the proposal; this catches the founder's decision upstream: if
#: the requester asked about rates, someone has to decide what to say.
REQUEST_MONEY = re.compile(
    r"(\$\s?\d|\b\d[\d,]*\s?(?:USD|dollars)\b|\bper\s+(?:hour|day|month)\b"
    r"|\b(?:budget|rates?|retainer|hourly|fixed[- ]fee|pricing|quote)\b)",
    re.I,
)

#: A contact at one of these stages has an open conversation the founder owns.
OPEN_DEAL_STAGES = frozenset({"meeting", "proposal", "won"})
EXCLUDED_FLAGS = frozenset({"disqualified", "removed_from_list"})

#: The Monday sync window the skill says to avoid (America/New_York).
SYNC_WINDOW_TZ = ZoneInfo("America/New_York")
SYNC_WINDOW_START = time(6, 45)
SYNC_WINDOW_END = time(8, 15)

#: Ledger-quality floors from the intake page, as a fraction of contacts that
#: are neither missing an email nor stale. "none" passes everything through.
QUALITY_FLOORS = {"none": 0.0, "fair": 0.4, "good": 0.7}


@dataclass
class FounderNote:
    holds: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    matched_doc_ids: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return STATUS_NEEDS_FOUNDER if self.holds else STATUS_DONE

    @property
    def text(self) -> str:
        lines = [f"HOLD — {h}" for h in self.holds] + [f"Note — {n}" for n in self.notes]
        return "\n".join(lines) if lines else "Nothing extenuating; proceed as drafted."

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "holds": list(self.holds), "notes": list(self.notes),
                "text": self.text, "matched_doc_ids": list(self.matched_doc_ids)}


def in_sync_window(now: datetime) -> bool:
    """True inside Mon 06:45–08:15 America/New_York."""
    local = now.astimezone(SYNC_WINDOW_TZ)
    return local.weekday() == 0 and SYNC_WINDOW_START <= local.time() <= SYNC_WINDOW_END


def quality_score(ledger_quality: dict[str, Any] | None) -> float | None:
    """Share of the account's contacts that have an email and are not stale."""
    if not ledger_quality:
        return None
    count = int(ledger_quality.get("contact_count") or 0)
    if count == 0:
        return None
    bad = set(ledger_quality.get("missing_email") or []) | set(ledger_quality.get("stale_over_90_days") or [])
    return max(0.0, 1.0 - len(bad) / count)


def match_crm_contacts(state: dict[str, Any], docs: dict[str, dict[str, Any]]) -> list[str]:
    """CRM contact ids this run concerns: the account's Apollo ids, else domain."""
    found: list[str] = []
    for row in state.get("account_contacts") or []:
        aid = row.get("apollo_contact_id")
        if aid and aid in docs and aid not in found:
            found.append(aid)
    if not found:
        domain = normalize_domain((state.get("account") or {}).get("domain"))
        if domain:
            for doc_id, doc in docs.items():
                if normalize_domain(doc.get("website")) == domain and doc_id not in found:
                    found.append(doc_id)
    return found


def _label(doc: dict[str, Any], doc_id: str) -> str:
    return doc.get("name") or " ".join(p for p in (doc.get("first_name"), doc.get("last_name")) if p) or doc_id


def assess(manifest: dict[str, Any], state: dict[str, Any], docs: dict[str, dict[str, Any]],
           now: datetime, *, account_lists_empty: bool = True) -> FounderNote:
    """Every extenuating criterion, evaluated once. Pure; no I/O."""
    fn = FounderNote()
    m_state = manifest.get("state") or {}
    request = manifest.get("request") or {}
    request_text = request.get("text") or ""
    disposition = (manifest.get("crm") or {}).get("disposition")
    account = state.get("account") or {}
    matched = match_crm_contacts(state, docs)
    fn.matched_doc_ids = matched

    # ---- HOLD --------------------------------------------------------------
    hit = REQUEST_MONEY.search(request_text)
    if hit:
        fn.holds.append(f"The request talks about money ({hit.group(0).strip()!r}); no market rates are set, "
                        "so decide what to say about pricing before this goes out.")

    for doc_id in matched:
        doc = docs[doc_id]
        who = _label(doc, doc_id)
        if doc.get("proposal_ref"):
            fn.holds.append(f"{who} already carries proposal {doc['proposal_ref']} "
                            f"(status {doc.get('proposal_status') or 'drafted'}); this would be a repeat.")
        flagged = set(doc.get("flags") or []) & EXCLUDED_FLAGS
        if flagged:
            fn.holds.append(f"{who} is flagged {', '.join(sorted(flagged))} in the CRM.")
        if doc.get("stage") in OPEN_DEAL_STAGES:
            fn.holds.append(f"{who} is at stage '{doc['stage']}' — an open conversation; coordinate before a new prequal.")

    if disposition == "apollo" and account_lists_empty:
        fn.holds.append("Disposition is Apollo but meta/config.account_lists is empty: the account would upload "
                        "and never read back. Re-add the list id or switch to manual.")

    if in_sync_window(now):
        fn.holds.append("Run started inside the Monday sync window (06:45–08:15 ET); the sync may have read a "
                        "half-written record. Check the contact after 08:15 ET.")

    # ---- Note --------------------------------------------------------------
    if not matched:
        fn.notes.append("No CRM contact matched this account; the proposal is filed on the account record only, "
                        "with nobody to attach it to.")
    elif not any(proposal_ready(docs[d]) for d in matched):
        fn.notes.append("No matched contact is proposal-ready (qualified, reachable, touched); treat this as cold outreach.")

    if not account.get("in_ledger", True):
        fn.notes.append("Account is not in the enriched data layer; the proposal leans on the website and the request alone.")
    else:
        lq = state.get("ledger_quality")
        floor_name = (m_state.get("ledger_quality") or {}).get("quality_floor") or "none"
        score = quality_score(lq)
        if score is not None and score < QUALITY_FLOORS.get(floor_name, 0.0):
            fn.notes.append(f"Ledger quality {score:.0%} is below the '{floor_name}' floor; ledger-derived claims are unsupported.")
        if lq and lq.get("contact_count") and len(lq.get("stale_over_90_days") or []) == lq["contact_count"]:
            fn.notes.append("Every ledger contact at this account is older than 90 days.")

    if state.get("page_error"):
        fn.notes.append(f"Website fetch failed ({state['page_error']}); no website summary.")
    if state.get("warehouse_findings") and state.get("warehouse_sentinel"):
        fn.notes.append("Warehouse findings are the 'not available' sentinel; no BigQuery in this run.")

    opted = [k for k, v in m_state.items() if isinstance(v, dict) and v.get("opted_out")]
    if opted:
        fn.notes.append(f"Opted out at intake: {', '.join(opted)}.")

    return fn
