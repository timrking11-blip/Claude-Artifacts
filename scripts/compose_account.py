#!/usr/bin/env python3
"""The deterministic legs of a button-driven account composition run.

This is the one process that produces a prequalification proposal. The
Intake page (https://claude.ai/artifact/BtU87XpWsN9VDNTFwidnA3) writes a run
manifest and wakes the session that owns this repo. That session runs three
commands here and does the language-model legs itself: web research (with its
own web search and fetch tools, following the research desk brief in
account_research/tools/web_research.py), the page summary, and the proposal
draft. No ADK runtime, no API key, no GCP.

  prepare  <manifest.json> --run-id <id> --crm-dump <dump>
      Re-gates the manifest, runs find_account / list_account_contacts /
      assess_ledger_quality from the agent's pure-Python ledger tools, fetches
      the page (honouring on_fetch_error), writes the warehouse sentinel,
      computes the founder note, and writes data/runs/<id>/{manifest,state,
      founder,run_update}.json plus prompts.md -- the web research brief and
      the page-summary prompt, filled in. Exit 2 when the manifest fails its
      gate or the run is halted for operator review.

  brief    <run-id> --web-research <memo.md> [--web-sources <urls.txt>]
           [--website-summary <file>] [--data-sources <firmographics.md>]
           [--coverage <coverage.json>]
      Stores the research the session did into the run state and writes
      proposal_prompt.md: the SMI prequalification prompt with every research
      slot filled.

  finalize <run-id> --proposal <draft.md> [--website-summary <file>]
           [--composer-flag <text>]... --crm-dump <dump>
      Validates the draft exactly as the agent's write_proposal tool does
      (SMI sections, no money, under 1,000 words, cites the research when it
      found sources), writes data/proposals/<slug>-<date>.{json,md}
      with the founder note inside, plans the CRM writes (contact notes via
      push_proposals_to_crm.plan; the account record per the disposition) and
      emits them as ArtifactData batch entries under data/artifact/crm/
      compose_<run-id>/, plus data/runs/<id>/run_final.json for the page.

Both commands are pure functions of their inputs and are tested without
network or credentials in tests/test_compose_account.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from crm import config  # noqa: E402
from crm.crm_sync import load_crm_dump, pinned, system_activity, utcnow_iso  # noqa: E402
from crm.founder_note import assess  # noqa: E402
from crm.guardrails import check_run, credit_spend_allowed  # noqa: E402
from crm.master import load_master  # noqa: E402
from crm.schema import normalize_domain  # noqa: E402

sys.path.insert(0, str(config.AGENT_DIR))
from account_research.sub_agents.prequal_agent_prompt import PROMPT as PREQUAL_PROMPT  # noqa: E402
from account_research.sub_agents.summarize_page_agent_prompt import PROMPT as SUMMARY_PROMPT  # noqa: E402
from account_research.tools import fetch_page, ledger  # noqa: E402
from account_research.tools.web_research import SYSTEM as RESEARCH_SYSTEM  # noqa: E402
from account_research.tools.web_research import _prompt as research_request  # noqa: E402
from account_research.tools.write_proposal import MAX_WORDS, _MONEY, cited_links, missing_sections, slugify  # noqa: E402

import push_proposals_to_crm  # noqa: E402

WAREHOUSE_SENTINEL = "not available"
STEP_ORDER = ("find_account", "list_account_contacts", "assess_ledger_quality", "fetch_page",
              "apollo", "prospecting", "web_research", "summarize_page", "warehouse_findings",
              "compose_proposal", "crm_write")

#: The data sources a run pulls, in order, and what each one is for. The
#: session reports each one's outcome in coverage.json; `brief` turns that into
#: step lamps on the page, founder-note lines, and the merged CRM note.
DATA_SOURCES = (
    ("ledger", "enriched data layer (data/master/contacts.json)"),
    ("apollo", "Apollo organization enrich + people at the domain"),
    ("prospecting", "Vibe Prospecting (Explorium) business match, firmographics, events"),
    ("site", "the company's own site, fetched from this container"),
    ("web", "open-web research: company, market, competitors, adjacent, macro"),
)

#: The Monday chain, UTC. Kept here once so the merged note, the docs and the
#: routines say the same thing.
SYNC_SCHEDULE = (
    (6, 0, "GitHub Actions: Apollo + Explorium pull, merge into the enriched data layer"),
    (11, 0, "Apollo ⇄ CRM two-way sync: uploads accounts flagged pending_apollo, re-keys them to the Apollo id"),
    (11, 30, "Enrichment → CRM push and proposal catch-up (idempotent by proposal id)"),
    (12, 0, "GTM Command Center refresh (proposal counts)"),
)


def next_monday(now: datetime) -> datetime:
    """The Monday whose 11:00 UTC sync has not happened yet."""
    days = (0 - now.weekday()) % 7
    monday = (now + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    if days == 0 and now.hour >= 11:
        monday += timedelta(days=7)
    return monday


def sync_schedule_lines(now: datetime) -> list[str]:
    monday = next_monday(now)
    return [f"{monday.strftime('%a %d %b %Y')} {h:02d}:{m:02d} UTC — {what}" for h, m, what in SYNC_SCHEDULE]


def lead_source_of(manifest: dict[str, Any]) -> str | None:
    """linkedin when the page's LinkedIn tick is on, else whatever the manifest says."""
    acct = (manifest.get("state") or {}).get("account") or {}
    if acct.get("source"):
        return str(acct["source"]).lower()
    if (manifest.get("crm") or {}).get("pre_qual"):
        return "linkedin"
    return (manifest.get("request") or {}).get("lead_source") or None

