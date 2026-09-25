#!/usr/bin/env python3
"""Push master-resolved fields back into Apollo -- the return leg of the exchange.

This is the only script in the repo that mutates a system outside this repo,
so it is off by default twice over: APOLLO_WRITEBACK_ENABLED must be true AND
--apply must be passed. Without both it prints the diff and changes nothing.

It pushes only fields where master disagrees with Apollo *and* master's value
came from a source Apollo does not have -- there is no point writing Apollo's
own value back to it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config, runlog
from crm.http import post_json, HttpError
from crm.master import load_master
from crm.schema import Contact, SOURCE_APOLLO

log = logging.getLogger("push_apollo")

#: Fields worth writing back. Email is excluded deliberately: Apollo is the
#: higher-trust source for it, so master should never be teaching Apollo an
#: email, and a wrong one would poison outreach.
WRITEBACK_FIELDS = ("title", "phone", "linkedin_url", "company_name", "company_domain")

APOLLO_FIELD_NAMES = {
    "title": "title",
    "phone": "direct_phone",
    "linkedin_url": "linkedin_url",
    "company_name": "organization_name",
    "company_domain": "website_url",
}


def pending_updates(contacts: list[Contact]) -> list[tuple[Contact, dict]]:
    """Find contacts where master knows something Apollo does not."""
    updates = []
    for contact in contacts:
        if not contact.apollo_contact_id:
            continue  # not an Apollo contact; nothing to update
        payload = {}
        for field_name in WRITEBACK_FIELDS:
            value = getattr(contact, field_name, None)
            if not value:
                continue
            prov = (contact.provenance or {}).get(field_name) or {}
            if prov.get("source") == SOURCE_APOLLO:
                continue  # Apollo already told us this
            payload[APOLLO_FIELD_NAMES[field_name]] = value
        if payload:
            updates.append((contact, payload))
    return updates


def apply_update(contact: Contact, payload: dict) -> None:
    post_json(
        f"{config.APOLLO_API_BASE}/contacts/{contact.apollo_contact_id}",
        payload,
        headers={"X-Api-Key": config.APOLLO_API_KEY, "Cache-Control": "no-cache"},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write to Apollo. Also requires APOLLO_WRITEBACK_ENABLED=true.",
    )
    parser.add_argument("--limit", type=int, default=0, help="cap updates (0 = all)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    updates = pending_updates(load_master())
    if args.limit:
        updates = updates[: args.limit]

    log.info("%s contacts have fields master could teach Apollo", len(updates))

    if not (args.apply and config.APOLLO_WRITEBACK_ENABLED):
        for contact, payload in updates[:50]:
            print(f"{contact.contact_id} ({contact.apollo_contact_id}): {json.dumps(payload)}")
        if len(updates) > 50:
            print(f"...and {len(updates) - 50} more")
        reason = (
            "--apply not passed"
            if not args.apply
            else "APOLLO_WRITEBACK_ENABLED is not true"
        )
        log.info("dry run (%s): nothing was written to Apollo", reason)
        return 0

    if not config.APOLLO_API_KEY:
        raise SystemExit("APOLLO_API_KEY is not set")

    failed = 0
    for contact, payload in updates:
        try:
            apply_update(contact, payload)
            log.info("updated %s", contact.apollo_contact_id)
        except HttpError as exc:
            failed += 1
            log.error("failed to update %s: %s", contact.apollo_contact_id, exc)

    log.info("wrote %s contacts, %s failures", len(updates) - failed, failed)
    # One line for the CRM page's Last runs strip. Writeback only updates
    # existing Apollo contacts, so it never creates and never holds.
    runlog.write_file(runlog.entry(
        "Apollo writeback", f"{len(updates) - failed} Apollo contacts updated, {failed} failed",
        0, len(updates) - failed, datetime.now(timezone.utc)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
