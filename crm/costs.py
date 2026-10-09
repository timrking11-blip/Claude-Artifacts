"""Cost basis (ADR-008): the dated price table, API-list estimates, and the composition cap.

The prices live in architecture/architecture-manifest.yaml (`cost_basis`),
read from Anthropic's official pricing pages on the date it gives. An
estimate here is tokens times list price: what the work would cost billed
at API rates. Sessions and routines bill against the owner's plan first, so
for them this is an upper bound, not an invoice. Actual spend is not kept in
this public repository.

The composition soft cap: the account composition run (the one proposal
process) may run COMPOSITION_MONTHLY_CAP times per calendar month in
MONTH_TZ. The next run holds until the owner confirms it on the CRM page.

  Counted from two places, so a run prepared here and a run recorded only
  in the CRM both count:
    - data/runs/<run_id>/manifest.json, dated by run.composed_at (else the
      date in the run id, else counted in the current month);
    - the CRM runlog's applied "Composition run" entries, keyed by their
      run_id (else a run id in the note or detail, else the entry id).
  A retried run id counts once, and re-preparing a counted run is never held.
  Held cap entries ("Composition cap") are not runs and do not count.

  Limits: counting is not atomic. Two sessions preparing at the same moment
  can both see 4 and both proceed, and a run whose CRM line is not yet in
  the dump is missed. This is a soft cap (GAP-016).

  A confirmation is a runlog entry the owner confirmed on the CRM page,
  checked structurally (crm.runlog.confirmed). The CLI flag that names it is
  a reference, never an approval in itself, and the check does not
  authenticate who confirmed.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from . import config, runlog

COMPOSITION_MONTHLY_CAP = 5
MONTH_TZ = "America/New_York"
COMPOSITION_RUN = "Composition run"
CAP_RUN = "Composition cap"
MANIFEST = config.REPO_ROOT / "architecture" / "architecture-manifest.yaml"
PRICE_FIELDS = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")

CAP_OK = "ok"
CAP_RETRY = "retry"
CAP_HELD = "held"
CAP_CONFIRMED = "confirmed"

_RUN_ID = re.compile(r"\brun_[A-Za-z0-9_]+")
_RUN_DATE = re.compile(r"^run_(\d{8})")


class CapError(ValueError):
    """A --cap-confirmation that does not name a confirmed cap entry for this run."""


# ------------------------------------------------------------ price table ----

def load_manifest(path: Path | None = None) -> dict[str, Any]:
    import yaml  # only the report and the validator need it
    return yaml.safe_load((path or MANIFEST).read_text())


def prices(manifest: dict[str, Any]) -> dict[str, dict[str, float]]:
    return manifest["cost_basis"]["usd_per_mtok"]


def estimate_usd(model: str, usage: dict[str, int], table: dict[str, dict[str, float]], *,
                 batch: bool = False) -> float:
    """API list-price estimate for one model's token usage. Unknown fields are refused."""
    if model not in table:
        raise KeyError(f"no list price for {model!r}; add it to cost_basis with its source and date")
    unknown = set(usage) - set(PRICE_FIELDS)
    if unknown:
        raise ValueError(f"unknown usage fields {sorted(unknown)}; use {PRICE_FIELDS}")
    rate = table[model]
    total = sum(usage.get(f, 0) * rate[f] for f in PRICE_FIELDS) / 1_000_000
    return round(total * (0.5 if batch else 1.0), 6)


# --------------------------------------------------------- composition cap ----

