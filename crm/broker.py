"""The Enrichment Broker (architecture blueprint, tool T1): nothing is bought without a ledger entry.

  1. Identity match -- free (Apollo people search, org lookup, Vibe match); writes vendor ids.
  2. Budget check   -- the credit ledger (CRM `meta/credits`) per provider, the
                       vendor's own estimate, and a floor per provider. Work that
                       would go below the floor is queued with the sentinel
                       PENDING_BUDGET instead of failing silently.
  3. Enrich by field owner -- email from Apollo; firmographics and tech from
                       Explorium (bought through Vibe Prospecting); title and
                       seniority from LinkedIn. A vendor that does not own a
                       field may fill it when it is empty, never overwrite it.
  4. Merge by trust order -- crm.master.resolve_field, unchanged: empty never
                       overwrites, manual outranks feeds, more than 7 days
                       fresher wins at equal trust, a disagreement is held.
  5. Pinned write   -- the push scripts' batch files, if_version from the dump,
                       plus provenance and an enrichment-job row.

Pure planning, like the rest of crm/: no network, no credentials. A Claude
session calls the vendor tools and hands their results here; the ledger and
job rows it plans are written to the CRM with ArtifactData, pinned.

The CRM keeps two things for this module:
  meta/credits  {providers: {<provider>: {unit, cycle, limit, used, balance,
                 floor, read_at, source}}, updated_at}
  jobs/<id>     one ENRICHMENT_JOB row per paid operation, written before it runs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable

from .schema import FIELD_TRUST, SOURCE_APOLLO, SOURCE_EXPLORIUM, SOURCE_MANUAL, Contact

#: The sentinel a field or a job carries when its enrichment waits for budget (contract C6).
PENDING_BUDGET = "pending_budget"
#: Vibe Prospecting sells Explorium's data; values bought there are attributed to Explorium.
PROVIDER_SOURCE = {"apollo": SOURCE_APOLLO, "vibe": SOURCE_EXPLORIUM, "explorium_rest": SOURCE_EXPLORIUM}

JOB_STATUSES = ("estimated", "approved", "done", "queued", "refused")


def field_owner(field_name: str) -> str | None:
    """The one feed that owns a field: the highest-trust non-manual source, if unique.

    Derived from crm.schema.FIELD_TRUST so the broker and the weekly merge can
    never disagree. A tie (phone, company domain, location) means no single
    owner: every vendor may then only fill the field while it is empty.
    """
    weights = {s: w for s, w in FIELD_TRUST.get(field_name, {}).items() if s != SOURCE_MANUAL}
    if not weights:
        return None
    top = max(weights.values())
    owners = [s for s, w in weights.items() if w == top]
    return owners[0] if len(owners) == 1 else None


def _empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == 0


def owned_fields(rec: Contact, incoming: dict[str, Any], source: str) -> dict[str, Any]:
    """The part of a vendor's answer it may write: fields it owns, or fields still empty."""
    out = {}
    for name, value in incoming.items():
        if _empty(value) or name not in FIELD_TRUST:
            continue
        if field_owner(name) == source or _empty(getattr(rec, name, None)):
            out[name] = value
    return out


#: Explorium's field names (REST and Vibe Prospecting) -> the master's.
EXPLORIUM_FIELDS = (
    ("linkedin_url", ("linkedin", "linkedin_url")),
    ("phone", ("mobile_phone", "phone")),
    ("title", ("job_title", "title")),
    ("seniority", ("job_seniority_level", "seniority")),
    ("location", ("location", "country_name")),
    ("company_name", ("company_name",)),
    ("industry", ("industry", "google_category")),
    ("employee_count", ("number_of_employees", "employee_count")),
)


def map_explorium(data: dict[str, Any]) -> dict[str, Any]:
    """A sparse field dict of what Explorium asserted, in the master's field names."""
    out: dict[str, Any] = {}
    for name, keys in EXPLORIUM_FIELDS:
        value = next((data.get(k) for k in keys if not _empty(data.get(k))), None)
        if value is not None:
            out[name] = value
    tech = [t for t in (data.get("technologies") or []) if t]
    if tech:
        out["technologies"] = tech
    if data.get("business_id"):
        out["explorium_business_id"] = data["business_id"]
    return out