#: Everything the CRM page's own "Add account" drawer writes for a new account,
#: in the same order, so a run-minted account looks like a hand-made one.
ACCOUNT_DEFAULTS: dict[str, Any] = {
    "apollo_account_id": "", "name": "", "domain": "", "website": "", "stage": "cold",
    "apollo_lists": [], "apollo_url": "", "apollo_synced_at": "", "segment": "Added by composition run",
    "origin": "crm", "owner": "", "employees": 0, "revenue": 0, "industry": "", "founded": 0,
    "city": "", "state": "", "country": "", "street": "", "postal": "", "address": "",
    "phone": "", "linkedin": "", "logo": "", "description": "", "keywords": [],
    "total_funding": 0, "latest_funding": "", "latest_funding_amount": 0, "last_raised_at": "",
    "parent_company": "", "parent_website": "", "suborg_count": 0, "suborgs": [], "sic": "", "naics": "",
    "qualified": False, "notes": "", "next_step": "", "next_date": "", "deal_value": 0,
    "activity": [], "flags": [], "created_at": "", "updated_at": "",
}


class GateError(SystemExit):
    """Manifest failed its gate; the run must not start."""

    def __init__(self, message: str):
        print(f"GATE: {message}", file=sys.stderr)
        super().__init__(2)


def _now(value: str | None) -> datetime:
    if value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _fill(prompt: str, values: dict[str, Any]) -> str:
    """Fill the agent prompt's `{key}` / `{key?}` slots without str.format."""
    out = prompt
    for key, value in values.items():
        text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
        out = out.replace("{" + key + "?}", text or "(none)").replace("{" + key + "}", text or "(none)")
    return out


# ---------------------------------------------------------------- prepare ----

def gate(manifest: dict[str, Any]) -> None:
    acct = (manifest.get("state") or {}).get("account") or {}
    if not (acct.get("name") or acct.get("domain")):
        raise GateError("state.account has neither name nor domain")
    if not (manifest.get("crm") or {}).get("disposition"):
        raise GateError("crm.disposition is null -- choose apollo or manual on the intake page")


def resolve_account(manifest: dict[str, Any], state: dict[str, Any]) -> str:
    """find_account with the manifest's domain, then name. Returns the step outcome."""
    acct = manifest["state"]["account"]
    ctx = SimpleNamespace(state=state)
    outcome = "not_found"
    for query in (acct.get("domain"), acct.get("name")):
        if not query:
            continue
        res = ledger.find_account_tool(query, ctx)
        if res["status"] == "OK":
            outcome = "done"
            break
        if res["status"] == "AMBIGUOUS":
            wanted = normalize_domain(acct.get("domain"))
            exact = [c for c in res["candidates"] if wanted and c.get("domain") == wanted]
            if exact:
                ledger.find_account_tool(exact[0]["domain"], ctx)
                outcome = "done"
                break
            raise GateError("find_account is ambiguous: " + ", ".join(c["name"] for c in res["candidates"])
                            + " -- give the intake page the exact domain")
    if outcome == "done":
        state["account"]["in_ledger"] = True
        # The manifest's spelling wins for display; the ledger's key drives the tools.
        state["account"]["name"] = acct.get("name") or state["account"]["name"]
    else:
        # Same shape register_prospect gives the agent: a company we have not met
        # in the ledger yet, researched from the open web, no contacts invented.
        dom = normalize_domain(acct.get("domain"))
        state["account"] = {"key": f"domain:{dom}" if dom else None, "name": acct.get("name") or dom,
                            "domain": dom, "contact_count": 0, "industry": None, "employee_count": None,
                            "in_ledger": False, "prospect": True}
    state["account"]["crm_account_id"] = acct.get("crm_account_id")
    return outcome