def month_of(ts: datetime) -> str:
    """The calendar month, in MONTH_TZ, that a moment falls in: 'YYYY-MM'."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(ZoneInfo(MONTH_TZ)).strftime("%Y-%m")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _run_dir_time(run_dir: Path) -> datetime | None:
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text())
    except (OSError, ValueError):
        manifest = {}
    ts = _parse(((manifest.get("run") or {}).get("composed_at")))
    if ts:
        return ts
    m = _RUN_DATE.match(run_dir.name)
    if m:
        # The id carries a date but no time: noon in MONTH_TZ keeps it in its own month.
        return datetime.strptime(m.group(1), "%Y%m%d").replace(hour=12, tzinfo=ZoneInfo(MONTH_TZ))
    return None


def _runlog_key(doc: dict[str, Any]) -> str:
    if doc.get("run_id"):
        return str(doc["run_id"])
    for text in (doc.get("note"), doc.get("detail")):
        m = _RUN_ID.search(text or "")
        if m:
            return m.group(0)
    return str(doc.get("id"))


def counted_runs(now: datetime, runs_dir: Path | None, runlog_docs: Iterable[dict[str, Any]] = ()) -> dict[str, str]:
    """Composition runs in now's month: {run key: where it was seen}."""
    month = month_of(now)
    seen: dict[str, str] = {}
    if runs_dir and runs_dir.exists():
        for d in sorted(p for p in runs_dir.iterdir() if p.is_dir() and (p / "manifest.json").exists()):
            ts = _run_dir_time(d)
            if ts is None or month_of(ts) == month:
                seen.setdefault(d.name, "data/runs" if ts else "data/runs (undated, counted)")
    for doc in runlog_docs:
        doc = doc.get("data", doc)
        if doc.get("run") != COMPOSITION_RUN or doc.get("status") != runlog.STATUS_APPLIED:
            continue
        ts = _parse(doc.get("at"))
        if ts is None or month_of(ts) == month:
            seen.setdefault(_runlog_key(doc), "CRM runlog")
    return seen


def cap_entry(run_id: str, count: int, now: datetime, cap: int = COMPOSITION_MONTHLY_CAP) -> dict[str, Any]:
    """The held runlog entry the owner confirms on the CRM page to allow one more run."""
    doc = runlog.entry(CAP_RUN, f"{run_id} would be run {count + 1} this month (cap {cap}, ADR-008)",
                       0, 0, now, status=runlog.STATUS_HELD,
                       check=f"open the Intake page and confirm {run_id} is a new account request, not a re-run "
                             f"of one already composed this month",
                       on_confirm=f"re-run prepare for {run_id} with --cap-confirmation <this entry id>")
    doc["run_id"] = run_id
    doc["line"] = f"{CAP_RUN} · {doc['detail']} · HELD (over the monthly cap)"
    return doc


def cap_check(run_id: str, now: datetime, runs_dir: Path | None, runlog_docs: Iterable[dict[str, Any]] = (),
              confirmation: str | None = None, cap: int = COMPOSITION_MONTHLY_CAP) -> dict[str, Any]:
    """Whether this run may start. Raises CapError on a confirmation that does not hold up."""
    docs = [d.get("data", d) for d in runlog_docs]
    seen = counted_runs(now, runs_dir, docs)
    others = sorted(k for k in seen if k != run_id)
    out = {"run_id": run_id, "month": month_of(now), "timezone": MONTH_TZ, "cap": cap,
           "count": len(others), "counted": others}
    if run_id in seen:
        return {**out, "status": CAP_RETRY}
    if len(others) < cap:
        return {**out, "status": CAP_OK}
    if not confirmation:
        return {**out, "status": CAP_HELD, "entry": cap_entry(run_id, len(others), now, cap)}
    doc = next((d for d in docs if d.get("id") == confirmation), None)
    if doc is None:
        raise CapError(f"{confirmation} is not in the CRM runlog dump; confirm the held entry on the CRM page first")
    if doc.get("run") != CAP_RUN or doc.get("run_id") != run_id:
        raise CapError(f"{confirmation} is not the cap entry for {run_id}")
    if not runlog.confirmed(doc):
        raise CapError(f"{confirmation} is not confirmed on the CRM page with a written check")
    if month_of(_parse(doc.get("at")) or now) != month_of(now):
        raise CapError(f"{confirmation} was held in another month; a new month needs a new confirmation")
    return {**out, "status": CAP_CONFIRMED, "confirmation": confirmation,
            "confirmed_at": doc.get("confirmed_at"), "confirm_check": doc.get("confirm_check")}
