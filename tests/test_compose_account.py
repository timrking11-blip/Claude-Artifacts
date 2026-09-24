"""scripts/compose_account.py: the gate, prepare, finalize and the CRM plan.

Runs on a three-record ledger, a two-document CRM dump and no network. The
page fetch is disabled (`fetch=False`), which also exercises the
on_fetch_error branches.
"""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm.master import load_master, save_master  # noqa: E402
from crm.schema import SOURCE_APOLLO, Contact  # noqa: E402


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


compose = _load_script("compose_account")
NOW = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)

PROPOSAL = """# Example Co -- Prequalification Proposal
Prepared by Strategic Marketing Insights

## Engagement summary
By a date we set together, Example Co decides whether to open a second location.

## What we heard
You asked for help planning a second location.

| Signal | Source | What SMI reads into it |
| --- | --- | --- |
| Hiring techs | [careers](https://example.com/careers) | Capacity is the constraint. [supported] |

## Why now: the market and the economy
Service demand in the region grew in 2026 ([bls](https://www.bls.gov/ces)) [needs stipulation].

## The problem in front of Example Co
1. Service radius caps growth ([site](https://example.com/about)) [needs stipulation]

## Approach
**Territory scan** (3 weeks). Gate: Example Co approves the shortlist.

## What we'd need to qualify this
1. Which towns are in scope, and by when?

## Next step
A 30-minute call with Ada Lovelace, CTO.

## Sources
- https://example.com/careers
"""


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    ada = Contact(contact_id="c_ada", first_name="Ada", last_name="Lovelace", title="CTO", email="ada@example.com",
                  apollo_contact_id="ap_ada", company_name="Example Co", company_domain="example.com",
                  sources=[SOURCE_APOLLO], provenance={}, last_updated="2026-09-20T00:00:00+00:00")
    bob = Contact(contact_id="c_bob", first_name="Bob", apollo_contact_id="ap_bob", company_name="Example Co",
                  company_domain="example.com", sources=[SOURCE_APOLLO], provenance={},
                  last_updated="2026-09-20T00:00:00+00:00")
    cy = Contact(contact_id="c_cy", first_name="Cy", email="cy@other.example", company_name="Other",
                 company_domain="other.example", sources=[SOURCE_APOLLO], provenance={})
    path = tmp_path / "contacts.json"
    save_master([ada, bob, cy], path)
    monkeypatch.setenv("ACCOUNT_RESEARCH_LEDGER", str(path))
    return path


@pytest.fixture
def dump(tmp_path):
    d = tmp_path / "dump" / "contacts"
    d.mkdir(parents=True)
    (d / "ap_ada.json").write_text(json.dumps({
        "name": "Ada Lovelace", "email": "ada@example.com", "qualified": True, "stage": "new", "flags": [],
        "notes": "hand-written", "website": "example.com", "activity": [{"type": "note", "text": "met"}]}))
    (d / "ap_zed.json").write_text(json.dumps({
        "name": "Zed", "email": "zed@other.example", "qualified": True, "stage": "new", "flags": [],
        "notes": "", "website": "other.example", "activity": []}))
    (tmp_path / "dump" / "versions.json").write_text(json.dumps({"ap_ada": 4, "ap_zed": 2}))
    return tmp_path / "dump"


def manifest(**over):
    m = {
        "run": {"event": "agents-go-live", "run_id": "run_t"},
        "request": {"text": "Help us plan a second location.", "source_url": "https://linkedin.example/post/1",
                    "requester": {"name": "Ada Lovelace", "linkedin_url": ""}},
        "state": {
            "account": {"required": True, "name": "Example Co", "domain": "example.com", "crm_account_id": None},
            "account_contacts": {"include": True, "limit": "1"},
            "ledger_quality": {"include": True, "quality_floor": "fair"},
            "website_summary": {"include": True, "page_url": "https://example.com", "on_fetch_error": "store_state"},
            "warehouse_findings": {"include": True, "sentinel": "not available"},
        },
        "crm": {"disposition": "manual"},
    }
    for k, v in over.items():
        if k in ("account", "account_contacts", "ledger_quality", "website_summary", "warehouse_findings"):
            m["state"][k] = v
        elif k == "disposition":
            m["crm"]["disposition"] = v
        else:
            m[k] = v
    return m