def prepare(manifest: dict[str, Any], run_id: str, docs: dict[str, dict[str, Any]], now: datetime,
            *, fetch: bool = True, account_lists_empty: bool = True) -> dict[str, Any]:
    """Run the deterministic legs. Returns {state, steps, founder, halted}."""
    gate(manifest)
    m_state = manifest["state"]
    state: dict[str, Any] = {"request_text": (manifest.get("request") or {}).get("text") or "",
                             "lead_source": lead_source_of(manifest) or "", "request_id": run_id}
    steps: dict[str, str] = {}
    ctx = SimpleNamespace(state=state)

    steps["find_account"] = resolve_account(manifest, state)
    in_ledger = state["account"]["in_ledger"]

    if (m_state.get("account_contacts") or {}).get("include"):
        if in_ledger:
            ledger.list_account_contacts_tool(ctx)
            limit = str((m_state["account_contacts"].get("limit") or "all"))
            if limit.isdigit():
                state["account_contacts"] = state["account_contacts"][: int(limit)]
            steps["list_account_contacts"] = "done"
        else:
            state["account_contacts"] = []
            steps["list_account_contacts"] = "empty"
    else:
        steps["list_account_contacts"] = "skipped"

    if (m_state.get("ledger_quality") or {}).get("include"):
        if in_ledger:
            ledger.assess_ledger_quality_tool(ctx)
            steps["assess_ledger_quality"] = "done"
        else:
            steps["assess_ledger_quality"] = "empty"
    else:
        steps["assess_ledger_quality"] = "skipped"

    halted = False
    web = m_state.get("website_summary") or {}
    if web.get("include"):
        url = web.get("page_url") or (f"https://{state['account']['domain']}" if state["account"].get("domain") else None)
        if not url:
            state["page_error"] = "no page_url and no domain"
        elif not fetch:
            state["page_error"] = "fetch disabled"
        else:
            res = fetch_page.fetch_page_tool(url, ctx)
            if res["status"] != "OK":
                state["page_error"] = res["message"]
        if state.get("page_error"):
            mode = web.get("on_fetch_error") or "store_state"
            steps["fetch_page"] = f"failed:{mode}"
            if mode == "store_state":
                state["website_summary"] = f"Website fetch failed: {state['page_error']}"
                steps["summarize_page"] = "skipped"
            elif mode == "halt":
                halted = True
                steps["summarize_page"] = "halted"
            else:
                steps["summarize_page"] = "skipped"
        else:
            steps["fetch_page"] = "done"
            steps["summarize_page"] = "pending"
    else:
        steps["fetch_page"] = steps["summarize_page"] = "skipped"

    steps["apollo"] = "pending"
    steps["prospecting"] = "pending"
    steps["web_research"] = "pending"

    wh = m_state.get("warehouse_findings") or {}
    if wh.get("include"):
        state["warehouse_findings"] = wh.get("sentinel") or WAREHOUSE_SENTINEL
        state["warehouse_sentinel"] = True
        steps["warehouse_findings"] = "sentinel"
    else:
        steps["warehouse_findings"] = "skipped"

    steps["compose_proposal"] = "halted" if halted else "pending"
    steps["crm_write"] = "pending"

    founder = assess(manifest, state, docs, now, account_lists_empty=account_lists_empty)
    return {"state": state, "steps": steps, "founder": founder, "halted": halted}


def research_prompt(state: dict[str, Any]) -> str:
    """The research desk brief (web_research.SYSTEM) plus the per-account request."""
    acct = state.get("account") or {}
    return (RESEARCH_SYSTEM.strip() + "\n\n---\n\n"
            + research_request(acct.get("name"), acct.get("domain"), state.get("request_text") or ""))


def summary_prompt(state: dict[str, Any]) -> str:
    return _fill(SUMMARY_PROMPT, {"page_contents": state.get("page_contents") or ""})


def proposal_prompt(state: dict[str, Any]) -> str:
    """The SMI prequalification prompt with every research slot filled from state."""
    prequal = _fill(PREQUAL_PROMPT, {
        "request_text": state.get("request_text") or "",
        "account": {k: v for k, v in (state.get("account") or {}).items() if k not in ("key",)},
        "firmographics": state.get("firmographics") or "",
        "web_research": state.get("web_research") or "",
        "web_sources": state.get("web_sources") or [],
        "website_summary": state.get("website_summary") or "",
        "account_contacts": state.get("account_contacts") or [],
        "ledger_quality": state.get("ledger_quality") or {},
        "warehouse_findings": state.get("warehouse_findings") or "",
    })
    tail = prequal.find("When the draft is complete, call the write_proposal tool")
    if tail != -1:
        prequal = prequal[:tail] + ("Return only the Markdown, nothing before or after it. The session saves it "
                                    "with `scripts/compose_account.py finalize`, which refuses a draft that is "
                                    f"missing a section, mentions money, runs past {MAX_WORDS:,} words, or cites "
                                    "nothing when the research found sources.\n")
    return prequal


def prompts_for(state: dict[str, Any]) -> tuple[str, str]:
    """Back-compat pair: (summary prompt, proposal prompt)."""
    return summary_prompt(state), proposal_prompt(state)


