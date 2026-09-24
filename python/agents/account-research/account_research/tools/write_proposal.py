"""'write_proposal' tool: persist a composed prequalification proposal to the repo.

The agent's session state is gone when the run ends, so the proposal is
written where the rest of the pipeline can find it: data/proposals/ at the
repo root, as JSON (for scripts/push_proposals_to_crm.py) and Markdown (for
a person). Pure Python -- no ADK or Anthropic import at run time, so it is
unit-testable without credentials, like the ledger tools.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # annotation only; keeps ADK out of the import path
    from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

#: Five sections a prequalification proposal must carry. The tool refuses a
#: draft that is missing one so a half-written proposal never reaches a
#: contact's notes.
REQUIRED_SECTIONS = (
    "What we understand",
    "What we know about you",
    "Where we can help",
    "What we'd need to qualify",
    "Proposed next step",
)

#: Money in a prequalification proposal is a bug: no rates are set.
_MONEY = re.compile(r"(\$\s?\d|\b\d[\d,]*\s?(?:USD|dollars)\b|\bper\s+(?:hour|day|month)\b)", re.I)


def default_proposals_dir() -> Path:
    """<repo>/data/proposals unless ACCOUNT_RESEARCH_PROPOSALS overrides it."""
    env = os.getenv("ACCOUNT_RESEARCH_PROPOSALS")
    if env:
        return Path(env)
    # this file: <repo>/python/agents/account-research/account_research/tools/
    return Path(__file__).resolve().parents[5] / "data" / "proposals"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "account").lower()).strip("-")[:60] or "account"


def missing_sections(markdown: str) -> list[str]:
    low = markdown.lower()
    return [s for s in REQUIRED_SECTIONS if s.lower() not in low]


def write_proposal_tool(proposal_markdown: str, tool_context: "ToolContext") -> dict[str, Any]:
    """Writes the composed prequalification proposal to data/proposals/.

    Args:
      proposal_markdown: the full proposal, Markdown, with all five sections.
      tool_context: ToolContext object; reads account, account_contacts and
        request_text from state.

    Returns:
      status "OK" with the file paths and proposal_id, or status "ERROR"
      with what is wrong (missing section, money mentioned, no account).
    """
    state = tool_context.state
    account = state.get("account") or {}
    if not account.get("name"):
        return {"status": "ERROR", "message": "No account in state -- call find_account first."}

    missing = missing_sections(proposal_markdown)
    if missing:
        return {"status": "ERROR", "message": f"Proposal is missing section(s): {missing}. Add them and call again."}
    money = _MONEY.search(proposal_markdown)
    if money:
        return {"status": "ERROR",
                "message": f"Proposal mentions money ({money.group(0)!r}); no rates are set. Remove it and call again."}

    contacts = state.get("account_contacts") or []
    request_text = state.get("request_text") or ""
    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    slug = slugify(account.get("name") or account.get("domain") or "account")
    proposal_id = "prq_" + hashlib.sha256(f"{slug}|{request_text}|{now.date()}".encode()).hexdigest()[:12]

    record = {
        "proposal_id": proposal_id,
        "generated_at": stamp,
        "model": os.getenv("ACCOUNT_RESEARCH_CLAUDE_MODEL", "claude-opus-5"),
        "account": {"name": account.get("name"), "domain": account.get("domain")},
        "contact_ids": [c.get("contact_id") for c in contacts if c.get("contact_id")],
        "apollo_contact_ids": [c.get("apollo_contact_id") for c in contacts if c.get("apollo_contact_id")],
        "request_text": request_text,
        "proposal_markdown": proposal_markdown.strip() + "\n",
    }

    out_dir = default_proposals_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{slug}-{now.date()}"
    json_path, md_path = base.with_suffix(".json"), base.with_suffix(".md")
    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    md_path.write_text(
        f"# Prequalification proposal — {account.get('name')}\n\n"
        f"_{stamp} · {proposal_id} · request: {request_text.strip().splitlines()[0] if request_text.strip() else '(none)'}_\n\n"
        + record["proposal_markdown"]
    )
    logger.info("write_proposal_tool(): %s -> %s", proposal_id, json_path)
    state.update({"proposal_id": proposal_id, "proposal_path": str(json_path)})
    return {"status": "OK", "proposal_id": proposal_id, "json": str(json_path), "markdown": str(md_path)}