# ---------- gate ------------------------------------------------------------

def test_gate_refuses_no_account_and_null_disposition(ledger, dump):
    docs = compose.load_crm_dump(dump)
    with pytest.raises(SystemExit) as e:
        compose.prepare(manifest(account={"name": None, "domain": None}), "run_t", docs, NOW, fetch=False)
    assert e.value.code == 2
    with pytest.raises(SystemExit):
        compose.prepare(manifest(disposition=None), "run_t", docs, NOW, fetch=False)


# ---------- prepare ---------------------------------------------------------

def test_prepare_runs_ledger_legs_and_respects_limit(ledger, dump):
    r = compose.prepare(manifest(), "run_t", compose.load_crm_dump(dump), NOW, fetch=False)
    s, steps = r["state"], r["steps"]
    assert steps["find_account"] == "done" and s["account"]["in_ledger"] is True
    assert s["account"]["domain"] == "example.com" and s["account"]["contact_count"] == 2
    assert len(s["account_contacts"]) == 1, "limit 1 caps the contacts stored"
    assert s["ledger_quality"]["contact_count"] == 2
    assert steps["fetch_page"] == "failed:store_state" and s["website_summary"].startswith("Website fetch failed")
    assert s["warehouse_findings"] == "not available" and steps["warehouse_findings"] == "sentinel"
    assert steps["compose_proposal"] == "pending" and steps["crm_write"] == "pending"
    assert steps["web_research"] == "pending", "the crawler runs even when our own fetch failed"
    assert s["request_id"] == "run_t" and s["lead_source"] == ""
    assert r["founder"].matched_doc_ids == ["ap_ada"]
    assert r["halted"] is False


def test_prepare_unknown_account_proceeds_with_a_note(ledger, dump):
    m = manifest(account={"name": "Brand New LLC", "domain": "brandnew.example", "crm_account_id": None})
    r = compose.prepare(m, "run_t", compose.load_crm_dump(dump), NOW, fetch=False)
    assert r["steps"]["find_account"] == "not_found"
    assert r["state"]["account"] == {"key": "domain:brandnew.example", "name": "Brand New LLC",
                                     "domain": "brandnew.example", "contact_count": 0, "industry": None,
                                     "employee_count": None, "in_ledger": False, "prospect": True,
                                     "crm_account_id": None}
    assert r["steps"]["list_account_contacts"] == "empty"
    assert any("not in the enriched data layer" in n for n in r["founder"].notes)
    assert any("No CRM contact matched" in n for n in r["founder"].notes)


def test_prepare_halt_on_fetch_error(ledger, dump):
    m = manifest(website_summary={"include": True, "page_url": "https://example.com", "on_fetch_error": "halt"})
    r = compose.prepare(m, "run_t", compose.load_crm_dump(dump), NOW, fetch=False)
    assert r["halted"] is True and r["steps"]["compose_proposal"] == "halted"
    assert "website_summary" not in r["state"]


def test_prepare_honours_opt_outs(ledger, dump):
    m = manifest(account_contacts={"include": False, "opted_out": True},
                 ledger_quality={"include": False, "opted_out": True},
                 website_summary={"include": False, "opted_out": True},
                 warehouse_findings={"include": False, "opted_out": True})
    r = compose.prepare(m, "run_t", compose.load_crm_dump(dump), NOW, fetch=False)
    assert {r["steps"][k] for k in ("list_account_contacts", "assess_ledger_quality", "fetch_page", "warehouse_findings")} == {"skipped"}
    assert "warehouse_findings" not in r["state"]
    assert r["founder"].matched_doc_ids == ["ap_ada"], "domain fallback still finds the contact"
    assert any("Opted out at intake" in n for n in r["founder"].notes)


