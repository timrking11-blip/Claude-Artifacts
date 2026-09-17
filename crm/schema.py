"""The canonical CRM contact record.

Both sources normalize into this shape before anything is merged, so the merge
never has to know which system a field came from -- only how fresh it is and
how much that source is trusted for that field.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

SOURCE_APOLLO = "apollo"
SOURCE_EXPLORIUM = "explorium"
SOURCE_MANUAL = "manual"

#: Per-field source precedence. Higher wins when two sources disagree and
#: neither is meaningfully fresher. Manual edits made in the CRM artifact
#: always outrank both feeds -- a human who corrected a record should not have
#: that correction overwritten by the next weekly run.
FIELD_TRUST: dict[str, dict[str, int]] = {
    "email": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 20, SOURCE_EXPLORIUM: 10},
    "phone": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 15, SOURCE_EXPLORIUM: 15},
    "title": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 15, SOURCE_EXPLORIUM: 20},
    "company_name": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 15, SOURCE_EXPLORIUM: 20},
    "company_domain": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 20, SOURCE_EXPLORIUM: 20},
    "linkedin_url": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 20, SOURCE_EXPLORIUM: 15},
    "location": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 15, SOURCE_EXPLORIUM: 20},
    "seniority": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 15, SOURCE_EXPLORIUM: 20},
    "employee_count": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 10, SOURCE_EXPLORIUM: 25},
    "industry": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 10, SOURCE_EXPLORIUM: 25},
    "technologies": {SOURCE_MANUAL: 30, SOURCE_APOLLO: 15, SOURCE_EXPLORIUM: 25},
}

DEFAULT_TRUST = {SOURCE_MANUAL: 30, SOURCE_APOLLO: 15, SOURCE_EXPLORIUM: 15}

#: Fields whose values are set-valued and accumulate rather than replace --
#: each source only ever sees part of the stack, so the last writer must not win.
UNION_FIELDS = ("technologies",)

#: Fields the merge actually reconciles. Anything else rides along untouched.
MERGED_FIELDS = tuple(FIELD_TRUST.keys()) + ("first_name", "last_name")

#: Fields resolved one-value-wins by `resolve_field`. Union fields are excluded
#: because they have their own accumulate rule; running both would let the
#: scalar pass overwrite the value the union pass is meant to extend.
SCALAR_FIELDS = tuple(f for f in MERGED_FIELDS if f not in UNION_FIELDS)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    return value if "@" in value and "." in value.split("@")[-1] else None


def normalize_domain(value: str | None) -> str | None:
    """Strip scheme, www and path so apollo.io and https://www.apollo.io/x match."""
    if not value:
        return None
    value = value.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    value = value.split("/")[0].split("?")[0]
    return value or None


def normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def normalize_linkedin(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^([a-z]{2,3}\.)?linkedin\.com", "linkedin.com", value)
    value = value.rstrip("/")
    return value or None


@dataclass
class Provenance:
    """Where one field's current value came from, and when."""

    source: str
    observed_at: str
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Contact:
    """One canonical person record in the master database."""

    contact_id: str = ""
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    title: str | None = None
    seniority: str | None = None
    linkedin_url: str | None = None
    location: str | None = None

    company_name: str | None = None
    company_domain: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    technologies: list[str] = field(default_factory=list)

    # Foreign keys back into each system, so a writeback knows what to update.
    apollo_contact_id: str | None = None
    apollo_person_id: str | None = None
    explorium_prospect_id: str | None = None
    explorium_business_id: str | None = None

    sources: list[str] = field(default_factory=list)
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    first_seen: str = ""
    last_updated: str = ""

    def identity_keys(self) -> list[str]:
        """Keys this record can be matched on, strongest first.

        Email is the only key treated as globally unique. LinkedIn is close.
        Name+domain is a heuristic and deliberately last -- two different
        J. Smiths at the same company will collide, which the merge logs.
        """
        keys = []
        email = normalize_email(self.email)
        if email:
            keys.append(f"email:{email}")
        li = normalize_linkedin(self.linkedin_url)
        if li:
            keys.append(f"linkedin:{li}")
        domain = normalize_domain(self.company_domain)
        first = normalize_name(self.first_name)
        last = normalize_name(self.last_name)
        if domain and first and last:
            keys.append(f"name_domain:{first.lower()}|{last.lower()}|{domain}")
        return keys

    def ensure_id(self) -> str:
        """Derive a stable id from the strongest identity key available.

        Deriving rather than randomizing means the same person gets the same
        id on a rebuild from scratch, so the master file stays diffable.
        """
        if self.contact_id:
            return self.contact_id
        keys = self.identity_keys()
        basis = keys[0] if keys else f"anon:{self.first_name}|{self.last_name}|{utcnow()}"
        self.contact_id = "c_" + hashlib.sha256(basis.encode()).hexdigest()[:16]
        return self.contact_id

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["technologies"] = sorted(set(self.technologies or []))
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Contact":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def trust_for(field_name: str, source: str) -> int:
    return FIELD_TRUST.get(field_name, DEFAULT_TRUST).get(source, 0)
