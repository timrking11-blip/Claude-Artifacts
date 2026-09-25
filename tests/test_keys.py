"""Stored keys: CRM <-> master (master_id / crm_id) and person -> organization (org_id).

Phase 2 of the architecture blueprint: no link between records is computed at
read time. These tests pin the three rules that make that true -- a key is
stored, an email or a company name never creates one, and a key that no
longer points anywhere fails loudly instead of quietly attaching elsewhere.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm.crm_sync import (  # noqa: E402
    PROPOSAL_READY_FLAG,
    REVIEW_ORG_FLAG,
    join_master,
    load_review,
    org_key,
    provenance_changed,
    provenance_view,
)
from crm.master import MergeReport, dedupe_by_vendor_id, load_master, merge_all, save_master  # noqa: E402
from crm.schema import SOURCE_APOLLO, Contact  # noqa: E402


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod              # a script's dataclasses resolve their annotations through it
    spec.loader.exec_module(mod)
    return mod


push = _load_script("push_enrichment_to_crm")
backfill = _load_script("backfill_keys")
validate = _load_script("validate_sync")
merge_script = _load_script("merge_master")
proposals = _load_script("push_proposals_to_crm")

PROV = {"source": SOURCE_APOLLO, "observed_at": "2026-09-17T14:06:10+00:00"}


def _master():
    return [
        Contact(contact_id="c_ada", first_name="Ada", email="ada@acme.example", apollo_contact_id="ap_ada",
                title="CEO", company_name="Acme", provenance={"title": PROV, "company_name": PROV}),
        Contact(contact_id="c_bob", first_name="Bob", email="bob@bolt.example", apollo_contact_id="ap_bob"),
        Contact(contact_id="c_cy", first_name="Cy", email="cy@cyan.example"),   # no Apollo id
    ]


def _doc(**kw):
    base = {"stage": "new", "flags": [], "activity": [], "notes": "", "email": "", "website": "", "company": ""}
    base.update(kw)
    return base


# ---------- join_master ----------------------------------------------------------

def test_join_uses_stored_key_then_apollo_id_and_never_email():
    docs = {"ap_ada": _doc(master_id="c_ada"), "ap_bob": _doc(), "crm_cy": _doc(email="CY@cyan.example")}
    j = join_master(_master(), docs)
    assert j.how == {"ap_ada": "master_id", "ap_bob": "apollo_id"}
    assert "crm_cy" not in j.joined                      # an email match is not a join ...
    assert j.email_only["crm_cy"].contact_id == "c_cy"   # ... it is reported for a logged backfill


def test_join_reports_a_dangling_or_disagreeing_key():
    docs = {"ap_ada": _doc(master_id="c_bob"), "ap_zed": _doc(master_id="c_gone")}
    j = join_master(_master(), docs)
    assert j.disagree == {"ap_ada": ("c_bob", "c_ada")}
    assert j.dangling == {"ap_zed": "c_gone"}
    assert not j.joined


# ---------- org_key ---------------------------------------------------------------

ACCOUNTS = {"acc_acme": {"name": "Acme", "domain": "acme.example"},
            "acc_mech": {"name": "Acme Mechanical", "domain": "acmemech.example"}}


def test_org_key_links_on_an_exact_domain_only():
    assert org_key(_doc(website="https://www.acme.example/about", company="Acme Inc"), ACCOUNTS) == ("acc_acme", False)
    assert org_key(_doc(website="acmemech.example"), ACCOUNTS) == ("acc_mech", False)
    assert org_key(_doc(website="sub.acme.example"), ACCOUNTS) == (None, False)   # a subdomain is not the domain


def test_org_key_never_links_by_name():
    # A name equal to an account's, on another domain: flagged, never linked.
    assert org_key(_doc(website="acme.other", company="Acme"), ACCOUNTS) == (None, True)
    # A name that merely contains an account's name: neither linked nor flagged.
    assert org_key(_doc(website="", company="Acme Roofing"), ACCOUNTS) == (None, False)


# ---------- the push's key plan ---------------------------------------------------

def test_push_writes_keys_without_activity_or_updated_at():
    docs = {"ap_ada": _doc(website="acme.example"), "ap_bob": _doc(company="Acme", website="bolt.example")}
    writes = {w["doc_id"]: w["data"] for w in push.plan(_master(), docs, accounts=ACCOUNTS, review={}, keys_only=True)}
    ada, bob = writes["ap_ada"], writes["ap_bob"]
    assert ada["master_id"] == "c_ada" and ada["org_id"] == "acc_acme"
    assert ada["provenance"]["title"] == {"value": "CEO", "source": "apollo", "observed_at": PROV["observed_at"]}
    assert "held" not in ada                             # empty queue, and the doc has none
    assert bob == {"master_id": "c_bob", "flags": [REVIEW_ORG_FLAG]}
    for data in writes.values():
        assert "activity" not in data and "updated_at" not in data


def test_keys_only_leaves_enrichment_and_the_proposal_flag_alone():
    docs = {"ap_ada": _doc(qualified=True, email="ada@acme.example", activity=[{"type": "note", "text": "x"}])}
    keys_only = push.plan(_master(), docs, keys_only=True)[0]["data"]
    assert "flags" not in keys_only and "activity" not in keys_only
    full = push.plan(_master(), docs)[0]["data"]
    assert PROPOSAL_READY_FLAG in full["flags"] and full["master_id"] == "c_ada"


def test_push_key_plan_is_idempotent_and_ignores_a_reaffirmed_date():
    docs = {"ap_ada": _doc(website="acme.example")}
    for w in push.plan(_master(), docs, accounts=ACCOUNTS, review={}, keys_only=True):
        docs[w["doc_id"]].update(w["data"])
    master = _master()
    master[0].provenance = {k: v | {"observed_at": "2026-09-28T06:00:00+00:00"} for k, v in master[0].provenance.items()}
    assert push.plan(master, docs, accounts=ACCOUNTS, review={}, keys_only=True) == []
    master[0].title = "Chair"                            # a value moved: that is a change
    again = push.plan(master, docs, accounts=ACCOUNTS, review={}, keys_only=True)
    assert again and again[0]["data"]["provenance"]["title"]["value"] == "Chair"


def test_org_id_is_cleared_only_when_the_accounts_were_dumped():
    docs = {"ap_ada": _doc(org_id="acc_old", website="gone.example")}
    assert push.plan(_master(), docs, accounts=None, keys_only=True)[0]["data"].get("org_id") is None
    cleared = push.plan(_master(), docs, accounts=ACCOUNTS, keys_only=True)[0]["data"]
    assert cleared["org_id"] == {"__delete__": True}


def test_held_conflicts_come_from_the_review_queue(tmp_path):
    path = tmp_path / "review.json"
    path.write_text(json.dumps({"conflicts_held": [
        {"contact_id": "c_ada", "field": "title", "kept": "CEO", "rejected": "Founder", "source": "explorium"}],
        "ambiguous_matches": [{"keys": ["email:x@y.z"], "candidates": ["c_ada", "c_bob"], "source": "apollo"}]}))
    review = load_review(path)
    assert [h["kind"] for h in review["c_ada"]] == ["conflict", "ambiguous"]
    docs = {"ap_ada": _doc(master_id="c_ada")}
    held = push.plan(_master(), docs, review=review, keys_only=True)[0]["data"]["held"]
    assert held[0]["rejected"] == "Founder"
    assert load_review(tmp_path / "absent.json") is None  # no queue file: `held` is left as it is


def test_provenance_view_skips_empty_values_and_unsourced_fields():
    rec = Contact(contact_id="c", title="", company_name="Acme",
                  provenance={"title": PROV, "company_name": PROV, "industry": {"observed_at": "x"}})
    assert list(provenance_view(rec)) == ["company_name"]
    assert not provenance_changed({"company_name": {"value": "Acme", "source": "apollo", "observed_at": "old"}},
                                  provenance_view(rec))


# ---------- backfill_keys ---------------------------------------------------------

def test_backfill_keys_both_sides_and_logs_an_email_key():
    docs = {"ap_ada": _doc(master_id="c_ada"), "ap_bob": _doc(), "crm_cy": _doc(email="cy@cyan.example",
                                                                                name="Cy Cyan", company="Cyan")}
    p = backfill.plan(_master(), docs)
    assert {w["doc_id"]: w["data"] for w in p.crm_writes} == {"ap_bob": {"master_id": "c_bob"},
                                                             "crm_cy": {"master_id": "c_cy"}}
    assert p.by_apollo == 1 and p.by_email == ["Cy Cyan (Cyan) -> c_cy"] and p.already == 1
    assert p.master_keys == {"c_ada": "ap_ada", "c_bob": "ap_bob", "c_cy": "crm_cy"}
    entry = backfill.changelog_entry(p, "2026-09-25T00:00:00+00:00")
    assert "2 CRM contact(s) given master_id (1 by Apollo id, 1 by email)" in entry
    assert "keyed by email, once: Cy Cyan (Cyan) -> c_cy" in entry


def test_backfill_leaves_a_contested_row_unkeyed():
    docs = {"crm_one": _doc(email="cy@cyan.example"), "crm_two": _doc(master_id="c_cy")}
    p = backfill.plan(_master(), docs)
    assert not p.crm_writes and "c_cy" not in p.master_keys
    assert any("claimed by 2 CRM contacts" in s for s in p.skipped)


def test_backfill_is_idempotent():
    master = _master()
    docs = {"ap_ada": _doc(), "ap_bob": _doc()}
    p = backfill.plan(master, docs)
    for w in p.crm_writes:
        docs[w["doc_id"]].update(w["data"])
    for rec in master:
        rec.crm_id = p.master_keys.get(rec.contact_id, rec.crm_id)
    again = backfill.plan(master, docs)
    assert not again.crm_writes and not again.master_keys and again.already == 2


# ---------- validate_sync ---------------------------------------------------------

@pytest.fixture
def files(tmp_path):
    path = tmp_path / "contacts.json"
    save_master(_master(), path)
    dump = tmp_path / "dump" / "contacts"
    dump.mkdir(parents=True)
    return path, dump


def test_validate_fails_on_a_broken_key_but_not_a_missing_one(files):
    path, dump = files
    (dump / "ap_ada.json").write_text(json.dumps(_doc(master_id="c_ada")))
    (dump / "ap_bob.json").write_text(json.dumps(_doc()))                      # not keyed yet: a fact
    report = validate.run(path, dump.parent, 0.5)
    assert report.ok, report.failures
    (dump / "ap_bob.json").write_text(json.dumps(_doc(master_id="c_ada")))     # disagrees with its Apollo id
    report = validate.run(path, dump.parent, 0.5)
    assert any("disagrees" in f for f in report.failures)


def test_validate_warns_on_an_email_only_match(files):
    path, dump = files
    (dump / "ap_ada.json").write_text(json.dumps(_doc()))
    (dump / "crm_cy.json").write_text(json.dumps(_doc(email="cy@cyan.example")))
    report = validate.run(path, dump.parent, 0.5)
    assert report.ok and any("email only" in w for w in report.warnings)


def test_validate_fails_on_a_duplicate_crm_id(tmp_path):
    master = _master()
    master[0].crm_id = master[1].crm_id = "ap_ada"
    path = tmp_path / "contacts.json"
    save_master(master, path)
    report = validate.run(path, None, 0.9)
    assert any("duplicate crm_id" in f for f in report.failures)


# ---------- the weekly merge carries crm_id and writes the queue -------------------

def test_weekly_merge_keeps_crm_id():
    master = _master()
    master[0].crm_id = "ap_ada"
    incoming = [Contact(apollo_contact_id="ap_ada", title="Chair", first_name="Ada")]
    merged, _ = merge_all(master, incoming, SOURCE_APOLLO, "2026-09-28T06:00:00+00:00")
    assert {c.contact_id: c.crm_id for c in merged}["c_ada"] == "ap_ada"
    # The older record is kept; a crm_id only the folded duplicate carried survives on it.
    for c in merged:
        if c.contact_id == "c_bob":
            c.first_seen = "2026-09-17T14:06:10+00:00"
    dup = Contact(contact_id="c_dup", apollo_contact_id="ap_bob", crm_id="ap_bob", first_seen="2026-09-30")
    folded, pairs = dedupe_by_vendor_id([*merged, dup])
    assert pairs == [("c_bob", "c_dup")]
    assert {c.contact_id: c.crm_id for c in folded}["c_bob"] == "ap_bob"


def test_merge_writes_the_review_queue(tmp_path):
    report = MergeReport()
    report.conflicts_held.append({"contact_id": "c_ada", "field": "title", "kept": "CEO", "rejected": "Founder",
                                  "source": "explorium"})
    path = tmp_path / "review.json"
    merge_script.write_review([("explorium", report)], path)
    assert load_review(path)["c_ada"][0]["kept"] == "CEO"


def test_round_trip_through_the_master_file_keeps_crm_id(tmp_path):
    master = _master()
    master[1].crm_id = "ap_bob"
    path = tmp_path / "contacts.json"
    save_master(master, path)
    assert {c.contact_id: c.crm_id for c in load_master(path)}["c_bob"] == "ap_bob"


# ---------- the proposal push finds contacts by stored key -------------------------

def test_proposal_reaches_a_contact_by_master_id_not_email():
    docs = {"crm_cy": _doc(email="cy@cyan.example"), "crm_cy2": _doc(master_id="c_cy")}
    p = {"proposal_id": "p1", "contact_ids": ["c_cy"], "apollo_contact_ids": [], "account": {}}
    assert proposals.targets_for(p, _master(), docs) == ["crm_cy2"]
