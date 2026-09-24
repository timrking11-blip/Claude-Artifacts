"""The note to the founder: a short cover note addressed to the prospect.

At a small startup the person who posts the request is the founder, so the
intake form's requester and the founder are the same person. This module
drafts the note that goes to them with the proposal. It is built only from
things the founder should hear: what we could not find about their company
(so they can fill the gap), and any scope limit or judgement call the
composer phrased for them (`founder_lines`). Internal review items (CRM
matches, data-source plumbing, sync timing) never appear here; those stay in
crm/review.py.

Deterministic and tested in tests/test_note_to_founder.py.
"""

from __future__ import annotations

import re
from typing import Any

from .review import REQUEST_MONEY

MAX_WORDS = 170
_MONEY = re.compile(r"(\$\s?\d|\b\d[\d,]*\s?(?:USD|dollars)\b|\bper\s+(?:hour|day|month)\b)", re.I)
_PREPARED_BY = re.compile(r"^\s*Prepared by\s+(.+?)\s*$", re.I | re.M)


def founder_of(manifest: dict[str, Any]) -> dict[str, Any]:
    """The founder is the requester: {name, linkedin_url} from the intake form."""
    req = manifest.get("request") or {}
    person = req.get("founder") or req.get("requester") or {}
    return {"name": (person.get("name") or "").strip() or None,
            "linkedin_url": (person.get("linkedin_url") or "").strip() or None}


def first_name(name: str | None) -> str | None:
    parts = (name or "").split()
    return parts[0] if parts else None


def brand_from(proposal_md: str, default: str = "Strategic Marketing Insights") -> str:
    m = _PREPARED_BY.search(proposal_md or "")
    return m.group(1).strip() if m else default


def draft(manifest: dict[str, Any], company: str | None, nothing_found: bool,
          founder_lines: list[str], proposal_md: str, sender: str = "Tim") -> str:
    """The cover note, as plain text. Raises ValueError if a founder line mentions money."""
    founder = founder_of(manifest)
    who = first_name(founder["name"])
    name = company or "your company"
    request_text = ((manifest.get("request") or {}).get("text") or "").strip()

    lines = [f"{who} —" if who else "Hello —", ""]
    if request_text:
        lines.append(f"Thank you for the request about {name}. The prequalification proposal below is our "
                     "first read of what you asked for, before any scoping call.")
    else:
        lines.append(f"Following our LinkedIn contact, the prequalification proposal below is our first read "
                     f"of where we could help {name}.")
    if nothing_found:
        lines.append(f"We could not find public information about {name} beyond your own description, so the "
                     "proposal works from that. Anything you can share before we talk (a deck, a product "
                     "walkthrough, a site we can open) will sharpen it.")
    if REQUEST_MONEY.search(request_text):
        lines.append("On pricing: we scope before we quote, so there are no fees in this draft.")
    for extra in founder_lines:
        extra = (extra or "").strip()
        if not extra:
            continue
        if _MONEY.search(extra):
            raise ValueError(f"founder line mentions money: {extra!r}")
        lines.append(extra if extra.endswith((".", "?", "!")) else extra + ".")
    lines.append("If the framing looks right, a 30-minute call is the next step.")
    lines += ["", sender, brand_from(proposal_md)]
    text = "\n".join(lines[:2]) + "\n" + " ".join(lines[2:-3]) + "\n" + "\n".join(lines[-3:])
    words = len(text.split())
    if words > MAX_WORDS:
        raise ValueError(f"note to the founder is {words} words; keep it under {MAX_WORDS}")
    return text
