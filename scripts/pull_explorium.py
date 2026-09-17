#!/usr/bin/env python3
"""Enrich the master roster against Explorium and stage the result.

Runs as the other half of the weekly exchange, in parallel with
pull_apollo.py. It reads the *previous* master as its input roster rather than
this week's Apollo staging, which is what lets the two jobs run concurrently:
neither waits on the other, and merge_master.py reconciles them afterwards.

The cost of that choice is that a contact added to Apollo this week is not
enriched until next week's run. That is a deliberate one-week lag traded for
parallelism; --roster apollo forces the serial behaviour instead.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config
from crm.http import post_json, HttpError
from crm.master import load_master
from crm.schema import Contact, SOURCE_EXPLORIUM, utcnow, normalize_email

log = logging.getLogger("pull_explorium")


def explorium_headers() -> dict[str, str]:
    if not config.EXPLORIUM_API_KEY:
        raise SystemExit(
            "EXPLORIUM_API_KEY is not set. In CI this comes from the repository "
            "secret of the same name; locally, export it before running."
        )
    return {"API_KEY": config.EXPLORIUM_API_KEY}


def load_roster(source: str) -> list[Contact]:
    if source == "apollo":
        if not config.APOLLO_STAGING.exists():
            raise SystemExit(
                f"--roster apollo needs {config.APOLLO_STAGING}, which does not "
                "exist. Run pull_apollo.py first, or use --roster master."
            )
        raw = json.loads(config.APOLLO_STAGING.read_text())
        return [Contact.from_dict(r) for r in raw.get("contacts", [])]
    return load_master()


def chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def match_prospects(batch: list[Contact]) -> dict[str, str]:
    """Resolve our contacts to Explorium prospect ids. Returns email -> id."""
    to_match = [
        {
            "email": normalize_email(c.email),
            "full_name": " ".join(p for p in (c.first_name, c.last_name) if p) or None,
            "company_name": c.company_name,
        }
        for c in batch
        if normalize_email(c.email)
    ]
    if not to_match:
        return {}

    data = post_json(
        f"{config.EXPLORIUM_API_BASE}/prospects/match",
        {"prospects_to_match": to_match},
        headers=explorium_headers(),
    )
    resolved: dict[str, str] = {}
    for entry in data.get("matched_prospects") or data.get("data") or []:
        email = normalize_email(
            (entry.get("input") or {}).get("email") or entry.get("email")
        )
        pid = entry.get("prospect_id")
        if email and pid:
            resolved[email] = pid
    return resolved


def enrich(prospect_ids: list[str]) -> dict[str, dict]:
    """Fetch enrichment for resolved prospect ids. Returns prospect_id -> data."""
    if not prospect_ids:
        return {}
    data = post_json(
        f"{config.EXPLORIUM_API_BASE}/prospects/contacts_information/bulk_enrich",
        {"prospect_ids": prospect_ids},
        headers=explorium_headers(),
    )
    out: dict[str, dict] = {}
    for entry in data.get("data") or []:
        pid = entry.get("prospect_id")
        if pid:
            out[pid] = entry.get("data") or entry
    return out


def to_contact(original: Contact, prospect_id: str, data: dict) -> Contact:
    """Build a sparse canonical record carrying only what Explorium asserted.

    Sparse on purpose: the merge treats an absent field as 'no opinion', so
    echoing back the Apollo values we sent would fabricate corroboration.
    """
    return Contact(
        # Carry identity so the merge can match, but claim nothing new about it.
        email=original.email,
        linkedin_url=data.get("linkedin") or data.get("linkedin_url"),
        first_name=original.first_name,
        last_name=original.last_name,
        company_domain=original.company_domain,
        phone=data.get("mobile_phone") or data.get("phone"),
        title=data.get("job_title") or data.get("title"),
        seniority=data.get("job_seniority_level") or data.get("seniority"),
        location=data.get("location") or data.get("country_name"),
        company_name=data.get("company_name"),
        industry=data.get("industry") or data.get("google_category"),
        employee_count=data.get("number_of_employees") or data.get("employee_count"),
        technologies=[t for t in (data.get("technologies") or []) if t],
        explorium_prospect_id=prospect_id,
        explorium_business_id=data.get("business_id"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roster",
        choices=("master", "apollo"),
        default="master",
        help="master (default, runs in parallel) or apollo (serial, needs this "
        "week's Apollo staging to exist first)",
    )
    parser.add_argument("--limit", type=int, default=0, help="cap records enriched (0 = all)")
    parser.add_argument("--out", type=Path, default=config.EXPLORIUM_STAGING)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    roster = load_roster(args.roster)
    if args.limit:
        roster = roster[: args.limit]

    if not roster:
        log.warning(
            "roster is empty -- nothing to enrich. On a first run this is "
            "expected: master fills up after the first Apollo pull and merge."
        )

    by_email = {normalize_email(c.email): c for c in roster if normalize_email(c.email)}
    enriched: list[Contact] = []

    try:
        for batch in chunked(list(by_email.values()), config.EXPLORIUM_BATCH_SIZE):
            resolved = match_prospects(batch)
            log.info("matched %s/%s prospects", len(resolved), len(batch))
            payload = enrich(list(resolved.values()))
            for email, pid in resolved.items():
                data = payload.get(pid)
                if data:
                    enriched.append(to_contact(by_email[email], pid, data))
    except HttpError as exc:
        log.error("Explorium enrichment failed: %s", exc)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "source": SOURCE_EXPLORIUM,
                "observed_at": utcnow(),
                "roster": args.roster,
                "count": len(enriched),
                "contacts": [c.to_dict() for c in enriched],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    log.info("staged %s enriched contacts to %s", len(enriched), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