def write_prepare(run_dir: Path, manifest: dict[str, Any], result: dict[str, Any], run_id: str, now: datetime) -> None:
    state = dict(result["state"])
    page = state.pop("page_contents", None)
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "state.json", state)
    if page:
        (run_dir / "page.txt").write_text(page)
    founder = result["founder"].as_dict()
    _write_json(run_dir / "founder.json", founder)
    acct = result["state"]["account"]
    spend = credit_spend_allowed(manifest)
    (run_dir / "prompts.md").write_text(
        "# Prompts for run " + run_id + "\n\n"
        "GUARDRAILS (from the intake form; finalize enforces them and refuses the run on a breach):\n"
        f"- Domain lock: the prospect is the company at {acct.get('domain') or '(no domain given)'} and nothing else. "
        "A similarly named company at another domain is not the prospect, whatever a search result says: record it "
        "under Gaps and use nothing from it.\n"
        + ("- Credit spend: ALLOWED by the intake form, for the intake domain only.\n" if spend else
           "- Credit spend: NOT allowed by the intake form. Do not call Apollo organization enrich or any Vibe "
           "Prospecting enrichment; record apollo and prospecting as \"skipped: credit spend not allowed on the "
           "intake form\". Free lookups (people search, match-business) are fine.\n")
        + "- Empty means empty: if nothing is found on the intake domain, the proposal is a not-found note that cites "
        "only that domain and primary macro sources.\n\n"
        "## 0 · Data sources → data_sources.md + coverage.json\n\n"
        f"Account: {acct.get('name')} ({acct.get('domain') or 'no domain'}).\n"
        "Pull every source that can speak to this account, cheapest first, and surface any credit cost before "
        "spending it:\n"
        "- **Apollo**: apollo_organizations_enrich on the domain (firmographics, funding, headcount, "
        "technologies, keywords); apollo_mixed_people_api_search on the domain for leadership and "
        "decision-makers (the plan may refuse people search; record that).\n"
        "- **Vibe Prospecting**: match-business on name + domain, then enrich-business for firmographics, "
        "technographics, funding and recent business events; fetch-prospects for decision-makers if the "
        "match holds. Use estimate-cost first; stop and record 'no credits' rather than spend blind.\n"
        "Write what you found to data_sources.md under '## Apollo' and '## Vibe Prospecting', each fact with its "
        "source, and never mix up a similarly named company (a name match with the wrong domain is not a match).\n"
        "Write coverage.json as {\"ledger\": ..., \"apollo\": ..., \"prospecting\": ..., \"site\": ..., "
        "\"web\": ...}, each value \"ok: <what>\" or \"none: <why>\" or \"error: <why>\" — for example "
        "\"none: host blocked by the environment's network policy\".\n\n"
        "## 1 · Web research → web_research.md + web_sources.txt\n\n"
        "Only the company at this domain counts: a similarly named company at another domain is not a "
        "match, even if a search result claims it is — record it under Gaps and use nothing from it. "
        "Answer with your own web search and web fetch tools. Save the memo to web_research.md and every URL "
        "you fetched or cited, one per line, to web_sources.txt.\n\n"
        + research_prompt(result["state"]).strip() + "\n\n"
        "## 2 · Summarise the page → website_summary.txt\n\n"
        + ("(fetch_page did not run; skip this leg — the research memo covers the site)\n" if not page
           else summary_prompt(result["state"]).strip() + "\n")
        + "\n## 3 · Draft the proposal\n\nRun `scripts/compose_account.py brief " + run_id
        + " --web-research ... --web-sources ... --data-sources ... --coverage ... [--website-summary ...]`; "
        "it writes proposal_prompt.md with the research filled in. Answer that prompt and save the Markdown "
        "to proposal.md.\n")
    _write_json(run_dir / "run_update.json", {
        "status": "halted" if result["halted"] else "running",
        "steps": result["steps"],
        "founder_note": founder["text"],
        "founder_status": founder["status"],
        "matched_contact_ids": founder["matched_doc_ids"],
        "account": {k: result["state"]["account"].get(k) for k in ("name", "domain", "in_ledger", "contact_count")},
        "prepared_at": _iso(now),
    })


# ------------------------------------------------------------------ brief ----

def read_sources(text: str | None) -> list[str]:
    out: list[str] = []
    for line in (text or "").splitlines():
        url = line.strip().lstrip("-* ").strip()
        if url.startswith("http") and url not in out:
            out.append(url)
    return out


def coverage_status(value: Any) -> str:
    """'ok: …' -> done, 'none: …' -> empty, 'error: …' -> failed, missing -> skipped."""
    text = str(value or "").strip().lower()
    if not text:
        return "skipped"
    if text.startswith("ok"):
        return "done"
    if text.startswith("none"):
        return "empty"
    if text.startswith("skip"):
        return "skipped"
    return "failed"


