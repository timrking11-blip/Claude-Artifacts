"""The Enrichment Broker's ledger and the activity rows the scorecard counts.

Both are money-and-numbers code: a wrong answer here spends credits nobody
approved or reports touches nobody sent. Each test pins one rule.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm import activity, broker  # noqa: E402
from crm.schema import SOURCE_APOLLO, SOURCE_EXPLORIUM, SOURCE_LINKEDIN, Contact  # noqa: E402

NOW = "2026-09-25T20:00:00Z"
LEDGER = {"providers": {"vibe": {"balance": 746, "floor": 200},
                        "apollo": {"limit": 280, "used": 271, "floor": 10},
                        "unfloored": {"balance": 500}}}


# ---------- field owners --------------------------------------------------------------

def test_field_owners_follow_the_trust_table():
    assert broker.field_owner("email") == SOURCE_APOLLO
    assert broker.field_owner("industry") == SOURCE_EXPLORIUM
    assert broker.field_owner("technologies") == SOURCE_EXPLORIUM
    assert broker.field_owner("title") == SOURCE_LINKEDIN
    assert broker.field_owner("seniority") == SOURCE_LINKEDIN
    assert broker.field_owner("company_domain") is None        # a tie: nobody owns it


def test_a_vendor_fills_blanks_but_overwrites_only_what_it_owns():
    rec = Contact(contact_id="c", email="a@b.co", industry="", title="CEO", phone="")
    answer = {"email": "other@b.co", "industry": "HVAC", "title": "Founder", "phone": "+1 555", "employee_count": 0}
    assert broker.owned_fields(rec, answer, SOURCE_EXPLORIUM) == {"industry": "HVAC", "phone": "+1 555"}
    rec.industry = "Plumbing"
    assert broker.owned_fields(rec, {"industry": "HVAC"}, SOURCE_EXPLORIUM) == {"industry": "HVAC"}   # it owns it
    assert broker.owned_fields(rec, {"industry": "HVAC"}, SOURCE_APOLLO) == {}                        # it does not


def test_explorium_fields_map_sparsely():
    got = broker.map_explorium({"job_title": "VP Ops", "number_of_employees": 40, "technologies": ["Stripe", ""],
                                "business_id": "b1", "linkedin": ""})
    assert got == {"title": "VP Ops", "employee_count": 40, "technologies": ["Stripe"], "explorium_business_id": "b1"}


# ---------- budget ---------------------------------------------------------------------

def test_budget_allows_a_spend_that_keeps_the_floor():
    ok = broker.budget_check(LEDGER, "vibe", 100)
    assert ok.ok and ok.headroom == 446


def test_budget_refuses_below_the_floor_and_on_anything_unknown():
    assert not broker.budget_check(LEDGER, "vibe", 600).ok                 # 746 - 600 < 200
    assert not broker.budget_check(LEDGER, "apollo", 5).ok                 # 9 left, floor 10
    assert "floor" in broker.budget_check(LEDGER, "unfloored", 1).reason   # the owner sets floors
    assert "balance" in broker.budget_check(LEDGER, "nobody", 1).reason
    assert "estimate" in broker.budget_check(LEDGER, "vibe", None).reason


def test_record_spend_moves_the_right_counter():
    after = broker.record_spend(LEDGER, "vibe", 50, NOW)
    assert after["providers"]["vibe"]["balance"] == 696
    after = broker.record_spend(LEDGER, "apollo", 2, NOW)
    assert after["providers"]["apollo"]["used"] == 273
    assert LEDGER["providers"]["vibe"]["balance"] == 746                   # pure


# ---------- jobs ----------------------------------------------------------------------

def test_a_job_is_estimated_then_approved_or_queued():
    job = broker.new_job("vibe", "enrich-prospects", ["p2", "p1"], 100, NOW)
    assert job["status"] == "estimated" and job["target_count"] == 2 and job["targets"] == ["p1", "p2"]
    assert job["job_id"].startswith("job_20260925_vibe_enrich_prospects_")
    approved = broker.approve(job, LEDGER, "owner", NOW)
    assert approved["status"] == "approved" and approved["approved_by"] == "owner"
    big = broker.new_job("vibe", "enrich-prospects", ["p1"], 700, NOW)
    queued = broker.approve(big, LEDGER, "owner", NOW)
    assert queued["status"] == "queued" and queued["sentinel"] == broker.PENDING_BUDGET


def test_only_an_approved_job_settles():
    job = broker.new_job("vibe", "enrich-prospects", ["p1"], 10, NOW)
    with pytest.raises(ValueError):
        broker.settle(job, 10, NOW)
    done = broker.settle(broker.approve(job, LEDGER, "owner", NOW), 9, NOW, dataset_id="ds_1")
    assert done["status"] == "done" and done["spent"] == 9 and done["dataset_id"] == "ds_1"


# ---------- activity ------------------------------------------------------------------

def test_rows_are_validated_and_trimmed():
    r = activity.row(NOW, "email", "out", "  Quick   question  " + "x" * 200, "gmail", "m1")
    assert r["channel_ref"] == "gmail:m1" and len(r["text"]) == activity.TEXT_LIMIT
    for bad in (("note", "out", "gmail", "m"), ("email", "sideways", "gmail", "m"), ("email", "out", "fax", "m"),
                ("email", "out", "gmail", "")):
        with pytest.raises(ValueError):
            activity.row(NOW, bad[0], bad[1], "t", bad[2], bad[3])


def test_capture_is_idempotent_and_respects_hand_logged_rows():
    existing = [{"ts": "2026-09-17T12:19:45Z", "type": "email", "text": "sent the intro"}]    # logged by hand
    rows = [activity.row("2026-09-17T12:00:00Z", "email", "out", "Intro", "gmail", "m1"),   # same day, same type
            activity.row("2026-09-24T09:00:00Z", "reply", "in", "Re: Intro", "gmail", "m2")]
    merged, added = activity.merge_rows(existing, rows)
    assert added == 1 and merged[-1]["channel_ref"] == "gmail:m2"
    again, added_again = activity.merge_rows(merged, rows)
    assert added_again == 0 and again == merged


def test_plan_capture_only_touches_activity_and_never_creates_a_contact():
    docs = {"ap_ada": {"email": "Ada@Acme.example", "activity": [], "_version": 4}}
    rows = {"ada@acme.example": [activity.row(NOW, "email", "out", "Hello", "apollo", "e1")],
            "stranger@else.example": [activity.row(NOW, "email", "out", "Hi", "gmail", "m9")]}
    writes = activity.plan_capture(docs, rows)
    assert len(writes) == 1 and writes[0]["doc_id"] == "ap_ada" and writes[0]["if_version"] == 4
    assert set(writes[0]["data"]) == {"activity"}


def test_scorecard_counts_contacts_from_activity_alone():
    docs = {
        "a": {"stage": "new", "activity": [{"ts": "2026-09-20T10:00:00Z", "type": "email", "direction": "out", "text": "x"},
                                           {"ts": "2026-09-22T10:00:00Z", "type": "reply", "direction": "in", "text": "y"}]},
        "b": {"stage": "meeting", "activity": [{"ts": "2026-09-21T10:00:00Z", "type": "email", "text": "by hand"},
                                               {"ts": "2026-09-23T10:00:00Z", "type": "meeting", "text": "call"}]},
        "c": {"stage": "won", "activity": [{"ts": "2026-09-01T10:00:00Z", "type": "linkedin", "text": "Reply (Accepted): yes"}]},
        "d": {"stage": "replied", "activity": [{"ts": "2026-09-20T10:00:00Z", "type": "system", "text": "Apollo sync"}]},
    }
    card = activity.scorecard(docs)
    assert card["first_touches"] == 2 and card["replies"] == 2 and card["calls_booked"] == 1
    assert card["reply_rate"] == 1.0
    windowed = activity.scorecard(docs, since="2026-09-17")
    assert windowed["replies"] == 1                                     # c's reply predates the window
