#!/usr/bin/env python3
"""Match the master roster to Explorium prospect ids and stage the result.

Match-only by decision D1 (25 Sep 2026): enrichment is bought from the Vibe
Prospecting balance through the Enrichment Broker (crm/broker.py), where
every paid call is estimated and logged as an enrichment job first. This
weekly REST step spends nothing: matching is free, and the prospect ids it
stages are identity keys the broker enriches against. `--enrich` restores
the paid REST call only with `--job` naming the approved enrichment job
that pays for it -- the day REST credits are bought.

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
from crm.broker import map_explorium
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


class CreditsExhausted(RuntimeError):
    """Explorium refused enrichment because the account has no credits left."""


def enrich(prospect_ids: list[str]) -> dict[str, dict]:
    """Fetch enrichment for resolved prospect ids. Returns prospect_id -> data."""
    if not prospect_ids:
        return {}
    try:
        data = post_json(
            f"{config.EXPLORIUM_API_BASE}/prospects/contacts_information/bulk_enrich",
            {"prospect_ids": prospect_ids},
            headers=explorium_headers(),
        )
    except HttpError as exc:
        if exc.status == 403 and "insufficient credits" in exc.body.lower():
            raise CreditsExhausted(exc.body) from exc
        raise
    out: dict[str, dict] = {}
    for entry in data.get("data") or []:
        pid = entry.get("prospect_id")
        if pid:
            out[pid] = entry.get("data") or entry
    return out


def matched_only(original: Contact, prospect_id: str) -> Contact:
    """The record we can still stage when matching worked but enrichment could
    not be paid for: identity for the merge to find it, plus the Explorium id
    so next week's run -- with credits -- enriches straight away.
    """
    return Contact(
        email=original.email,
        first_name=original.first_name,
        last_name=original.last_name,
        company_domain=original.company_domain,
        explorium_prospect_id=prospect_id,
    )


def to_contact(original: Contact, prospect_id: str, data: dict) -> Contact:
    """Build a sparse canonical record carrying only what Explorium asserted.

    Sparse on purpose: the merge treats an absent field as 'no opinion', so
    echoing back the Apollo values we sent would fabricate corroboration.
    The field mapping is the broker's (crm.broker.map_explorium), so a paid
    REST run and a Vibe Prospecting purchase land the same way.
    """
    return Contact(
        # Carry identity so the merge can match, but claim nothing new about it.
        email=original.email,
        first_name=original.first_name,
        last_name=original.last_name,
        company_domain=original.company_domain,
        explorium_prospect_id=prospect_id,
        **map_explorium(data),
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
    parser.add_argument("--limit", type=int, default=0, help="cap records matched (0 = all)")
    parser.add_argument("--enrich", action="store_true",
                        help="also call the paid REST enrichment (off by decision D1); needs --job")
    parser.add_argument("--job", default="", help="the approved enrichment job id that pays for --enrich")
    parser.add_argument("--out", type=Path, default=config.EXPLORIUM_STAGING)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.enrich and not args.job.strip():
        log.error("--enrich spends Explorium credits: name the approved enrichment job with --job. "
                  "Nothing is bought without a ledger entry (crm/broker.py).")
        return 2

    # Validate the credential before doing anything, even on an empty roster:
    # otherwise week one "succeeds" without ever proving the key works.
    explorium_headers()

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
    # Match-only unless a paid run was named; a paid run stops paying the
    # moment the account runs dry and keeps matching.
    credits_exhausted = False

    try:
        for batch in chunked(list(by_email.values()), config.EXPLORIUM_BATCH_SIZE):
            resolved = match_prospects(batch)
            log.info("matched %s/%s prospects", len(resolved), len(batch))
            if not args.enrich or credits_exhausted:
                # Matching is free; keep resolving ids so the whole roster is
                # linked, and skip the paid step.
                enriched.extend(matched_only(by_email[e], pid) for e, pid in resolved.items())
                continue
            try:
                payload = enrich(list(resolved.values()))
            except CreditsExhausted:
                credits_exhausted = True
                log.warning(
                    "Explorium account has no enrichment credits left. Staging "
                    "matched prospect ids only; enrichment fields will fill in "
                    "on the first run after credits are added."
                )
                enriched.extend(matched_only(by_email[e], pid) for e, pid in resolved.items())
                continue
            for email, pid in resolved.items():
                data = payload.get(pid)
                if data:
                    enriched.append(to_contact(by_email[email], pid, data))
                else:
                    enriched.append(matched_only(by_email[email], pid))
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
                "mode": "enrich" if args.enrich else "match_only",
                "job_id": args.job.strip() or None,
                "credits_exhausted": credits_exhausted if args.enrich else None,
                "count": len(enriched),
                "contacts": [c.to_dict() for c in enriched],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    log.info("staged %s %s contacts to %s", len(enriched), "enriched" if args.enrich else "matched", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