def test_write_prepare_emits_prompts_and_run_update(ledger, dump, tmp_path):
    r = compose.prepare(manifest(), "run_t", compose.load_crm_dump(dump), NOW, fetch=False)
    run_dir = tmp_path / "runs" / "run_t"
    compose.write_prepare(run_dir, manifest(), r, "run_t", NOW)
    assert {p.name for p in run_dir.iterdir()} == {"manifest.json", "state.json", "founder.json", "prompts.md", "run_update.json"}
    prompts = (run_dir / "prompts.md").read_text()
    assert "research desk" in prompts and "Website: https://example.com" in prompts, "crawler brief is prompt 1"
    assert "skip this leg" in prompts, "no page fetched -> summariser leg skipped"
    assert "compose_account.py brief run_t" in prompts
    prompt = compose.brief(run_dir, "## Company\nExamples. ([site](https://example.com/about)) [supported]", [], None)
    assert "Ada Lovelace" in prompt and "Help us plan a second location." in prompt
    assert "https://example.com/about" in prompt, "sources come from the memo's links when no list is given"
    assert "write_proposal tool" not in prompt and "compose_account.py finalize" in prompt
    assert "{web_research" not in prompt and "{account" not in prompt, "every slot filled"
    assert (run_dir / "proposal_prompt.md").exists()
    upd = json.loads((run_dir / "run_update.json").read_text())
    assert upd["status"] == "running" and upd["steps"]["find_account"] == "done"
    assert upd["matched_contact_ids"] == ["ap_ada"] and upd["account"]["in_ledger"] is True


# ---------- finalize --------------------------------------------------------

def _prepared(ledger, dump, tmp_path, **over):
    m = manifest(**over)
    r = compose.prepare(m, "run_t", compose.load_crm_dump(dump), NOW, fetch=False)
    run_dir = tmp_path / "runs" / "run_t"
    compose.write_prepare(run_dir, m, r, "run_t", NOW)
    return run_dir


def test_finalize_refuses_missing_section_and_money(ledger, dump, tmp_path):
    run_dir = _prepared(ledger, dump, tmp_path)
    docs, master = compose.load_crm_dump(dump), load_master(ledger)
    with pytest.raises(SystemExit):
        compose.finalize(run_dir, PROPOSAL.replace("## Sources", "## Links"), None, [], master, docs, {}, NOW)
    with pytest.raises(SystemExit):
        compose.finalize(run_dir, PROPOSAL + "\nAbout $2,000 per month.\n", None, [], master, docs, {}, NOW)
    with pytest.raises(SystemExit):
        compose.finalize(run_dir, PROPOSAL + ("word " * 1000), None, [], master, docs, {}, NOW)
    compose.brief(run_dir, "memo", ["https://example.com/careers"], None)
    uncited = PROPOSAL.replace("[careers](https://example.com/careers)", "careers").replace(
        "([site](https://example.com/about)) ", "").replace("([bls](https://www.bls.gov/ces)) ", "").replace(
        "- https://example.com/careers", "- none")
    with pytest.raises(SystemExit):
        compose.finalize(run_dir, uncited, None, [], master, docs, {}, NOW)


def test_finalize_plans_contact_note_and_mints_account(ledger, dump, tmp_path):
    run_dir = _prepared(ledger, dump, tmp_path)
    docs, master = compose.load_crm_dump(dump), load_master(ledger)
    res = compose.finalize(run_dir, PROPOSAL, "Example Co makes examples.", ["Deadline is unrealistic"], master, docs, {}, NOW)
    rec = res["record"]
    assert rec["proposal_id"].startswith("prq_") and rec["run_id"] == "run_t"
    assert rec["founder_note"]["status"] == "needs_founder"
    assert rec["founder_note"]["holds"] == ["Composer: Deadline is unrealistic"]
    assert rec["request"]["source_url"] == "https://linkedin.example/post/1"
    assert res["state"]["website_summary"] == "Example Co makes examples."

    contact, account = res["writes"]
    assert contact["collection"] == "contacts" and contact["doc_id"] == "ap_ada" and contact["if_version"] == 4
    assert contact["data"]["notes"].startswith("hand-written\n\n--- Prequalification proposal")
    assert "Founder note:\nHOLD — Composer: Deadline is unrealistic" in contact["data"]["notes"]
    assert contact["data"]["proposal_status"] == "drafted" and contact["data"]["proposal_ref"] == rec["proposal_id"]
    assert "stage" not in contact["data"]

    assert account["op"] == "set" and account["collection"] == "accounts" and account["doc_id"].startswith("crm_20260924_")
    d = account["data"]
    assert d["name"] == "Example Co" and d["domain"] == "example.com" and d["website"] == "https://example.com"
    assert d["origin"] == "crm" and d["flags"] == ["pending_apollo"] and d["stage"] == "cold"
    assert rec["proposal_id"] in d["notes"] and d["activity"][0]["type"] == "system"
    assert d["proposal_ref"] == rec["proposal_id"] and "source" not in d, "not a LinkedIn lead"
    assert rec["sources"] == ["https://example.com/careers", "https://www.bls.gov/ces", "https://example.com/about"]
    assert "see contact notes" in d["notes"], "contacts matched -> account gets a pointer, not the text"
    assert set(compose.ACCOUNT_DEFAULTS) <= set(d)