def brief(run_dir: Path, web_research: str | None, web_sources: list[str], website_summary: str | None,
          data_sources: str | None = None, coverage: dict[str, Any] | None = None) -> str:
    """Store the session's research in state.json and return the filled proposal prompt."""
    state = json.loads((run_dir / "state.json").read_text())
    if data_sources and data_sources.strip():
        state["firmographics"] = data_sources.strip()
    cov = dict(coverage or {})
    cov.setdefault("ledger", "ok: {} contact(s)".format((state.get("account") or {}).get("contact_count") or 0)
                   if (state.get("account") or {}).get("in_ledger") else "none: not in the enriched data layer")
    if "site" not in cov:
        cov["site"] = f"error: {state['page_error']}" if state.get("page_error") else ("ok: fetched" if state.get("page_url") else "")
    state["coverage"] = cov
    memo = (web_research or "").strip()
    if memo:
        state["web_research"] = memo
        # Sources the memo links count too, so a memo without a separate list still cites.
        state["web_sources"] = web_sources or cited_links(memo)
    else:
        state["web_research"] = "Web research returned nothing."
        state["web_sources"] = []
        state["web_research_error"] = "empty memo"
    if website_summary:
        state["website_summary"] = website_summary.strip()
    cov.setdefault("web", f"ok: {len(state['web_sources'])} source(s)" if state.get("web_sources")
                   else "none: no sources found")
    _write_json(run_dir / "state.json", state)
    prompt = proposal_prompt(state)
    (run_dir / "proposal_prompt.md").write_text(prompt)
    return prompt


# --------------------------------------------------------------- finalize ----

def proposal_record(state: dict[str, Any], manifest: dict[str, Any], run_id: str, proposal_md: str,
                    founder: dict[str, Any], composer_flags: list[str], now: datetime) -> dict[str, Any]:
    """Same shape as the agent's write_proposal tool, plus founder_note and run.

    One proposal per run, one run per intake-form submission. A changed
    proposal is a new run started on the intake page, never an edit here.
    """
    missing = missing_sections(proposal_md)
    if missing:
        raise GateError(f"proposal is missing section(s): {missing}")
    money = _MONEY.search(proposal_md)
    if money:
        raise GateError(f"proposal mentions money ({money.group(0)!r}); no rates are set")
    words = len(proposal_md.split())
    if words > MAX_WORDS:
        raise GateError(f"proposal is {words} words; keep it under {MAX_WORDS}")
    cited = cited_links(proposal_md)
    if state.get("web_sources") and not cited:
        raise GateError("web research found sources but the proposal cites none; link the claims to them")
    account = state["account"]
    request_text = state.get("request_text") or ""
    slug = slugify(account.get("name") or account.get("domain") or "account")
    # One id per run: a re-run of the same account on the same day with better
    # research is a new proposal, not a silent no-op against yesterday's draft.
    pid = "prq_" + hashlib.sha256(f"{slug}|{request_text}|{now.date()}|{run_id}".encode()).hexdigest()[:12]
    holds = list(founder.get("holds") or []) + [f"Composer: {f}" for f in composer_flags if f.strip()]
    notes = list(founder.get("notes") or [])
    from crm.guardrails import found_on_intake_domain, urls_in  # local: keeps the module's import list honest
    intake = normalize_domain(((manifest.get("state") or {}).get("account") or {}).get("domain"))
    if intake and not found_on_intake_domain(state.get("coverage"), urls_in(state.get("web_research")) + cited, intake):
        holds.append(f"Nothing was found on {intake} by any source; this is a not-found note. Confirm the domain "
                     "with the prospect before anything goes out.")
    if state.get("web_research_error") or not state.get("web_sources"):
        notes.append("Web research found no sources; the proposal argues from the request and the ledger alone.")
    labels = dict(DATA_SOURCES)
    for key, value in (state.get("coverage") or {}).items():
        if key in ("web", "ledger", "site"):
            continue  # already covered by the lines above and by founder_note.assess
        if coverage_status(value) in ("empty", "failed"):
            notes.append(f"{labels.get(key, key).split(':')[0].split(' (')[0]}: {str(value).split(':', 1)[-1].strip()}.")
    text = "\n".join([f"HOLD — {h}" for h in holds] + [f"Note — {n}" for n in notes]) or "Nothing extenuating; proceed as drafted."
    contacts = state.get("account_contacts") or []
    cov = state.get("coverage") or {}
    appendix = ["Research coverage:"]
    for key, label in DATA_SOURCES:
        appendix.append(f"- {label}: {cov.get(key) or 'not reported'}")
    appendix.append(f"- sources cited in the proposal: {len(cited)}")
    appendix.append("Sync schedule (what happens to this record next):")
    appendix += [f"- {line}" for line in sync_schedule_lines(now)]
    return {
        "proposal_id": pid,
        "generated_at": _iso(now),
        "model": os.getenv("ACCOUNT_RESEARCH_CLAUDE_MODEL", "session"),
        "run_id": run_id,
        "account": {"name": account.get("name"), "domain": account.get("domain"),
                    "prospect": bool(account.get("prospect"))},
        "lead_source": state.get("lead_source") or None,
        "request_id": run_id,
        "sources": cited,
        "contact_ids": [c.get("contact_id") for c in contacts if c.get("contact_id")],
        "apollo_contact_ids": [c.get("apollo_contact_id") for c in contacts if c.get("apollo_contact_id")],
        "request_text": request_text,
        "request": manifest.get("request") or {},
        "founder_note": {"status": "needs_founder" if holds else "done", "holds": holds, "notes": notes, "text": text},
        "coverage": cov,
        "notes_appendix": "\n".join(appendix),
        "proposal_markdown": proposal_md.strip() + "\n",
    }


