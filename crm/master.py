"""Load, merge and persist the master contact database.

The merge is field-level, not record-level: a record is never wholesale
replaced by a newer one. Each field is resolved independently from whichever
source has the better claim to it, and the winning claim is recorded in
`provenance` so any value can be traced back to a source and a timestamp.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from typing import Any, Iterable

from crm import config
from crm.schema import (
    Contact,
    MERGED_FIELDS,
    SCALAR_FIELDS,
    UNION_FIELDS,
    Provenance,
    trust_for,
    utcnow,
    normalize_domain,
    normalize_email,
    normalize_linkedin,
    normalize_name,
)


class MergeReport:
    """What one merge run actually changed, for the changelog and for CI logs."""

    def __init__(self) -> None:
        self.created: list[str] = []
        self.updated: list[str] = []
        self.unchanged: list[str] = []
        self.field_changes: list[dict[str, Any]] = []
        self.ambiguous_matches: list[dict[str, Any]] = []
        self.conflicts_held: list[dict[str, Any]] = []

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated)

    def summary(self) -> str:
        return (
            f"{len(self.created)} created, {len(self.updated)} updated, "
            f"{len(self.unchanged)} unchanged, "
            f"{len(self.field_changes)} field changes, "
            f"{len(self.conflicts_held)} conflicts held, "
            f"{len(self.ambiguous_matches)} ambiguous matches"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged_count": len(self.unchanged),
            "field_changes": self.field_changes,
            "ambiguous_matches": self.ambiguous_matches,
            "conflicts_held": self.conflicts_held,
        }


def load_master(path=None) -> list[Contact]:
    path = path or config.MASTER_CONTACTS
    if not path.exists():
        return []
    raw = json.loads(path.read_text() or "{}")
    return [Contact.from_dict(r) for r in raw.get("contacts", [])]


def save_master(contacts: list[Contact], path=None) -> None:
    """Write the master file deterministically so git diffs stay readable."""
    path = path or config.MASTER_CONTACTS
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at": utcnow(),
        "count": len(contacts),
        "contacts": [c.to_dict() for c in sorted(contacts, key=lambda x: x.contact_id)],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def build_index(contacts: Iterable[Contact]) -> dict[str, Contact]:
    """Map every identity key a record answers to onto that record."""
    index: dict[str, Contact] = {}
    for c in contacts:
        for key in c.identity_keys():
            index.setdefault(key, c)
    return index


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _normalized(field_name: str, value: Any) -> Any:
    if _is_empty(value):
        return None
    if field_name == "email":
        return normalize_email(value)
    if field_name == "company_domain":
        return normalize_domain(value)
    if field_name == "linkedin_url":
        return normalize_linkedin(value)
    if field_name in ("first_name", "last_name", "company_name", "title", "location"):
        return normalize_name(value)
    return value


def resolve_field(
    field_name: str,
    current_value: Any,
    current_prov: dict[str, Any] | None,
    incoming_value: Any,
    incoming_prov: Provenance,
) -> tuple[Any, dict[str, Any] | None, str]:
    """Decide one field. Returns (value, provenance, reason).

    Rules, in order:
      1. An empty incoming value never overwrites a populated one.
      2. An empty current value is filled by anything.
      3. A higher-trust source wins.
      4. At equal trust, a materially fresher observation (>7 days) wins.
      5. Otherwise the incumbent holds and the disagreement is recorded.
    """
    incoming_value = _normalized(field_name, incoming_value)
    current_norm = _normalized(field_name, current_value)

    if incoming_value is None:
        return current_value, current_prov, "incoming_empty"

    if current_norm is None:
        return incoming_value, incoming_prov.to_dict(), "filled_empty"

    if current_norm == incoming_value:
        # Same value: refresh the timestamp so staleness stays honest, but
        # credit stays with the source that first asserted it. Re-crediting
        # would let an identity field carried along for matching look like a
        # new claim, and the writeback would then push Apollo its own data.
        cur_at = _parse_ts((current_prov or {}).get("observed_at"))
        inc_at = _parse_ts(incoming_prov.observed_at)
        if cur_at and inc_at and inc_at > cur_at:
            refreshed = dict(current_prov or {})
            refreshed["observed_at"] = incoming_prov.observed_at
            return current_value, refreshed, "reaffirmed"
        return current_value, current_prov, "unchanged"

    cur_source = (current_prov or {}).get("source", "")
    cur_trust = trust_for(field_name, cur_source)
    inc_trust = trust_for(field_name, incoming_prov.source)

    if inc_trust > cur_trust:
        return incoming_value, incoming_prov.to_dict(), "higher_trust"
    if inc_trust < cur_trust:
        return current_value, current_prov, "lower_trust_held"

    cur_at = _parse_ts((current_prov or {}).get("observed_at"))
    inc_at = _parse_ts(incoming_prov.observed_at)
    if cur_at and inc_at and (inc_at - cur_at).days > 7:
        return incoming_value, incoming_prov.to_dict(), "fresher"

    return current_value, current_prov, "conflict_held"


def merge_contact(
    existing: Contact, incoming: Contact, source: str, observed_at: str, report: MergeReport
) -> Contact:
    merged = replace(existing)
    merged.provenance = dict(existing.provenance or {})
    touched = False

    for field_name in SCALAR_FIELDS:
        incoming_value = getattr(incoming, field_name, None)
        value, prov, reason = resolve_field(
            field_name,
            getattr(existing, field_name, None),
            (existing.provenance or {}).get(field_name),
            incoming_value,
            Provenance(source=source, observed_at=observed_at),
        )
        if reason in ("filled_empty", "higher_trust", "fresher"):
            report.field_changes.append(
                {
                    "contact_id": existing.contact_id,
                    "field": field_name,
                    "from": getattr(existing, field_name, None),
                    "to": value,
                    "source": source,
                    "reason": reason,
                }
            )
            touched = True
        elif reason == "conflict_held":
            report.conflicts_held.append(
                {
                    "contact_id": existing.contact_id,
                    "field": field_name,
                    "kept": getattr(existing, field_name, None),
                    "rejected": _normalized(field_name, incoming_value),
                    "source": source,
                }
            )
        setattr(merged, field_name, value)
        if prov is not None:
            merged.provenance[field_name] = prov

    # Union fields accumulate rather than replace -- each source sees part of
    # the stack, so taking the newer value alone would quietly lose the rest.
    for field_name in UNION_FIELDS:
        incoming_values = getattr(incoming, field_name, None) or []
        if not incoming_values:
            continue
        before = set(getattr(merged, field_name, None) or [])
        after = before | set(incoming_values)
        if after != before:
            setattr(merged, field_name, sorted(after))
            merged.provenance[field_name] = Provenance(
                source=source, observed_at=observed_at
            ).to_dict()
            report.field_changes.append(
                {
                    "contact_id": existing.contact_id,
                    "field": field_name,
                    "from": sorted(before),
                    "to": sorted(after),
                    "source": source,
                    "reason": "union",
                }
            )
            touched = True

    # Foreign keys are additive: learning an Explorium id never drops the Apollo one.
    for fk in (
        "apollo_contact_id",
        "apollo_person_id",
        "explorium_prospect_id",
        "explorium_business_id",
    ):
        incoming_fk = getattr(incoming, fk, None)
        if incoming_fk and not getattr(merged, fk, None):
            setattr(merged, fk, incoming_fk)
            touched = True

    if source not in merged.sources:
        merged.sources = sorted(set(merged.sources) | {source})
        touched = True

    if touched:
        merged.last_updated = observed_at
        report.updated.append(merged.contact_id)
    else:
        report.unchanged.append(merged.contact_id)

    return merged


def merge_all(
    master: list[Contact], incoming: list[Contact], source: str, observed_at: str | None = None
) -> tuple[list[Contact], MergeReport]:
    """Fold one source's records into master. Safe to run repeatedly."""
    observed_at = observed_at or utcnow()
    report = MergeReport()
    by_id = {c.ensure_id(): c for c in master}
    index = build_index(by_id.values())

    for record in incoming:
        keys = record.identity_keys()
        matches = {index[k].contact_id for k in keys if k in index}

        if len(matches) > 1:
            # The same incoming record points at two master records. Merging
            # them here would silently fuse two people, so log and take the
            # strongest key's match only.
            report.ambiguous_matches.append(
                {"keys": keys, "candidates": sorted(matches), "source": source}
            )

        target = next((index[k] for k in keys if k in index), None)

        if target is None:
            record.ensure_id()
            record.sources = [source]
            record.first_seen = observed_at
            record.last_updated = observed_at
            record.provenance = {
                f: Provenance(source=source, observed_at=observed_at).to_dict()
                for f in MERGED_FIELDS
                if not _is_empty(getattr(record, f, None))
            }
            by_id[record.contact_id] = record
            for key in record.identity_keys():
                index.setdefault(key, record)
            report.created.append(record.contact_id)
        else:
            merged = merge_contact(target, record, source, observed_at, report)
            by_id[merged.contact_id] = merged
            # Re-index: the merge may have added an email the record lacked before.
            for key in merged.identity_keys():
                index.setdefault(key, merged)

    return list(by_id.values()), report
