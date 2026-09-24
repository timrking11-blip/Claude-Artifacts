"""The data layer -> CRM System bridge: validation gate, enrichment push, proposal push.

Everything here runs on a three-record master and a three-document dump built
in a temp dir. No network, no credentials, no ArtifactData -- these test the
*plans* the scripts produce, which is the part that can silently damage a
human's CRM if it is wrong.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm.crm_sync import (  # noqa: E402
    CRM_OWNED_FIELDS,
    PROPOSAL_READY_FLAG,
    PROPOSAL_STATUSES,
    load_crm_dump,
    proposal_ready,
    write_batches,
)
from crm.master import save_master  # noqa: E402
from crm.schema import SOURCE_APOLLO, SOURCE_EXPLORIUM, Contact  # noqa: E402


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


validate_sync = _load_script("validate_sync")
push_enrichment = _load_script("push_enrichment_to_crm")
push_proposals = _load_script("push_proposals_to_crm")


# ---------- fixtures ----------------------------------------------------------

def _prov(source, **fields):
    return {f: {"source": source, "observed_at": "2026-09-20T00:00:00+00:00"} for f in fields} | fields


@pytest.fixture
def master(tmp_path):
    ada = Contact(contact_id="c_ada", first_name="Ada", email="ada@example.com",
                  apollo_contact_id="ap_ada", seniority="c_suite", industry="software",
                  employee_count=40, location="Boston, MA", sources=[SOURCE_APOLLO, SOURCE_EXPLORIUM],
                  provenance={"seniority": {"source": SOURCE_EXPLORIUM, "observed_at": "x"},
                              "industry": {"source": SOURCE_EXPLORIUM, "observed_at": "x"},
                              "employee_count": {"source": SOURCE_EXPLORIUM, "observed_at": "x"},
                              "location": {"source": SOURCE_APOLLO, "observed_at": "x"}})
    bob = Contact(contact_id="c_bob", first_name="Bob", email="bob@example.com",
                  apollo_contact_id="ap_bob", sources=[SOURCE_APOLLO], provenance={})
    cy = Contact(contact_id="c_cy", first_name="Cy", email="cy@other.example",
                 company_domain="other.example", sources=[SOURCE_APOLLO], provenance={})
    path = tmp_path / "contacts.json"
    save_master([ada, bob, cy], path)
    return path


def _doc(**kw):
    base = {"stage": "new", "flags": [], "activity": [], "notes": "", "qualified": False,
            "email": "", "city": "", "state": "", "industry": "", "employees": "",
            "linkedin": "", "website": ""}
    base.update(kw)
    return base


@pytest.fixture
def dump(tmp_path):
    d = tmp_path / "dump" / "contacts"
    d.mkdir(parents=True)
    # ada: joins by apollo id; qualified, has email, has a note -> proposal-ready.
    (d / "ap_ada.json").write_text(json.dumps(_doc(
        email="ada@example.com", qualified=True,
        activity=[{"ts": "t", "type": "note", "text": "met at event"}])))
    # bob: qualified with email but never touched -> not ready.
    (d / "ap_bob.json").write_text(json.dumps(_doc(email="bob@example.com", qualified=True)))
    # zed: not in master at all; ready but flagged disqualified -> not ready.
    (d / "ap_zed.json").write_text(json.dumps(_doc(
        email="zed@example.com", qualified=True, flags=["disqualified"],
        activity=[{"ts": "t", "type": "call", "text": "spoke"}], website="other.example")))
    return tmp_path / "dump"


# ---------- proposal_ready: each criterion alone -------------------------------

def test_ready_needs_every_criterion():
    good = _doc(email="a@b.co", qualified=True, activity=[{"type": "note", "text": "x"}])
    assert proposal_ready(good)
    assert not proposal_ready(good | {"qualified": False})
    assert not proposal_ready(good | {"email": ""})
    assert not proposal_ready(good | {"flags": ["disqualified"]})
    assert not proposal_ready(good | {"flags": ["removed_from_list"]})
    assert not proposal_ready(good | {"activity": [{"type": "system", "text": "sync"}]})
    assert not proposal_ready(good | {"activity": []})


# ---------- enrichment push ------------------------------------------------------

def test_enrichment_fills_empty_fields_only_and_flags(master, dump):
    docs = load_crm_dump(dump)
    from crm.master import load_master
    writes = push_enrichment.plan(load_master(master), docs, now="2026-09-24T12:00:00Z")
    by_id = {w["doc_id"]: w["data"] for w in writes}

    ada = by_id["ap_ada"]
    assert ada["seniority"] == "c_suite" and ada["industry"] == "software"
    assert ada["employees"] == "40"                      # CRM stores a string
    assert ada["city"] == "Boston" and ada["state"] == "MA"
    assert PROPOSAL_READY_FLAG in ada["flags"]
    assert ada["activity"][-1]["type"] == "system"
    assert "Enriched" in ada["activity"][-1]["text"] and "proposal-ready" in ada["activity"][-1]["text"]

    assert "ap_bob" not in by_id                          # nothing new, not ready -> no write
    assert "ap_zed" not in by_id                          # not in master, disqualified -> no write


def test_enrichment_never_overwrites_a_crm_value(master, dump):
    docs = load_crm_dump(dump)
    docs["ap_ada"]["industry"] = "aerospace"              # the human already set it
    from crm.master import load_master
    writes = push_enrichment.plan(load_master(master), docs)
    ada = {w["doc_id"]: w["data"] for w in writes}["ap_ada"]
    assert "industry" not in ada
    assert ada["seniority"] == "c_suite"                  # still fills the empty ones


def test_enrichment_never_emits_owned_fields(master, dump):
    from crm.master import load_master
    writes = push_enrichment.plan(load_master(master), load_crm_dump(dump))
    for w in writes:
        touched = set(w["data"]) & CRM_OWNED_FIELDS
        assert not touched, f"{w['doc_id']} would write {touched}"


def test_enrichment_is_idempotent(master, dump):
    from crm.master import load_master
    docs = load_crm_dump(dump)
    first = push_enrichment.plan(load_master(master), docs)
    for w in first:                                       # apply the plan in memory
        docs[w["doc_id"]].update(w["data"])
    second = push_enrichment.plan(load_master(master), docs)
    assert second == []


def test_flag_is_removed_when_no_longer_ready(master, dump):
    from crm.master import load_master
    docs = load_crm_dump(dump)
    docs["ap_bob"]["flags"] = [PROPOSAL_READY_FLAG]      # stale flag from an earlier week
    writes = push_enrichment.plan(load_master(master), docs)
    bob = {w["doc_id"]: w["data"] for w in writes}["ap_bob"]
    assert bob["flags"] == []
    assert "No longer" in bob["activity"][-1]["text"]


# ---------- proposal push --------------------------------------------------------

def _proposal(pid="p1", **kw):
    base = {"proposal_id": pid, "account": {"name": "Example", "domain": "example.com"},
            "apollo_contact_ids": ["ap_ada"], "contact_ids": ["c_ada"],
            "request_text": "Need help sizing the northeast market.\nMore detail.",
            "proposal_markdown": "# Prequalification\n\nWe understand ...", "generated_at": "2026-09-24T00:00:00Z"}
    base.update(kw)
    return base


def test_proposal_appends_to_notes_and_sets_status(master, dump):
    from crm.master import load_master
    docs = load_crm_dump(dump)
    docs["ap_ada"]["notes"] = "Existing human note."
    writes, log = push_proposals.plan([_proposal()], load_master(master), docs, now="2026-09-24T12:00:00Z")
    assert len(writes) == 1 and writes[0]["doc_id"] == "ap_ada"
    data = writes[0]["data"]
    assert data["notes"].startswith("Existing human note.")     # never overwritten
    assert "--- Prequalification proposal · 2026-09-24 · p1 ---" in data["notes"]
    assert data["notes"].rstrip().endswith("We understand ...")
    assert data["proposal_status"] == "drafted"
    assert data["proposal_scope"] == "Need help sizing the northeast market."
    assert data["proposal_ref"] == "p1"
    assert "1 contact(s) updated" in log[0]


def test_proposal_never_regresses_an_advanced_status(master, dump):
    from crm.master import load_master
    docs = load_crm_dump(dump)
    docs["ap_ada"]["proposal_status"] = "sent"
    writes, _ = push_proposals.plan([_proposal()], load_master(master), docs)
    assert "proposal_status" not in writes[0]["data"]
    assert writes[0]["data"]["proposal_ref"] == "p1"


def test_proposal_is_idempotent(master, dump):
    from crm.master import load_master
    docs = load_crm_dump(dump)
    docs["ap_ada"]["proposal_ref"] = "p1"
    writes, log = push_proposals.plan([_proposal()], load_master(master), docs)
    assert writes == []
    assert "1 already carried it" in log[0]


def test_proposal_falls_back_to_domain(master, dump):
    from crm.master import load_master
    docs = load_crm_dump(dump)
    p = _proposal(pid="p2", apollo_contact_ids=[], contact_ids=[], account={"name": "Other", "domain": "other.example"})
    writes, _ = push_proposals.plan([p], load_master(master), docs)
    assert [w["doc_id"] for w in writes] == ["ap_zed"]


def test_proposal_with_no_match_writes_nothing(master, dump):
    from crm.master import load_master
    p = _proposal(pid="p3", apollo_contact_ids=[], contact_ids=[], account={"name": "Nobody", "domain": "nobody.example"})
    writes, log = push_proposals.plan([p], load_master(master), load_crm_dump(dump))
    assert writes == [] and "no CRM contact matched" in log[0]


# ---------- validation gate ------------------------------------------------------

def test_validate_passes_on_clean_data(master, dump):
    report = validate_sync.run(master, dump, min_coverage=0.5)
    assert report.ok, report.failures


def test_validate_fails_on_unknown_source(master, tmp_path):
    raw = json.loads(master.read_text())
    raw["contacts"][0]["provenance"]["seniority"]["source"] = "zoominfo"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw))
    report = validate_sync.run(bad, None, 0.9)
    assert not report.ok and any("unknown source" in f for f in report.failures)


def test_validate_fails_on_duplicate_apollo_id(master, tmp_path):
    raw = json.loads(master.read_text())
    raw["contacts"][1]["apollo_contact_id"] = raw["contacts"][0]["apollo_contact_id"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw))
    report = validate_sync.run(bad, None, 0.9)
    assert not report.ok and any("duplicate apollo_contact_id" in f for f in report.failures)


def test_validate_fails_on_bad_proposal_status(master, dump):
    (dump / "contacts" / "ap_ada.json").write_text(json.dumps(_doc(proposal_status="maybe")))
    report = validate_sync.run(master, dump, 0.5)
    assert any("proposal_status" in f for f in report.failures)
    assert "maybe" not in PROPOSAL_STATUSES


def test_validate_fails_below_coverage(master, dump):
    report = validate_sync.run(master, dump, min_coverage=0.99)   # zed is not in master: 2/3
    assert any("coverage" in f for f in report.failures)


# ---------- batch files ----------------------------------------------------------

def test_write_batches_splits_at_fifty_and_clears_stale(tmp_path):
    (tmp_path / "enrich_099.json").write_text("[]")               # stale from last week
    writes = [{"op": "update", "collection": "contacts", "doc_id": str(i), "data": {}} for i in range(120)]
    files = write_batches(writes, tmp_path, "enrich")
    assert [f.name for f in files] == ["enrich_000.json", "enrich_001.json", "enrich_002.json"]
    assert not (tmp_path / "enrich_099.json").exists()
    assert len(json.loads(files[2].read_text())) == 20