def test_finalize_appends_to_existing_account_and_is_idempotent(ledger, dump, tmp_path):
    run_dir = _prepared(ledger, dump, tmp_path)
    docs, master = compose.load_crm_dump(dump), load_master(ledger)
    accounts = {"acc_1": {"name": "Example Co", "domain": "example.com", "stage": "warm", "notes": "keep",
                          "activity": [], "_version": 9}}
    res = compose.finalize(run_dir, PROPOSAL, None, [], master, docs, accounts, NOW)
    acc = [w for w in res["writes"] if w["collection"] == "accounts"][0]
    assert acc["op"] == "update" and acc["doc_id"] == "acc_1" and acc["if_version"] == 9
    assert acc["data"]["notes"].startswith("keep\n\n---") and "stage" not in acc["data"]
    assert acc["data"]["proposal_ref"] == res["record"]["proposal_id"]
    pid = res["record"]["proposal_id"]
    # Once the CRM carries the proposal, a re-run plans nothing.
    docs["ap_ada"]["proposal_ref"] = pid
    accounts["acc_1"]["proposal_ref"] = pid
    again = compose.finalize(run_dir, PROPOSAL, None, [], master, docs, accounts, NOW)
    assert again["writes"] == [] and again["record"]["proposal_id"] == pid


def test_write_finalize_emits_batch_files_and_run_final(ledger, dump, tmp_path):
    run_dir = _prepared(ledger, dump, tmp_path)
    docs, master = compose.load_crm_dump(dump), load_master(ledger)
    res = compose.finalize(run_dir, PROPOSAL, None, [], master, docs, {}, NOW)
    json_path, md_path = compose.write_proposal_files(res["record"], tmp_path / "proposals", NOW)
    assert json_path.name == "example-co-2026-09-24-run_t.json" and "**Founder note**" in md_path.read_text()
    writes_path = compose.write_finalize(run_dir, res, tmp_path / "batch", json_path, md_path, NOW)
    entries = json.loads(writes_path.read_text())
    assert [e["collection"] for e in entries] == ["contacts", "accounts"]
    assert entries[0]["if_version"] == 4 and "if_version" not in entries[1]
    for e in entries:
        assert Path(e["file_path"]).exists() and "data" not in e
    final = json.loads((run_dir / "run_final.json").read_text())
    assert final["status"] == "done" and final["steps"]["compose_proposal"] == "done"
    assert final["crm"]["contact_ids"] == ["ap_ada"] and final["crm"]["writes_planned"] == 2
    assert final["proposal_markdown"].startswith("# Example Co -- Prequalification Proposal")


