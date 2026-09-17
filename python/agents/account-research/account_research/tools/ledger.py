"""Ledger tools: read the CRM master ledger for one account.

The ledger is the repo's data/master/contacts.json (the committed mirror of
the CRM artifact database). These tools are pure Python -- no Google client,
no ADK import at run time -- so they are unit-testable without credentials and
so the same code runs unchanged inside Agent Runtime.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # the annotation only; keeps ADK out of the test import path
    from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

STALE_AFTER_DAYS = 90

# Highest first. Unknown/None sorts last.
SENIORITY_RANK = {
    "owner": 0, "founder": 0, "c_suite": 0, "c-suite": 0, "cxo": 0,
    "partner": 1, "vp": 1, "vice president": 1,
    "head": 2, "director": 2,
    "manager": 3, "senior": 4, "entry": 5, "intern": 6,
}


def default_ledger_path() -> Path:
    """data/master/contacts.json at the repo root, unless overridden."""
    env = os.getenv("ACCOUNT_RESEARCH_LEDGER")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[5] / "data" / "master" / "contacts.json"


def load_ledger(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or default_ledger_path()
    if not path.exists():
        logger.warning("ledger not found at %s", path)
        return []
    return json.loads(path.read_text() or "{}").get("contacts", [])


def normalize_domain(value: str | None) -> str | None:
    """Same rule as crm/schema.py: strip scheme, www and path."""
    if not value:
        return None
    value = value.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    value = value.split("/")[0].split("?")[0]
    return value or None


def _account_key(contact: dict[str, Any]) -> str | None:
    domain = normalize_domain(contact.get("company_domain"))
    if domain:
        return f"domain:{domain}"
    name = (contact.get("company_name") or "").strip().lower()
    return f"name:{name}" if name else None


def _group_accounts(contacts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in contacts:
        key = _account_key(c)
        if key:
            groups[key].append(c)
    return groups


def _describe(key: str, members: list[dict[str, Any]]) -> dict[str, Any]:
    names = [m.get("company_name") for m in members if m.get("company_name")]
    name = max(set(names), key=names.count) if names else key.split(":", 1)[1]
    domain = key[len("domain:"):] if key.startswith("domain:") else next(
        (normalize_domain(m.get("company_domain")) for m in members if m.get("company_domain")), None
    )
    return {
        "key": key,
        "name": name,
        "domain": domain,
        "contact_count": len(members),
        "industry": next((m.get("industry") for m in members if m.get("industry")), None),
        "employee_count": next((m.get("employee_count") for m in members if m.get("employee_count")), None),
    }


def find_account_tool(query: str, tool_context: "ToolContext") -> dict[str, Any]:
    """Resolves a company name or domain to one account in the ledger.

    Args:
      query: What the user typed -- a company name or a web domain.
      tool_context: ToolContext object.

    Returns:
      status "OK" with the stored account, "AMBIGUOUS" with candidates, or
      "NOT_FOUND".
    """
    q = (query or "").strip()
    if not q:
        return {"status": "ERROR", "message": "Empty query"}

    groups = _group_accounts(load_ledger())
    q_domain = normalize_domain(q) if ("." in q and " " not in q) else None
    q_lower = q.lower()

    matches: list[tuple[str, list[dict[str, Any]]]] = []
    if q_domain and f"domain:{q_domain}" in groups:
        matches = [(f"domain:{q_domain}", groups[f"domain:{q_domain}"])]
    else:
        for key, members in groups.items():
            names = {(m.get("company_name") or "").lower() for m in members}
            domain = key[len("domain:"):] if key.startswith("domain:") else ""
            if any(q_lower == n for n in names) or (q_domain and q_domain == domain):
                matches.append((key, members))
        if not matches:
            # Substring fallback. On domains, only the registrable label counts:
            # "example" must not match kernel.example through its suffix.
            for key, members in groups.items():
                names = {(m.get("company_name") or "").lower() for m in members}
                domain = key[len("domain:"):] if key.startswith("domain:") else ""
                label = domain.split(".")[0] if domain else ""
                if any(q_lower in n for n in names if n) or (label and q_lower in label):
                    matches.append((key, members))

    if not matches:
        return {"status": "NOT_FOUND", "message": f"No ledger contacts at '{q}'"}

    if len(matches) > 1:
        candidates = sorted((_describe(k, m) for k, m in matches),
                            key=lambda d: -d["contact_count"])[:5]
        return {"status": "AMBIGUOUS", "candidates": candidates}

    account = _describe(*matches[0])
    tool_context.state.update({"account": account})
    logger.info("find_account_tool(): matched %s", account["key"])
    return {"status": "OK", "account": account}


def _seniority_sort_key(contact: dict[str, Any]) -> tuple[int, str]:
    s = (contact.get("seniority") or "").lower()
    rank = SENIORITY_RANK.get(s, 9)
    return (rank, (contact.get("last_name") or "").lower())


def list_account_contacts_tool(tool_context: "ToolContext") -> dict[str, Any]:
    """Loads every ledger contact at the account stored by find_account.

    Args:
      tool_context: ToolContext object.

    Returns:
      status and the number of contacts stored under "account_contacts".
    """
    account = tool_context.state.get("account")
    if not account:
        return {"status": "ERROR", "message": "Call find_account first"}

    members = _group_accounts(load_ledger()).get(account["key"], [])
    rows = []
    for c in sorted(members, key=_seniority_sort_key):
        rows.append({
            "contact_id": c.get("contact_id"),
            "name": " ".join(p for p in (c.get("first_name"), c.get("last_name")) if p) or "(no name)",
            "title": c.get("title"),
            "seniority": c.get("seniority"),
            "location": c.get("location"),
            "has_email": bool(c.get("email")),
            "has_phone": bool(c.get("phone")),
            "has_linkedin": bool(c.get("linkedin_url")),
            "sources": c.get("sources") or [],
            "last_updated": c.get("last_updated"),
            "apollo_contact_id": c.get("apollo_contact_id"),
        })
    tool_context.state.update({"account_contacts": rows})
    return {"status": "OK", "count": len(rows)}


def assess_ledger_quality_tool(tool_context: "ToolContext") -> dict[str, Any]:
    """Flags gaps and staleness in the account's contact records.

    Args:
      tool_context: ToolContext object.

    Returns:
      status; the flags are stored under "ledger_quality".
    """
    account = tool_context.state.get("account")
    if not account:
        return {"status": "ERROR", "message": "Call find_account first"}

    members = _group_accounts(load_ledger()).get(account["key"], [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_AFTER_DAYS)

    def name(c: dict[str, Any]) -> str:
        return " ".join(p for p in (c.get("first_name"), c.get("last_name")) if p) or c.get("contact_id", "?")

    def stale(c: dict[str, Any]) -> bool:
        try:
            return datetime.fromisoformat(c.get("last_updated") or "") < cutoff
        except ValueError:
            return True

    quality = {
        "contact_count": len(members),
        "missing_email": [name(c) for c in members if not c.get("email")],
        "missing_phone": [name(c) for c in members if not c.get("phone")],
        "missing_title": [name(c) for c in members if not c.get("title")],
        "single_source_only": [name(c) for c in members if len(c.get("sources") or []) == 1],
        "stale_over_90_days": [name(c) for c in members if stale(c)],
        "manually_edited": [
            name(c) for c in members
            if any((p or {}).get("source") == "manual" for p in (c.get("provenance") or {}).values())
        ],
        "not_yet_enriched": [name(c) for c in members if "explorium" not in (c.get("sources") or [])],
        "seniority_unknown": [name(c) for c in members if not c.get("seniority")],
    }
    tool_context.state.update({"ledger_quality": quality})
    return {"status": "OK", "flags": {k: len(v) for k, v in quality.items() if isinstance(v, list)}}
