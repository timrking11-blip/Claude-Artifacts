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

PROPOSAL = """## What we understand you're asking for
A second location.

## What we know about you
Example Co; Ada Lovelace, CTO.

## Where we can help
- A cost-to-serve model.

## What we'd need to qualify this
1. Which towns?

## Proposed next step
A short call with Ada.
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
    assert r["founder"].matched_doc_ids == ["ap_ada"]
    assert r["halted"] is False


def test_prepare_unknown_account_proceeds_with_a_note(ledger, dump):
    m = manifest(account={"name": "Brand New LLC", "domain": "brandnew.example", "crm_account_id": None})
    r = compose.prepare(m, "run_t", compose.load_crm_dump(dump), NOW, fetch=False)
    assert r["steps"]["find_account"] == "not_found"
    assert r["state"]["account"] == {"key": None, "name": "Brand New LLC", "domain": "brandnew.example",
                                     "contact_count": 0, "industry": None, "employee_count": None,
                                     "in_ledger": False, "crm_account_id": None}
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
    assert "skip this leg" in prompts, "no page fetched -> summariser leg skipped"
    assert "Ada Lovelace" in prompts and "Help us plan a second location." in prompts
    assert "write_proposal tool" not in prompts and "compose_account.py finalize" in prompts
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
        compose.finalize(run_dir, PROPOSAL.replace("## Proposed next step", "## Next"), None, [], master, docs, {}, NOW)
    with pytest.raises(SystemExit):
        compose.finalize(run_dir, PROPOSAL + "\nAbout $2,000 per month.\n", None, [], master, docs, {}, NOW)


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
    pid = res["record"]["proposal_id"]
    # Once the CRM carries the proposal, a re-run plans nothing.
    docs["ap_ada"]["proposal_ref"] = pid
    accounts["acc_1"]["notes"] += "\n\n" + acc["data"]["notes"].split("\n\n", 1)[1]
    again = compose.finalize(run_dir, PROPOSAL, None, [], master, docs, accounts, NOW)
    assert again["writes"] == [] and again["record"]["proposal_id"] == pid


def test_write_finalize_emits_batch_files_and_run_final(ledger, dump, tmp_path):
    run_dir = _prepared(ledger, dump, tmp_path)
    docs, master = compose.load_crm_dump(dump), load_master(ledger)
    res = compose.finalize(run_dir, PROPOSAL, None, [], master, docs, {}, NOW)
    json_path, md_path = compose.write_proposal_files(res["record"], tmp_path / "proposals", NOW)
    assert json_path.name == "example-co-2026-09-24.json" and "**Founder note**" in md_path.read_text()
    writes_path = compose.write_finalize(run_dir, res, tmp_path / "batch", json_path, md_path, NOW)
    entries = json.loads(writes_path.read_text())
    assert [e["collection"] for e in entries] == ["contacts", "accounts"]
    assert entries[0]["if_version"] == 4 and "if_version" not in entries[1]
    for e in entries:
        assert Path(e["file_path"]).exists() and "data" not in e
    final = json.loads((run_dir / "run_final.json").read_text())
    assert final["status"] == "done" and final["steps"]["compose_proposal"] == "done"
    assert final["crm"]["contact_ids"] == ["ap_ada"] and final["crm"]["writes_planned"] == 2
    assert final["proposal_markdown"].startswith("## What we understand")


def test_cli_prepare_then_finalize(ledger, dump, tmp_path):
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps(manifest()))
    rc = compose.main(["prepare", str(mpath), "--crm-dump", str(dump), "--runs-dir", str(tmp_path / "runs"),
                       "--no-fetch", "--now", "2026-09-24T20:00:00Z"])
    assert rc == 0
    draft = tmp_path / "draft.md"
    draft.write_text(PROPOSAL)
    rc = compose.main(["finalize", "run_t", "--proposal", str(draft), "--crm-dump", str(dump),
                       "--runs-dir", str(tmp_path / "runs"), "--proposals-dir", str(tmp_path / "proposals"),
                       "--out-dir", str(tmp_path / "batch"), "--master", str(ledger), "--now", "2026-09-24T20:05:00Z"])
    assert rc == 0
    assert (tmp_path / "batch" / "compose_run_t" / "writes.json").exists()
    assert (tmp_path / "runs" / "run_t" / "run_final.json").exists()