def write_proposal_files(record: dict[str, Any], proposals_dir: Path, now: datetime) -> tuple[Path, Path]:
    proposals_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(record["account"].get("name") or record["account"].get("domain") or "account")
    base = proposals_dir / f"{slug}-{now.date()}"
    json_path, md_path = base.with_suffix(".json"), base.with_suffix(".md")
    _write_json(json_path, record)
    first = record["request_text"].strip().splitlines()[0] if record["request_text"].strip() else "(none)"
    md_path.write_text(
        f"# Prequalification proposal — {record['account'].get('name')}\n\n"
        f"_{record['generated_at']} · {record['proposal_id']} · run {record['run_id']} · request: {first}_\n\n"
        + record["proposal_markdown"]
        + "\n---\n\n**Founder note**\n\n" + record["founder_note"]["text"] + "\n")
    return json_path, md_path


def _mint_account_id(now: datetime) -> str:
    return "crm_" + now.strftime("%Y%m%d") + "_" + secrets.token_hex(3)


def plan_account_write(record: dict[str, Any], manifest: dict[str, Any], accounts: dict[str, dict[str, Any]],
                       contact_ids: list[str], now: datetime) -> dict[str, Any] | None:
    """One write to the CRM `accounts` collection, or None when nothing is needed.

    Existing account (by manifest id, then by domain): append notes + activity,
    never touch stage or any populated field. Otherwise mint the CRM page's
    own new-account document with `pending_apollo` -- both dispositions end up
    here, because the Apollo path's search/create is the session's Apollo call
    and the record still has to exist for the weekly sync to re-key it.
    """
    acct = record["account"]
    domain = normalize_domain(acct.get("domain"))
    pid, stamp = record["proposal_id"], _iso(now)
    if contact_ids:
        line = (f"--- Prequalification proposal · {stamp[:10]} · {pid} --- "
                f"attached to {len(contact_ids)} contact(s); run {record['run_id']}; see contact notes.")
    else:
        # A prospect with no CRM contacts: the account carries the proposal itself,
        # in the same block shape push_proposals_to_crm uses.
        line = push_proposals_to_crm.NOTES_HEADER.format(date=stamp[:10], pid=pid) + "\n" + record["proposal_markdown"].strip()
        line += "\n\nFounder note:\n" + record["founder_note"]["text"]
        line += "\n\n" + record["notes_appendix"]
    wanted = (manifest["state"]["account"] or {}).get("crm_account_id")
    existing_id = wanted if wanted in accounts else next(
        (i for i, d in accounts.items() if domain and normalize_domain(d.get("domain") or d.get("website")) == domain), None)
    if existing_id:
        doc = accounts[existing_id]
        if doc.get("proposal_ref") == pid or pid in (doc.get("notes") or ""):
            return None
        notes = (doc.get("notes") or "").rstrip()
        data = {"notes": (notes + "\n\n" + line) if notes else line, "proposal_ref": pid, "updated_at": stamp,
                "activity": system_activity(doc.get("activity"), f"Prequalification proposal drafted ({pid})", ts=stamp)}
        if (record.get("lead_source") or "") == "linkedin" and not doc.get("source"):
            data["source"] = "linkedin"
        if not isinstance(doc.get("pre_qual"), bool):
            data["pre_qual"] = True  # a drafted proposal puts the account in the pre-qual phase
        return pinned(doc, {"op": "update", "collection": "accounts", "doc_id": existing_id, "data": data})
    if not (acct.get("name") and domain):
        return None
    doc = dict(ACCOUNT_DEFAULTS)
    doc["pre_qual"] = True
    if (record.get("lead_source") or "") == "linkedin":
        doc["source"] = "linkedin"
    doc.update({"name": acct["name"], "domain": domain, "website": "https://" + domain, "notes": line,
                "proposal_ref": pid,
                "activity": [{"ts": stamp, "type": "system", "text": f"Added by composition run {record['run_id']} — queued for Apollo upload"}],
                "flags": ["pending_apollo"], "created_at": stamp, "updated_at": stamp})
    return {"op": "set", "collection": "accounts", "doc_id": _mint_account_id(now), "data": doc}


