"""The evidence ledger: one schema for every research profile, and the checks that keep it honest.

The schema is `architecture/schemas/evidence-ledger.schema.json`, and it is the
only definition: the required fields per profile are read from it here, not
restated. Profiles (docs/research-profiles.md):

  full  legal, health, privacy, market sizing, or any claim that will be
        published or shown outside SMI (a proposal to a prospect included).
        Brief, source register, claim ledger and search log.
  lean  development research: a claim ledger plus sources only.

Integrity rules, in both profiles (a JSON Schema cannot state them):
  1. every claim cites only source ids that exist in the ledger;
  2. every quote has its locator (a `quote`, or an `excerpt` in quotation
     marks, needs a page, section, table, endpoint or figure);
  3. every source has an access date;
  4. a FACT rests on at least one source that was actually reviewed, not a
     search snippet; ids are unique; contradictions, supersessions and
     rechecks point at things that exist.

The ledger's objects are ADR-012's proposed shapes (`objects`), so a ledger can
feed the AI-Native Intelligence Core later without reshaping. It is a file:
nothing here writes to the CRM.

Pure and stdlib-only, like the rest of crm/.
"""

from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "architecture" / "schemas" / "evidence-ledger.schema.json"
PROFILES = ("full", "lean")
QUOTE_MARKS = ('"', "“", "‘", "'")


@lru_cache(maxsize=1)
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def profile_of(ledger: dict[str, Any]) -> str:
    """The ledger's profile. Absent means full: an unlabelled ledger gets the stricter reading."""
    return ledger.get("profile") or "full"


def required(profile: str) -> dict[str, list[str]]:
    """Required fields per part, for one profile, read from the schema."""
    s = schema()
    props = s["properties"]
    out = {"ledger": list(s["required"]),
           "sources": list(props["sources"]["items"]["required"]),
           "claims": list(props["claims"]["items"]["required"]),
           "brief": list(props["brief"]["required"]),
           "contradictions": list(props["contradictions"]["items"]["required"]),
           "search_log": list(props["search_log"]["items"]["required"])}
    if profile == "full":
        then = s["allOf"][0]["then"]
        out["ledger"] = list(then["required"])
        out["sources"] = list(then["properties"]["sources"]["items"]["required"])
        out["claims"] = list(then["properties"]["claims"]["items"]["required"])
    return out


def _pattern(ref: str) -> re.Pattern[str]:
    return re.compile(schema()["$defs"][ref]["pattern"])


def _is_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def _enum(part: str, field: str) -> list[str] | None:
    props = schema()["properties"][part]["items"]["properties"].get(field) or {}
    return props.get("enum")


def _missing(item: dict[str, Any], fields: list[str]) -> list[str]:
    return [f for f in fields if item.get(f) in (None, "", []) and not (f == "reviewed" and item.get(f) is False)]


