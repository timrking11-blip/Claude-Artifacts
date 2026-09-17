#!/usr/bin/env python3
"""Pull this team's Apollo contacts and stage them in canonical form.

Runs as one half of the weekly exchange, in parallel with pull_explorium.py.
Writes only to data/staging/apollo.json -- it never touches master, so a bad
run can be thrown away by deleting one file.
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
from crm.schema import Contact, SOURCE_APOLLO, utcnow

log = logging.getLogger("pull_apollo")


def apollo_headers() -> dict[str, str]:
    if not config.APOLLO_API_KEY:
        raise SystemExit(
            "APOLLO_API_KEY is not set. In CI this comes from the repository "
            "secret of the same name; locally, export it before running."
        )
    return {"X-Api-Key": config.APOLLO_API_KEY, "Cache-Control": "no-cache"}


def to_contact(record: dict) -> Contact:
    """Map one Apollo contact onto the canonical record.

    Apollo nests the employer under `organization` for contacts and under
    `account` for saved accounts; both appear in practice, so try each.
    """
    org = record.get("organization") or record.get("account") or {}
    return Contact(
        first_name=record.get("first_name"),
        last_name=record.get("last_name"),
        email=record.get("email"),
        phone=(
            record.get("sanitized_phone")
            or (record.get("phone_numbers") or [{}])[0].get("sanitized_number")
        ),
        title=record.get("title"),
        seniority=record.get("seniority"),
        linkedin_url=record.get("linkedin_url"),
        location=", ".join(
            p for p in (record.get("city"), record.get("state"), record.get("country")) if p
        )
        or None,
        company_name=org.get("name"),
        company_domain=org.get("primary_domain") or org.get("domain") or org.get("website_url"),
        industry=org.get("industry"),
        employee_count=org.get("estimated_num_employees"),
        technologies=[t for t in (org.get("technology_names") or []) if t],
        apollo_contact_id=record.get("id"),
        apollo_person_id=record.get("person_id") or record.get("contact_id"),
    )


def fetch_page(page: int, list_ids: list[str] | None) -> dict:
    payload: dict = {"page": page, "per_page": config.APOLLO_PAGE_SIZE}
    if list_ids:
        payload["contact_label_ids"] = list_ids
    return post_json(
        f"{config.APOLLO_API_BASE}/contacts/search", payload, headers=apollo_headers()
    )


def pull(list_ids: list[str] | None, max_pages: int) -> list[Contact]:
    contacts: list[Contact] = []
    page = 1
    while page <= max_pages:
        log.info("fetching Apollo contacts page %s", page)
        data = fetch_page(page, list_ids)
        batch = data.get("contacts") or data.get("people") or []
        if not batch:
            break
        contacts.extend(to_contact(r) for r in batch)

        pagination = data.get("pagination") or {}
        total_pages = pagination.get("total_pages")
        if total_pages and page >= total_pages:
            break
        page += 1
    else:
        log.warning(
            "stopped at the APOLLO_MAX_PAGES cap (%s); there may be more contacts. "
            "Raise the cap or narrow the query.",
            max_pages,
        )
    return contacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-id",
        action="append",
        dest="list_ids",
        help="Apollo list (label) id to restrict the pull to. Repeatable.",
    )
    parser.add_argument("--max-pages", type=int, default=config.APOLLO_MAX_PAGES)
    parser.add_argument(
        "--out", type=Path, default=config.APOLLO_STAGING, help="staging file to write"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        contacts = pull(args.list_ids, args.max_pages)
    except HttpError as exc:
        log.error("Apollo pull failed: %s", exc)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "source": SOURCE_APOLLO,
                "observed_at": utcnow(),
                "count": len(contacts),
                "contacts": [c.to_dict() for c in contacts],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    log.info("staged %s Apollo contacts to %s", len(contacts), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
