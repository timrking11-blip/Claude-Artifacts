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

#: Sections a prequalification proposal must carry, in SMI's proposal shape
#: (see prequal_agent_prompt.py). The tool refuses a draft that is missing one
#: so a half-written proposal never reaches a CRM record.
REQUIRED_SECTIONS = (
    "Engagement summary",
    "What we heard",
    "The problem in front of",
    "Approach",
    "What we'd need to qualify",
    "Next step",
    "Sources",
)

#: "In short": a prequalification proposal is one page, not the full proposal.
MAX_WORDS = 900
_LINK = re.compile(r"\]\((https?://[^)\s]+)\)|<(https?://[^>\s]+)>|(?<![(<])\b(https?://[^\s)>\]]+)")

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


def cited_links(markdown: str) -> list[str]:
    """Every http(s) link in the proposal, in first-seen order."""
    out: list[str] = []
    for m in _LINK.finditer(markdown):
        url = next(g for g in m.groups() if g)
        if url not in out:
            out.append(url)
    return out


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
    words = len(proposal_markdown.split())
    if words > MAX_WORDS:
        return {"status": "ERROR",
                "message": f"Proposal is {words} words; keep it under {MAX_WORDS}. Cut and call again."}
    cited = cited_links(proposal_markdown)
    if state.get("web_sources") and not cited:
        return {"status": "ERROR",
                "message": "Web research found sources but the proposal cites none. Link the claims to them and call again."}

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
        "account": {"name": account.get("name"), "domain": account.get("domain"),
                    "prospect": bool(account.get("prospect"))},
        "lead_source": state.get("lead_source") or None,
        "request_id": state.get("request_id") or None,
        "sources": cited,
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