def validate(ledger: dict[str, Any]) -> list[str]:
    """Every schema and integrity error, as readable lines. Empty means the ledger passes."""
    errors: list[str] = []
    if not isinstance(ledger, dict):
        return ["a ledger is a JSON object"]
    profile = profile_of(ledger)
    if profile not in PROFILES:
        return [f"profile {profile!r} not in {PROFILES}"]
    req = required(profile)
    for part in req["ledger"]:
        if part not in ledger:
            errors.append(f"{profile} profile: the ledger needs `{part}`")
    brief = ledger.get("brief")
    if isinstance(brief, dict):
        for f in _missing(brief, req["brief"]):
            errors.append(f"brief: missing {f}")
        if brief.get("date") and not _is_date(brief["date"]):
            errors.append("brief: date must be an ISO date")

    src_id, claim_id = _pattern("sourceId"), _pattern("claimId")
    sources = ledger.get("sources") or []
    claims = ledger.get("claims") or []
    by_src: dict[str, dict[str, Any]] = {}
    for s in sources:
        sid = s.get("id", "?")
        if not src_id.match(str(sid)):
            errors.append(f"source {sid}: id must look like SRC-001")
        if sid in by_src:
            errors.append(f"source {sid}: listed twice")
        by_src[sid] = s
        for f in _missing(s, req["sources"]):
            errors.append(f"source {sid}: missing {f}")
        if not s.get("accessed") or not _is_date(s["accessed"]):
            errors.append(f"source {sid}: needs an access date (ISO), the day the source was actually read")
        quote = (s.get("quote") or "").strip()
        excerpt = (s.get("excerpt") or "").strip()
        if (quote or excerpt.startswith(QUOTE_MARKS)) and not (s.get("locator") or "").strip():
            errors.append(f"source {sid}: a quote needs its locator (page, section, table, endpoint or figure)")
        if s.get("source_type") and s["source_type"] not in (_enum("sources", "source_type") or []):
            errors.append(f"source {sid}: source_type {s['source_type']!r} is not allowed")
        if "reviewed" in s and not isinstance(s["reviewed"], bool):
            errors.append(f"source {sid}: reviewed must be true or false")

    seen_claims: set[str] = set()
    for c in claims:
        cid = c.get("id", "?")
        if not claim_id.match(str(cid)):
            errors.append(f"claim {cid}: id must look like CLAIM-001")
        if cid in seen_claims:
            errors.append(f"claim {cid}: listed twice")
        seen_claims.add(cid)
        for f in _missing(c, req["claims"]):
            errors.append(f"claim {cid}: missing {f}")
        for field in ("status", "confidence", "evidence_type", "applies"):
            allowed = _enum("claims", field)
            if c.get(field) is not None and allowed and c[field] not in allowed:
                errors.append(f"claim {cid}: {field} {c[field]!r} not in {allowed}")
        cited = c.get("source_ids") or []
        for sid in cited:
            if sid not in by_src:
                errors.append(f"claim {cid}: cites {sid}, which is not in the source register")
        if c.get("status") == "FACT":
            if not cited:
                errors.append(f"claim {cid}: a FACT cites at least one source")
            elif not any(by_src.get(sid, {}).get("reviewed") is True for sid in cited):
                errors.append(f"claim {cid}: a FACT needs a reviewed source, not only a search snippet")
        if c.get("recheck_by") and not _is_date(c["recheck_by"]):
            errors.append(f"claim {cid}: recheck_by must be an ISO date")
    for c in claims:
        sup = c.get("superseded_by")
        if sup and sup not in seen_claims:
            errors.append(f"claim {c.get('id')}: superseded_by {sup} is not in the claim ledger")

    for x in ledger.get("contradictions") or []:
        xid = x.get("id", "?")
        for f in _missing(x, req["contradictions"]):
            errors.append(f"contradiction {xid}: missing {f}")
        for cid in x.get("claim_ids") or []:
            if cid not in seen_claims:
                errors.append(f"contradiction {xid}: names {cid}, which is not in the claim ledger")
        for sid in x.get("source_ids") or []:
            if sid not in by_src:
                errors.append(f"contradiction {xid}: names {sid}, which is not in the source register")
    if isinstance(brief, dict):
        for ch in brief.get("changes") or []:
            for cid in ch.get("claims_to_recheck") or []:
                if cid not in seen_claims:
                    errors.append(f"brief change: recheck names {cid}, which is not in the claim ledger")
    for i, e in enumerate(ledger.get("search_log") or [], 1):
        for f in _missing(e, req["search_log"]):
            errors.append(f"search_log entry {i}: missing {f}")
        if e.get("date") and not _is_date(e["date"]):
            errors.append(f"search_log entry {i}: date must be an ISO date")
    return errors


def load(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def objects(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """The ledger as ADR-012's proposed object types. A view, not a store."""
    out: list[dict[str, Any]] = []
    for s in ledger.get("sources") or []:
        out.append({"type": "Observation", "id": s["id"], "source": s.get("locator_url"), "observed_at": s.get("accessed")})
    for c in ledger.get("claims") or []:
        kind = "Claim" if c.get("status") == "FACT" else "Hypothesis"
        out.append({"type": kind, "id": c["id"], "status": c.get("status"), "confidence": c.get("confidence")})
        for sid in c.get("source_ids") or []:
            out.append({"type": "Evidence", "observation": sid, "claim": c["id"], "stance": "supports"})
        if c.get("superseded_by"):
            out.append({"type": "ProvenanceEdge", "from": c["id"], "to": c["superseded_by"], "relation": "superseded_by"})
    for x in ledger.get("contradictions") or []:
        out.append({"type": "Contradiction", "id": x["id"], "claims": list(x.get("claim_ids") or []),
                    "status": x.get("status")})
        for sid in x.get("source_ids") or []:
            for cid in x.get("claim_ids") or []:
                out.append({"type": "Evidence", "observation": sid, "claim": cid, "stance": "contradicts"})
    return out
