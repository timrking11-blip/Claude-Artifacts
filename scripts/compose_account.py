#!/usr/bin/env python3
"""The deterministic legs of a button-driven account composition run.

The Intake page (https://claude.ai/artifact/BtU87XpWsN9VDNTFwidnA3) writes a
run manifest and wakes the session that owns this repo. That session runs two
commands here and does the two language-model legs itself (summarise the
page, draft the proposal). No ADK, no API key, no GCP.

  prepare  <manifest.json> --run-id <id> --crm-dump <dump>
      Re-gates the manifest, runs find_account / list_account_contacts /
      assess_ledger_quality from the agent's pure-Python ledger tools, fetches
      the page (honouring on_fetch_error), writes the warehouse sentinel,
      computes the founder note, and writes data/runs/<id>/{manifest,state,
      founder,run_update}.json plus prompts.md -- the two prompts the session
      needs, filled in. Exit 2 when the manifest fails its gate or the run is
      halted for operator review.

  finalize <run-id> --proposal <draft.md> [--website-summary <file>]
           [--composer-flag <text>]... --crm-dump <dump>
      Validates the draft exactly as the agent's write_proposal tool does
      (five sections, no money), writes data/proposals/<slug>-<date>.{json,md}
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
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from crm import config  # noqa: E402
from crm.crm_sync import load_crm_dump, pinned, system_activity, utcnow_iso  # noqa: E402
from crm.founder_note import assess  # noqa: E402
from crm.master import load_master  # noqa: E402
from crm.schema import normalize_domain  # noqa: E402

sys.path.insert(0, str(config.AGENT_DIR))
from account_research.sub_agents.prequal_agent_prompt import PROMPT as PREQUAL_PROMPT  # noqa: E402
from account_research.sub_agents.summarize_page_agent_prompt import PROMPT as SUMMARY_PROMPT  # noqa: E402
from account_research.tools import fetch_page, ledger  # noqa: E402
from account_research.tools.write_proposal import _MONEY, missing_sections, slugify  # noqa: E402

import push_proposals_to_crm  # noqa: E402

WAREHOUSE_SENTINEL = "not available"
STEP_ORDER = ("find_account", "list_account_contacts", "assess_ledger_quality", "fetch_page",
              "summarize_page", "warehouse_findings", "compose_proposal", "crm_write")

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
        state["account"] = {"key": None, "name": acct.get("name"), "domain": normalize_domain(acct.get("domain")),
                            "contact_count": 0, "industry": None, "employee_count": None, "in_ledger": False}
    state["account"]["crm_account_id"] = acct.get("crm_account_id")
    return outcome


def prepare(manifest: dict[str, Any], run_id: str, docs: dict[str, dict[str, Any]], now: datetime,
            *, fetch: bool = True, account_lists_empty: bool = True) -> dict[str, Any]:
    """Run the deterministic legs. Returns {state, steps, founder, halted}."""
    gate(manifest)
    m_state = manifest["state"]
    state: dict[str, Any] = {"request_text": (manifest.get("request") or {}).get("text") or ""}
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


def prompts_for(state: dict[str, Any]) -> tuple[str, str]:
    """The summariser prompt and the prequal prompt, filled from state."""
    summary = _fill(SUMMARY_PROMPT, {"page_contents": state.get("page_contents") or ""})
    prequal = _fill(PREQUAL_PROMPT, {
        "request_text": state.get("request_text") or "",
        "account": {k: v for k, v in (state.get("account") or {}).items() if k not in ("key",)},
        "account_contacts": state.get("account_contacts") or [],
        "ledger_quality": state.get("ledger_quality") or {},
        "website_summary": state.get("website_summary") or "",
        "warehouse_findings": state.get("warehouse_findings") or "",
    })
    tail = prequal.find("When the draft is complete, call the write_proposal tool")
    if tail != -1:
        prequal = prequal[:tail] + ("Return only the Markdown, nothing before or after it. The session saves it "
                                    "with `scripts/compose_account.py finalize`, which refuses a draft that is "
                                    "missing a heading or mentions money.\n")
    return summary, prequal


def write_prepare(run_dir: Path, manifest: dict[str, Any], result: dict[str, Any], run_id: str, now: datetime) -> None:
    state = dict(result["state"])
    page = state.pop("page_contents", None)
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "state.json", state)
    if page:
        (run_dir / "page.txt").write_text(page)
    founder = result["founder"].as_dict()
    _write_json(run_dir / "founder.json", founder)
    summary, prequal = prompts_for(result["state"])
    (run_dir / "prompts.md").write_text(
        "# Prompts for run " + run_id + "\n\n## 1 · Summarise the page → website_summary\n\n"
        + ("(fetch_page did not run; skip this leg)\n" if not page else summary.strip() + "\n")
        + "\n\n## 2 · Draft the prequalification proposal\n\n"
        + "(fill <WEBSITE_SUMMARY> with the answer to prompt 1 before using this)\n\n" + prequal.strip() + "\n")
    _write_json(run_dir / "run_update.json", {
        "status": "halted" if result["halted"] else "running",
        "steps": result["steps"],
        "founder_note": founder["text"],
        "founder_status": founder["status"],
        "matched_contact_ids": founder["matched_doc_ids"],
        "account": {k: result["state"]["account"].get(k) for k in ("name", "domain", "in_ledger", "contact_count")},
        "prepared_at": _iso(now),
    })


# --------------------------------------------------------------- finalize ----

def proposal_record(state: dict[str, Any], manifest: dict[str, Any], run_id: str, proposal_md: str,
                    founder: dict[str, Any], composer_flags: list[str], now: datetime) -> dict[str, Any]:
    """Same shape as the agent's write_proposal tool, plus founder_note and run."""
    missing = missing_sections(proposal_md)
    if missing:
        raise GateError(f"proposal is missing section(s): {missing}")
    money = _MONEY.search(proposal_md)
    if money:
        raise GateError(f"proposal mentions money ({money.group(0)!r}); no rates are set")
    account = state["account"]
    request_text = state.get("request_text") or ""
    slug = slugify(account.get("name") or account.get("domain") or "account")
    pid = "prq_" + hashlib.sha256(f"{slug}|{request_text}|{now.date()}".encode()).hexdigest()[:12]
    holds = list(founder.get("holds") or []) + [f"Composer: {f}" for f in composer_flags if f.strip()]
    notes = list(founder.get("notes") or [])
    text = "\n".join([f"HOLD — {h}" for h in holds] + [f"Note — {n}" for n in notes]) or "Nothing extenuating; proceed as drafted."
    contacts = state.get("account_contacts") or []
    return {
        "proposal_id": pid,
        "generated_at": _iso(now),
        "model": os.getenv("ACCOUNT_RESEARCH_CLAUDE_MODEL", "session"),
        "run_id": run_id,
        "account": {"name": account.get("name"), "domain": account.get("domain")},
        "contact_ids": [c.get("contact_id") for c in contacts if c.get("contact_id")],
        "apollo_contact_ids": [c.get("apollo_contact_id") for c in contacts if c.get("apollo_contact_id")],
        "request_text": request_text,
        "request": manifest.get("request") or {},
        "founder_note": {"status": "needs_founder" if holds else "done", "holds": holds, "notes": notes, "text": text},
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
    line = (f"--- Prequalification proposal · {stamp[:10]} · {pid} --- "
            f"attached to {len(contact_ids)} contact(s); run {record['run_id']}; see contact notes.")
    wanted = (manifest["state"]["account"] or {}).get("crm_account_id")
    existing_id = wanted if wanted in accounts else next(
        (i for i, d in accounts.items() if domain and normalize_domain(d.get("domain") or d.get("website")) == domain), None)
    if existing_id:
        doc = accounts[existing_id]
        if pid in (doc.get("notes") or ""):
            return None
        notes = (doc.get("notes") or "").rstrip()
        data = {"notes": (notes + "\n\n" + line) if notes else line, "updated_at": stamp,
                "activity": system_activity(doc.get("activity"), f"Prequalification proposal drafted ({pid})", ts=stamp)}
        return pinned(doc, {"op": "update", "collection": "accounts", "doc_id": existing_id, "data": data})
    if not (acct.get("name") and domain):
        return None
    doc = dict(ACCOUNT_DEFAULTS)
    doc.update({"name": acct["name"], "domain": domain, "website": "https://" + domain, "notes": line,
                "activity": [{"ts": stamp, "type": "system", "text": f"Added by composition run {record['run_id']} — queued for Apollo upload"}],
                "flags": ["pending_apollo"], "created_at": stamp, "updated_at": stamp})
    return {"op": "set", "collection": "accounts", "doc_id": _mint_account_id(now), "data": doc}


def finalize(run_dir: Path, proposal_md: str, website_summary: str | None, composer_flags: list[str],
             master, docs: dict[str, dict[str, Any]], accounts: dict[str, dict[str, Any]],
             now: datetime) -> dict[str, Any]:
    """Validate, build the record, plan every CRM write. Pure apart from reading run_dir."""
    manifest = json.loads((run_dir / "manifest.json").read_text())
    state = json.loads((run_dir / "state.json").read_text())
    founder = json.loads((run_dir / "founder.json").read_text())
    run_id = run_dir.name
    if website_summary:
        state["website_summary"] = website_summary.strip()
    record = proposal_record(state, manifest, run_id, proposal_md, founder, composer_flags, now)
    writes, log = push_proposals_to_crm.plan([record], master, docs, now=_iso(now))
    contact_ids = [w["doc_id"] for w in writes]
    account_write = plan_account_write(record, manifest, accounts, contact_ids or founder.get("matched_doc_ids") or [], now)
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
                  "summarize_page": "done" if result["state"].get("website_summary") else "skipped",
                  "compose_proposal": "done", "crm_write": "pending" if entries else "nothing"},
        "founder_note": record["founder_note"]["text"],
        "founder_status": record["founder_note"]["status"],
        "proposal_id": record["proposal_id"],
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
    if args.master:
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