def finalize(run_dir: Path, proposal_md: str, website_summary: str | None, composer_flags: list[str],
             master, docs: dict[str, dict[str, Any]], accounts: dict[str, dict[str, Any]],
             now: datetime) -> dict[str, Any]:
    """Validate, build the record, plan every CRM write. Pure apart from reading run_dir.

    Refuses when a proposal is already filed for this run (run_final.json):
    a changed proposal is a new run from the intake page. Refuses on any
    guardrail violation (crm/guardrails.py) before anything is written.
    """
    manifest = json.loads((run_dir / "manifest.json").read_text())
    state = json.loads((run_dir / "state.json").read_text())
    founder = json.loads((run_dir / "founder.json").read_text())
    run_id = run_dir.name
    if website_summary:
        state["website_summary"] = website_summary.strip()
    prior = run_dir / "run_final.json"
    if prior.exists():
        raise GateError(f"run {run_id} already filed {json.loads(prior.read_text()).get('proposal_id')}; "
                        "a changed proposal is a new run started on the intake page")
    research = (run_dir / "web_research.md").read_text() if (run_dir / "web_research.md").exists() else state.get("web_research") or ""
    sources_md = (run_dir / "data_sources.md").read_text() if (run_dir / "data_sources.md").exists() else state.get("firmographics") or ""
    problems = check_run(manifest, state.get("coverage"), research, sources_md, proposal_md, cited_links(proposal_md))
    if problems:
        raise GateError("guardrail: " + " | ".join(problems))
    record = proposal_record(state, manifest, run_id, proposal_md, founder, composer_flags, now)
    writes, log = push_proposals_to_crm.plan([record], master, docs, now=_iso(now))
    contact_ids = [w["doc_id"] for w in writes]
    account_write = plan_account_write(record, manifest, accounts, contact_ids, now)
    if account_write:
        writes.append(account_write)
    return {"record": record, "state": state, "writes": writes, "log": log, "contact_ids": contact_ids,
            "account_id": account_write["doc_id"] if account_write else None}


def write_finalize(run_dir: Path, result: dict[str, Any], batch_dir: Path, json_path: Path, md_path: Path,
                   now: datetime) -> Path:
    """Emit the batch (per-document files + one writes.json) and run_final.json."""
    batch_dir.mkdir(parents=True, exist_ok=True)
    for stale in batch_dir.glob("*.json"):
        stale.unlink()
    entries = []
    for w in result["writes"]:
        doc_path = batch_dir / f"{w['collection']}__{w['doc_id']}.json"
        _write_json(doc_path, w["data"])
        entry = {"op": w["op"], "collection": w["collection"], "doc_id": w["doc_id"], "file_path": str(doc_path)}
        if "if_version" in w:
            entry["if_version"] = w["if_version"]
        entries.append(entry)
    writes_path = batch_dir / "writes.json"
    _write_json(writes_path, entries)
    record = result["record"]
    _write_json(run_dir / "state.json", result["state"])
    _write_json(run_dir / "run_final.json", {
        "status": record["founder_note"]["status"],
        "steps": {**json.loads((run_dir / "run_update.json").read_text()).get("steps", {}),
                  "apollo": coverage_status((result["state"].get("coverage") or {}).get("apollo")),
                  "prospecting": coverage_status((result["state"].get("coverage") or {}).get("prospecting")),
                  "web_research": ("failed" if result["state"].get("web_research_error")
                                   else "done" if result["state"].get("web_research") else "skipped"),
                  "summarize_page": "done" if result["state"].get("website_summary") else "skipped",
                  "compose_proposal": "done", "crm_write": "pending" if entries else "nothing"},
        "founder_note": record["founder_note"]["text"],
        "founder_status": record["founder_note"]["status"],
        "proposal_id": record["proposal_id"],
        "sources": record["sources"],
        "coverage": record["coverage"],
        "sync_schedule": sync_schedule_lines(now),
        "proposal_markdown": record["proposal_markdown"],
        "proposal_path": str(json_path.relative_to(ROOT)) if json_path.is_relative_to(ROOT) else str(json_path),
        "crm": {"contact_ids": result["contact_ids"], "account_id": result["account_id"],
                "writes_planned": len(entries)},
        "log": result["log"],
        "finished_at": _iso(now),
    })
    return writes_path


