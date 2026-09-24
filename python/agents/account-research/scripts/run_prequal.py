#!/usr/bin/env python3
"""Run the account-research agents headless and write a prequalification proposal.

This is the entry point the "Prequalification proposal" GitHub Actions
workflow calls. It drives the same ADK agents as `adk web` -- root agent,
research agent (ledger + site + open-web research), prequal agent -- with no
human in the loop, then reports where the proposal landed.

Two ways in:

  # one account, from the command line
  python scripts/run_prequal.py --account "Acme" --domain acme.com \
      --request "Asked on LinkedIn about pricing for a federal pilot" --lead-source linkedin

  # every queued request under data/prequal/requests/ without a proposal yet
  python scripts/run_prequal.py --pending

A queued request is a JSON file:
  {"account": "Acme", "domain": "acme.com", "request_text": "...",
   "lead_source": "linkedin", "requested_at": "2026-09-24"}
When its proposal is written, the file gains proposal_id / proposal_path /
completed_at, which is what makes --pending skip it next time.

Credentials: ANTHROPIC_API_KEY (or an `ant auth login` profile) for both the
agents and the web research tool. Exit code 1 if any request produced no proposal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
REPO = AGENT_DIR.parents[2]
QUEUE = REPO / "data" / "prequal" / "requests"
sys.path.insert(0, str(AGENT_DIR))

APP = "account_research"
USER = "prequal-workflow"


def message_for(req: dict) -> str:
    name, domain = (req.get("account") or "").strip(), (req.get("domain") or "").strip()
    who = f"{name} ({domain})" if name and domain else (name or domain)
    text = (req.get("request_text") or "").strip()
    if not text:
        src = (req.get("lead_source") or "").strip().lower()
        how = "a LinkedIn contact" if src == "linkedin" else (f"a {src} contact" if src else "an outbound contact")
        text = (f"No written request is on file; this follows {how}. "
                "Write a proactive prequalification note from the research.")
    return f"prequal {who}: {text}"


async def run_one(req: dict, request_id: str | None) -> dict:
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from account_research.agent import root_agent

    runner = InMemoryRunner(agent=root_agent, app_name=APP)
    session = await runner.session_service.create_session(
        app_name=APP, user_id=USER,
        state={"lead_source": req.get("lead_source") or "", "request_id": request_id or ""},
    )
    prompt = message_for(req)
    print(f"\n>>> {prompt}", flush=True)
    last_text = ""
    async for event in runner.run_async(
        user_id=USER, session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        for part in (getattr(event.content, "parts", None) or []) if event.content else []:
            if getattr(part, "text", None):
                last_text = part.text
                print(f"[{event.author}] {part.text[:400]}", flush=True)
            elif getattr(part, "function_call", None):
                print(f"[{event.author}] -> {part.function_call.name}", flush=True)
    final = await runner.session_service.get_session(app_name=APP, user_id=USER, session_id=session.id)
    state = dict(final.state) if final else {}
    return {"proposal_id": state.get("proposal_id"), "proposal_path": state.get("proposal_path"),
            "last_message": last_text}


def pending_requests() -> list[Path]:
    if not QUEUE.exists():
        return []
    return [p for p in sorted(QUEUE.glob("*.json"))
            if not json.loads(p.read_text() or "{}").get("proposal_id")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pending", action="store_true", help="run every queued request without a proposal")
    ap.add_argument("--account", default="")
    ap.add_argument("--domain", default="")
    ap.add_argument("--request", default="", help="the inbound request text, verbatim")
    ap.add_argument("--lead-source", default="")
    args = ap.parse_args()

    jobs: list[tuple[Path | None, dict]] = []
    if args.pending:
        jobs = [(p, json.loads(p.read_text())) for p in pending_requests()]
        if not jobs:
            print("No pending prequalification requests.")
            return 0
    elif args.account or args.domain:
        jobs = [(None, {"account": args.account, "domain": args.domain,
                        "request_text": args.request, "lead_source": args.lead_source})]
    else:
        ap.error("give --pending, or --account and/or --domain")

    failed = 0
    for path, req in jobs:
        out = asyncio.run(run_one(req, path.stem if path else None))
        if out["proposal_id"]:
            print(f"OK {out['proposal_id']} -> {out['proposal_path']}")
            if path:
                req.update(proposal_id=out["proposal_id"],
                           proposal_path=os.path.relpath(out["proposal_path"], REPO),
                           completed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                path.write_text(json.dumps(req, indent=2, ensure_ascii=False) + "\n")
        else:
            failed += 1
            print(f"FAILED {path.name if path else req.get('account')}: no proposal written. "
                  f"Last agent message: {out['last_message'][:600]}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