# ---------- the credit ledger ------------------------------------------------------

@dataclass
class Budget:
    ok: bool
    headroom: int | None       # credits left above the floor after this spend
    reason: str


def remaining(ledger: dict[str, Any], provider: str) -> int | None:
    """Credits left for a provider this cycle, or None when the ledger has no reading."""
    p = (ledger.get("providers") or {}).get(provider) or {}
    if isinstance(p.get("balance"), (int, float)):
        return int(p["balance"])
    if isinstance(p.get("limit"), (int, float)) and isinstance(p.get("used"), (int, float)):
        return int(p["limit"] - p["used"])
    return None


def budget_check(ledger: dict[str, Any], provider: str, est_credits: int) -> Budget:
    """May this spend go ahead? Fails closed on anything unknown.

    No reading, no floor, or no estimate means no: an unset floor is the
    owner's to set, never a default here.
    """
    p = (ledger.get("providers") or {}).get(provider) or {}
    left = remaining(ledger, provider)
    floor = p.get("floor")
    if left is None:
        return Budget(False, None, f"no {provider} balance on the ledger; read it before spending")
    if not isinstance(floor, (int, float)):
        return Budget(False, None, f"no floor set for {provider}; the owner sets it")
    if not isinstance(est_credits, (int, float)) or est_credits < 0:
        return Budget(False, None, "no cost estimate; run the vendor's free estimate first")
    headroom = int(left - est_credits - floor)
    if headroom < 0:
        return Budget(False, headroom, f"{provider}: {left} left, floor {int(floor)}, this needs {int(est_credits)}")
    return Budget(True, headroom, f"{provider}: {left} left, floor {int(floor)}, {headroom} spare after this")


def record_spend(ledger: dict[str, Any], provider: str, spent: int, now: str) -> dict[str, Any]:
    """The ledger after a settled spend. Pure: returns a new dict."""
    providers = {k: dict(v) for k, v in (ledger.get("providers") or {}).items()}
    p = providers.setdefault(provider, {})
    if isinstance(p.get("balance"), (int, float)):
        p["balance"] = int(p["balance"] - spent)
    else:
        p["used"] = int((p.get("used") or 0) + spent)
    p["read_at"] = now
    p["source"] = "settled spend"
    return {**ledger, "providers": providers, "updated_at": now}


# ---------- enrichment jobs ----------------------------------------------------------

def job_id(provider: str, operation: str, targets: Iterable[str], at: str) -> str:
    digest = hashlib.sha256("|".join(sorted(targets)).encode()).hexdigest()[:8]
    return f"job_{at[:10].replace('-', '')}_{provider}_{operation.replace('-', '_')}_{digest}"


def new_job(provider: str, operation: str, targets: list[str], est_credits: int | None, at: str, *,
            run_id: str | None = None, note: str = "") -> dict[str, Any]:
    """An ENRICHMENT_JOB row, written before anything is bought. Status `estimated`."""
    return {
        "job_id": job_id(provider, operation, targets, at), "provider": provider, "operation": operation,
        "target_count": len(targets), "targets": sorted(targets), "est_credits": est_credits, "spent": None,
        "status": "estimated", "run_id": run_id, "approved_by": None, "approved_at": None,
        "dataset_id": None, "at": at, "note": note,
    }


def approve(job: dict[str, Any], ledger: dict[str, Any], by: str, at: str) -> dict[str, Any]:
    """Approve a job only if the owner said go and the budget allows it; otherwise queue it."""
    check = budget_check(ledger, job["provider"], job.get("est_credits"))
    if not check.ok:
        return {**job, "status": "queued", "queued_reason": check.reason, "sentinel": PENDING_BUDGET}
    return {**job, "status": "approved", "approved_by": by, "approved_at": at, "budget": check.reason}


def settle(job: dict[str, Any], spent: int, at: str, dataset_id: str | None = None) -> dict[str, Any]:
    if job.get("status") != "approved":
        raise ValueError(f"job {job.get('job_id')} is {job.get('status')!r}, not approved; nothing may be settled")
    return {**job, "status": "done", "spent": int(spent), "settled_at": at, "dataset_id": dataset_id}