# ------------------------------------------------------------------- main ----

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("manifest", type=Path)
    p.add_argument("--run-id", default=None)
    p.add_argument("--crm-dump", type=Path, required=True)
    p.add_argument("--runs-dir", type=Path, default=config.RUNS_DIR)
    p.add_argument("--master", type=Path, default=None, help="ledger file (default data/master/contacts.json)")
    p.add_argument("--no-fetch", action="store_true", help="do not fetch the page (tests, offline)")
    p.add_argument("--account-lists-present", action="store_true",
                   help="meta/config.account_lists is no longer empty (default: empty, as of 17 Sep 2026)")
    p.add_argument("--now", default=None)

    b = sub.add_parser("brief")
    b.add_argument("run_id")
    b.add_argument("--web-research", type=Path, default=None, help="the research memo (Markdown)")
    b.add_argument("--web-sources", type=Path, default=None, help="URLs, one per line")
    b.add_argument("--website-summary", type=Path, default=None)
    b.add_argument("--data-sources", type=Path, default=None, help="Apollo / prospecting findings (Markdown)")
    b.add_argument("--coverage", type=Path, default=None, help="per-source outcome (JSON)")
    b.add_argument("--runs-dir", type=Path, default=config.RUNS_DIR)
    b.add_argument("--now", default=None)

    f = sub.add_parser("finalize")
    f.add_argument("run_id")
    f.add_argument("--proposal", type=Path, required=True, help="the drafted Markdown")
    f.add_argument("--website-summary", type=Path, default=None)
    f.add_argument("--composer-flag", action="append", default=[], help="a judgement-call HOLD line; repeatable")
    f.add_argument("--crm-dump", type=Path, required=True)
    f.add_argument("--runs-dir", type=Path, default=config.RUNS_DIR)
    f.add_argument("--proposals-dir", type=Path, default=config.PROPOSALS_DIR)
    f.add_argument("--out-dir", type=Path, default=config.CRM_BATCH_DIR)
    f.add_argument("--master", type=Path, default=None)
    f.add_argument("--now", default=None)

    args = parser.parse_args(argv)
    now = _now(args.now)
    if getattr(args, "master", None):
        os.environ["ACCOUNT_RESEARCH_LEDGER"] = str(args.master)

    if args.cmd == "prepare":
        manifest = json.loads(args.manifest.read_text())
        run_id = args.run_id or (manifest.get("run") or {}).get("run_id") or ("run_" + now.strftime("%Y%m%d") + "_" + secrets.token_hex(3))
        docs = load_crm_dump(args.crm_dump)
        result = prepare(manifest, run_id, docs, now, fetch=not args.no_fetch,
                         account_lists_empty=not args.account_lists_present)
        run_dir = args.runs_dir / run_id
        write_prepare(run_dir, manifest, result, run_id, now)
        founder = result["founder"]
        print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "steps": result["steps"],
                          "founder_status": founder.status, "holds": len(founder.holds), "notes": len(founder.notes),
                          "matched_contacts": founder.matched_doc_ids, "halted": result["halted"]}, indent=2))
        return 2 if result["halted"] else 0

    run_dir = args.runs_dir / args.run_id
    if not (run_dir / "state.json").exists():
        raise GateError(f"no prepared run at {run_dir}; run prepare first")

    if args.cmd == "brief":
        memo = args.web_research.read_text() if args.web_research and args.web_research.exists() else None
        srcs = read_sources(args.web_sources.read_text()) if args.web_sources and args.web_sources.exists() else []
        summ = args.website_summary.read_text() if args.website_summary and args.website_summary.exists() else None
        ds = args.data_sources.read_text() if args.data_sources and args.data_sources.exists() else None
        cov = json.loads(args.coverage.read_text()) if args.coverage and args.coverage.exists() else None
        brief(run_dir, memo, srcs, summ, ds, cov)
        state = json.loads((run_dir / "state.json").read_text())
        print(json.dumps({"run_id": args.run_id, "proposal_prompt": str(run_dir / "proposal_prompt.md"),
                          "web_sources": len(state.get("web_sources") or []),
                          "web_research": "failed" if state.get("web_research_error") else "ok"}, indent=2))
        return 0

    docs = load_crm_dump(args.crm_dump)
    accounts = load_crm_dump(args.crm_dump, "accounts")
    master = load_master(args.master)
    summary = args.website_summary.read_text() if args.website_summary else None
    result = finalize(run_dir, args.proposal.read_text(), summary, args.composer_flag, master, docs, accounts, now)
    json_path, md_path = write_proposal_files(result["record"], args.proposals_dir, now)
    writes_path = write_finalize(run_dir, result, args.out_dir / f"compose_{args.run_id}", json_path, md_path, now)
    print(json.dumps({"run_id": args.run_id, "proposal_id": result["record"]["proposal_id"],
                      "status": result["record"]["founder_note"]["status"], "proposal": str(json_path),
                      "contacts": result["contact_ids"], "account": result["account_id"],
                      "writes": writes_path.as_posix(), "writes_planned": len(result["writes"]), "log": result["log"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