def test_cli_prepare_then_finalize(ledger, dump, tmp_path):
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps(manifest()))
    rc = compose.main(["prepare", str(mpath), "--crm-dump", str(dump), "--runs-dir", str(tmp_path / "runs"),
                       "--no-fetch", "--now", "2026-09-24T20:00:00Z"])
    assert rc == 0
    memo = tmp_path / "memo.md"
    memo.write_text("## Company\nExamples ([site](https://example.com/about)) [supported]")
    cov = tmp_path / "coverage.json"
    cov.write_text(json.dumps({"apollo": "none: plan", "prospecting": "skipped: credit spend not allowed on the intake form"}))
    rc = compose.main(["brief", "run_t", "--web-research", str(memo), "--coverage", str(cov),
                       "--runs-dir", str(tmp_path / "runs")])
    assert rc == 0 and (tmp_path / "runs" / "run_t" / "proposal_prompt.md").exists()
    draft = tmp_path / "draft.md"
    draft.write_text(PROPOSAL)
    rc = compose.main(["finalize", "run_t", "--proposal", str(draft), "--crm-dump", str(dump),
                       "--runs-dir", str(tmp_path / "runs"), "--proposals-dir", str(tmp_path / "proposals"),
                       "--out-dir", str(tmp_path / "batch"), "--master", str(ledger), "--now", "2026-09-24T20:05:00Z"])
    assert rc == 0
    assert (tmp_path / "batch" / "compose_run_t" / "writes.json").exists()
    final = json.loads((tmp_path / "runs" / "run_t" / "run_final.json").read_text())
    assert final["steps"]["apollo"] == "empty" and final["steps"]["prospecting"] == "skipped"
    assert final["coverage"]["apollo"] == "none: plan" and len(final["sync_schedule"]) == 4
    rec = json.loads(next((tmp_path / "proposals").glob("*.json")).read_text())
    assert "Sync schedule" in rec["notes_appendix"] and "Mon 28 Sep 2026 11:00 UTC" in rec["notes_appendix"]


def test_linkedin_prospect_gets_the_proposal_on_its_account(ledger, dump, tmp_path):
    m = manifest(account={"name": "Brand New LLC", "domain": "brandnew.example", "crm_account_id": None,
                          "source": "linkedin"})
    m["crm"]["pre_qual"] = True
    r = compose.prepare(m, "run_p", compose.load_crm_dump(dump), NOW, fetch=False)
    assert r["state"]["lead_source"] == "linkedin" and r["state"]["account"]["prospect"] is True
    run_dir = tmp_path / "runs" / "run_p"
    compose.write_prepare(run_dir, m, r, "run_p", NOW)
    compose.brief(run_dir, "", [], None)
    draft = PROPOSAL.replace("Example Co", "Brand New LLC")
    for u in ("https://example.com/careers", "https://example.com/about"):
        draft = draft.replace(u, "https://www.fdic.gov/qbp")
    draft = draft.replace("You asked for help planning a second location.", "What the company does: not found.")
    res = compose.finalize(run_dir, draft, None, [], load_master(ledger), compose.load_crm_dump(dump), {}, NOW)
    rec = res["record"]
    assert rec["lead_source"] == "linkedin" and rec["account"]["prospect"] is True
    assert any("no sources" in n for n in rec["founder_note"]["notes"])
    assert any("not-found note" in h for h in rec["founder_note"]["holds"])
    assert [w["collection"] for w in res["writes"]] == ["accounts"], "no contacts -> the account only"
    d = res["writes"][0]["data"]
    assert d["source"] == "linkedin" and d["pre_qual"] is True and d["proposal_ref"] == rec["proposal_id"]
    assert "## Engagement summary" in d["notes"] and "Founder note:" in d["notes"]
    # The Monday catch-up sees proposal_ref on the account and does not add it again.
    push = compose.push_proposals_to_crm
    again, _ = push.plan([rec], load_master(ledger), compose.load_crm_dump(dump),
                         accounts={res["writes"][0]["doc_id"]: {**d, "domain": "brandnew.example"}})
    assert again == []


def test_accounts_dump_reads_its_own_versions_file(tmp_path):
    d = tmp_path / "dump" / "accounts"
    d.mkdir(parents=True)
    (d / "acc_1.json").write_text(json.dumps({"name": "A", "domain": "a.example"}))
    (tmp_path / "dump" / "versions.json").write_text(json.dumps({"acc_1": 99}))
    (tmp_path / "dump" / "versions_accounts.json").write_text(json.dumps({"acc_1": 5}))
    accs = compose.push_proposals_to_crm.load_accounts_dump(tmp_path / "dump")
    assert accs["acc_1"]["_version"] == 5



