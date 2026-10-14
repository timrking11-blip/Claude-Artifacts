"""The Signal record (SPEC-002): one observed commercial event about one subject.

Specification: `architecture/specs/SPEC-002-signal-model.md`. Governing decision:
ADR-012 (Proposed), so this module is the executable shape of a proposed object,
not an accepted one. It has no store and no writer: nothing here reads or writes
the CRM. A producer (the Enrichment Broker, a research run, a ledger) builds a
Signal, calls `validate`, and keeps it wherever its own rules allow.

What a Signal holds, and what it does not:

  observation   kind, subject, source, source_ref, observed_at, hint, evidence.
                What a source reported, nothing more (INV-02).
  assessment    strength, confidence, expires_at. Optional, each a number or a
                date a policy can recompute.
  interpretation  optional, kept apart from the observation, and only with the
                producer that wrote it (model and prompt hash, or a rule and its
                version; INV-16). A Signal without one is complete.

The subject is a stored key, `org_id` or `master_id` (CLAUDE.md: nothing matches
by email or company name), so a Signal can never attach itself to a record by a
guess. The id is a hash of the observation, so the same event reported twice
yields the same id and a store can refuse the duplicate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

#: Signal kinds. The blueprint's SIGNAL row names funding, site and exec; Vibe
#: business events add hiring, launches and expansion. A new kind is a change to
#: SPEC-002, not a free-text value.
SIGNAL_KINDS = ("funding", "hiring", "exec_change", "site_visit", "product_launch", "expansion", "other")
#: Where a signal came from. A value outside this list is refused, not guessed.
SIGNAL_SOURCES = ("apollo", "vibe", "explorium", "crunchbase", "web", "gmail", "gcal", "manual")
#: The stored keys a Signal may name. Email and company name are never keys.
SUBJECT_TYPES = {"org": "org_id", "person": "master_id"}
#: A hint is a headline, like an activity row's text, never a page or a message body.
HINT_LIMIT = 140


@dataclass(frozen=True)
class Interpretation:
    """What a producer read into a signal. Never part of the observation."""

    text: str
    producer: str            # e.g. "claude-opus-5-5" or "rule:hiring-capacity"
    version: str             # prompt hash or rule version
    at: str                  # ISO 8601 with a time zone


@dataclass(frozen=True)
class Signal:
    id: str
    kind: str
    subject_type: str
    subject_id: str
    source: str
    source_ref: str
    observed_at: str
    hint: str = ""
    evidence: tuple[str, ...] = ()
    strength: float | None = None
    confidence: float | None = None
    expires_at: str | None = None
    interpretation: Interpretation | None = None
    recommended_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = list(self.evidence)
        return d

    def expired(self, at: str) -> bool:
        """True once `at` is on or after `expires_at`. A signal with no expiry never expires."""
        return self.expires_at is not None and _ts(at) >= _ts(self.expires_at)


def _ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"{value!r} has no time zone")
    return dt


def signal_id(kind: str, subject_type: str, subject_id: str, source: str, source_ref: str, observed_at: str) -> str:
    """The id is the observation: the same event from the same source always gets the same id."""
    blob = json.dumps([kind, subject_type, subject_id, source, source_ref, observed_at], separators=(",", ":"))
    return "sig_" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def make(kind: str, subject_type: str, subject_id: str, source: str, source_ref: str, observed_at: str,
         **optional: Any) -> Signal:
    """Build a Signal with its id. Raises ValueError on any shape `validate` would refuse."""
    interp = optional.pop("interpretation", None)
    if isinstance(interp, dict):
        interp = Interpretation(**interp)
    evidence = tuple(optional.pop("evidence", ()) or ())
    sig = Signal(id=signal_id(kind, subject_type, subject_id, source, source_ref, observed_at), kind=kind,
                 subject_type=subject_type, subject_id=subject_id, source=source, source_ref=source_ref,
                 observed_at=observed_at, evidence=evidence, interpretation=interp, **optional)
    errors = validate(sig)
    if errors:
        raise ValueError("; ".join(errors))
    return sig


def from_dict(d: dict[str, Any]) -> Signal:
    """Read a stored Signal back. Unknown keys are refused rather than dropped."""
    known = set(Signal.__dataclass_fields__)
    extra = set(d) - known
    if extra:
        raise ValueError(f"unknown signal fields {sorted(extra)}")
    d = dict(d)
    if isinstance(d.get("interpretation"), dict):
        d["interpretation"] = Interpretation(**d["interpretation"])
    d["evidence"] = tuple(d.get("evidence") or ())
    return Signal(**d)


def validate(sig: Signal) -> list[str]:
    """Every rule SPEC-002 states, as a list of errors. Empty means the record is well formed."""
    errors: list[str] = []
    if sig.kind not in SIGNAL_KINDS:
        errors.append(f"kind {sig.kind!r} not in {SIGNAL_KINDS}")
    if sig.source not in SIGNAL_SOURCES:
        errors.append(f"source {sig.source!r} not in {SIGNAL_SOURCES}")
    if sig.subject_type not in SUBJECT_TYPES:
        errors.append(f"subject_type {sig.subject_type!r} must be one of {sorted(SUBJECT_TYPES)}")
    if not sig.subject_id or "@" in sig.subject_id or " " in sig.subject_id.strip():
        errors.append("subject_id must be a stored key (org_id or master_id), never an email or a name")
    if not sig.source_ref:
        errors.append("source_ref is required: the vendor event id, message id or URL the signal came from")
    try:
        observed = _ts(sig.observed_at)
    except (ValueError, AttributeError) as exc:
        errors.append(f"observed_at: {exc}")
        observed = None
    if len(sig.hint) > HINT_LIMIT:
        errors.append(f"hint is {len(sig.hint)} characters; a hint is a headline of at most {HINT_LIMIT}")
    for name in ("strength", "confidence"):
        v = getattr(sig, name)
        if v is not None and not (isinstance(v, (int, float)) and 0 <= v <= 1):
            errors.append(f"{name} must be between 0 and 1")
    if sig.expires_at is not None:
        try:
            if observed is not None and _ts(sig.expires_at) <= observed:
                errors.append("expires_at must be after observed_at")
        except ValueError as exc:
            errors.append(f"expires_at: {exc}")
    if sig.recommended_action and sig.interpretation is None:
        errors.append("a recommended_action needs the interpretation that produced it")
    it = sig.interpretation
    if it is not None:
        if not (it.text and it.producer and it.version):
            errors.append("an interpretation needs text, producer and version (INV-16)")
        try:
            _ts(it.at)
        except (ValueError, AttributeError) as exc:
            errors.append(f"interpretation.at: {exc}")
    if observed is not None and sig.id != signal_id(sig.kind, sig.subject_type, sig.subject_id, sig.source,
                                                    sig.source_ref, sig.observed_at):
        errors.append("id does not match the observation it names")
    return errors