def test_second_finalize_of_a_run_is_refused(ledger, dump, tmp_path):
    run_dir = _prepared(ledger, dump, tmp_path)
    docs, master = compose.load_crm_dump(dump), load_master(ledger)
    first = compose.finalize(run_dir, PROPOSAL, None, [], master, docs, {}, NOW)
    jp, mp = compose.write_proposal_files(first["record"], tmp_path / "proposals", NOW)
    compose.write_finalize(run_dir, first, tmp_path / "batch", jp, mp, NOW)
    with pytest.raises(SystemExit):  # a changed proposal is a new run from the intake page
        compose.finalize(run_dir, PROPOSAL, None, [], master, docs, {}, NOW)


def test_lookalike_domain_in_research_or_citations_is_refused(ledger, dump, tmp_path):
    run_dir = _prepared(ledger, dump, tmp_path)
    docs, master = compose.load_crm_dump(dump), load_master(ledger)
    compose.brief(run_dir, "## Company\nExamples ([site](https://www.exampl.com/about)) [supported]", [], None)
    with pytest.raises(SystemExit):
        compose.finalize(run_dir, PROPOSAL, None, [], master, docs, {}, NOW)
    compose.brief(run_dir, "## Company\nExamples ([site](https://example.com/about)) [supported]", [], None)
    bad = PROPOSAL.replace("https://example.com/careers", "https://examplle.com/careers")
    with pytest.raises(SystemExit):
        compose.finalize(run_dir, bad, None, [], master, docs, {}, NOW)


def test_empty_means_empty(ledger, dump, tmp_path):
    m = manifest(account={"name": "Brand New LLC", "domain": "brandnew.example", "crm_account_id": None})
    r = compose.prepare(m, "run_e", compose.load_crm_dump(dump), NOW, fetch=False)
    run_dir = tmp_path / "runs" / "run_e"
    compose.write_prepare(run_dir, m, r, "run_e", NOW)
    compose.brief(run_dir, "## Gaps\nnothing on brandnew.example", [], None,
                  coverage={"apollo": "none: not in Apollo", "prospecting": "none: no match"})
    docs, master = compose.load_crm_dump(dump), load_master(ledger)
    draft = PROPOSAL.replace("Example Co", "Brand New LLC")
    with pytest.raises(SystemExit):  # cites example.com etc. about a company nothing was found on
        compose.finalize(run_dir, draft, None, [], master, docs, {}, NOW)
    ok = draft
    for u in ("https://example.com/careers", "https://example.com/about"):
        ok = ok.replace(u, "https://www.fdic.gov/qbp")
    ok = ok.replace("## What we heard\nYou asked for help planning a second location.",
                    "## What we heard\nWhat the company does: not found.")
    res = compose.finalize(run_dir, ok, None, [], master, docs, {}, NOW)
    assert any("not-found note" in h for h in res["record"]["founder_note"]["holds"])
    assert res["record"]["founder_note"]["status"] == "needs_founder"


def test_credit_spend_needs_the_intake_tick(ledger, dump, tmp_path):
    run_dir = _prepared(ledger, dump, tmp_path)
    docs, master = compose.load_crm_dump(dump), load_master(ledger)
    compose.brief(run_dir, "## Company\nExamples ([site](https://example.com/about)) [supported]", [], None,
                  coverage={"apollo": "ok: enriched (1 credit)"})
    with pytest.raises(SystemExit):
        compose.finalize(run_dir, PROPOSAL, None, [], master, docs, {}, NOW)
    m = manifest(); m["data_sources"] = {"allow_credit_spend": True}
    r = compose.prepare(m, "run_c", compose.load_crm_dump(dump), NOW, fetch=False)
    rd = tmp_path / "runs" / "run_c"
    compose.write_prepare(rd, m, r, "run_c", NOW)
    assert "Credit spend: ALLOWED" in (rd / "prompts.md").read_text()
    assert "NOT allowed" in (run_dir / "prompts.md").read_text()
    compose.brief(rd, "## Company\nExamples ([site](https://example.com/about)) [supported]", [], None,
                  coverage={"apollo": "ok: enriched (1 credit)"})
    assert compose.finalize(rd, PROPOSAL, None, [], master, docs, {}, NOW)["record"]["proposal_id"]
