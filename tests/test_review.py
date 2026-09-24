"""Each review criterion in crm/review.py, one at a time.

The review is what the sender reads before a button-drafted proposal goes
anywhere, so every line it can produce is pinned here against a small,
explicit fixture. No network, no files.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm.review import (  # noqa: E402
    STATUS_DONE,
    STATUS_NEEDS_REVIEW,
    assess,
    in_sync_window,
    match_crm_contacts,
    quality_score,
)

NOW = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)  # a Thursday


def manifest(**over):
    m = {
        "run": {"run_id": "run_t"},
        "request": {"text": "Can you help us plan a second location?", "requester": {"name": "Ada Lovelace"}},
        "state": {
            "account": {"name": "Example Co", "domain": "example.com", "crm_account_id": None},
            "account_contacts": {"include": True, "limit": "25"},
            "ledger_quality": {"include": True, "quality_floor": "fair"},
            "website_summary": {"include": True, "page_url": "https://example.com", "on_fetch_error": "store_state"},
            "warehouse_findings": {"include": True, "sentinel": "not available"},
        },
        "crm": {"disposition": "manual"},
    }
    for k, v in over.items():
        if k == "request_text":
            m["request"]["text"] = v
        elif k == "disposition":
            m["crm"]["disposition"] = v
        else:
            m["state"][k] = v
    return m


def state(**over):
    s = {
        "account": {"name": "Example Co", "domain": "example.com", "contact_count": 2, "in_ledger": True},
        "account_contacts": [{"contact_id": "c_ada", "name": "Ada", "apollo_contact_id": "ap_ada"}],
        "ledger_quality": {"contact_count": 2, "missing_email": [], "stale_over_90_days": []},
    }
    s.update(over)
    return s


def doc(**over):
    d = {"name": "Ada Lovelace", "email": "ada@example.com", "qualified": True, "stage": "new",
         "flags": [], "website": "example.com", "activity": [{"type": "note", "text": "met"}]}
    d.update(over)
    return d


def test_clean_run_is_done_with_no_lines():
    fn = assess(manifest(), state(), {"ap_ada": doc()}, NOW)
    assert fn.status == STATUS_DONE
    assert fn.holds == [] and fn.notes == []
    assert fn.matched_doc_ids == ["ap_ada"]
    assert "Nothing extenuating" in fn.text


@pytest.mark.parametrize("text", ["what's your rate?", "we have a $5,000 budget", "billed per hour", "send a quote"])
def test_money_in_request_holds(text):
    fn = assess(manifest(request_text=text), state(), {"ap_ada": doc()}, NOW)
    assert fn.status == STATUS_NEEDS_REVIEW
    assert any("money" in h for h in fn.holds)


def test_existing_proposal_ref_holds():
    fn = assess(manifest(), state(), {"ap_ada": doc(proposal_ref="prq_old", proposal_status="sent")}, NOW)
    assert any("already carries proposal prq_old" in h for h in fn.holds)


@pytest.mark.parametrize("flag", ["disqualified", "removed_from_list"])
def test_excluded_flag_holds(flag):
    fn = assess(manifest(), state(), {"ap_ada": doc(flags=[flag])}, NOW)
    assert any(flag in h for h in fn.holds)


@pytest.mark.parametrize("stage", ["meeting", "proposal", "won"])
def test_open_deal_stage_holds(stage):
    fn = assess(manifest(), state(), {"ap_ada": doc(stage=stage)}, NOW)
    assert any(f"stage '{stage}'" in h for h in fn.holds)


def test_apollo_disposition_with_empty_lists_holds():
    fn = assess(manifest(disposition="apollo"), state(), {"ap_ada": doc()}, NOW)
    assert any("account_lists is empty" in h for h in fn.holds)
    ok = assess(manifest(disposition="apollo"), state(), {"ap_ada": doc()}, NOW, account_lists_empty=False)
    assert ok.holds == []


def test_sync_window_is_monday_morning_eastern():
    # Mon 28 Sep 2026 07:30 ET == 11:30 UTC
    inside = datetime(2026, 9, 28, 11, 30, tzinfo=timezone.utc)
    assert in_sync_window(inside)
    assert not in_sync_window(datetime(2026, 9, 28, 13, 0, tzinfo=timezone.utc))
    assert not in_sync_window(datetime(2026, 9, 29, 11, 30, tzinfo=timezone.utc))
    fn = assess(manifest(), state(), {"ap_ada": doc()}, inside)
    assert any("sync window" in h for h in fn.holds)


def test_no_match_is_a_note_not_a_hold():
    fn = assess(manifest(), state(account_contacts=[]), {"ap_zed": doc(website="other.example")}, NOW)
    assert fn.status == STATUS_DONE
    assert fn.matched_doc_ids == []
    assert any("No CRM contact matched" in n for n in fn.notes)


def test_domain_fallback_matches_when_no_apollo_ids():
    docs = {"x1": doc(website="https://www.example.com/"), "x2": doc(website="other.example")}
    assert match_crm_contacts(state(account_contacts=[]), docs) == ["x1"]


def test_not_ready_is_a_note():
    fn = assess(manifest(), state(), {"ap_ada": doc(qualified=False)}, NOW)
    assert any("cold outreach" in n for n in fn.notes)


def test_account_not_in_ledger_is_a_note():
    fn = assess(manifest(), state(account={"name": "New Co", "domain": "new.example", "in_ledger": False},
                                  account_contacts=[], ledger_quality=None), {}, NOW)
    assert any("not in the enriched data layer" in n for n in fn.notes)


def test_quality_below_floor_and_all_stale():
    lq = {"contact_count": 2, "missing_email": ["Ada"], "stale_over_90_days": ["Ada", "Bob"]}
    assert quality_score(lq) == 0.0
    fn = assess(manifest(), state(ledger_quality=lq), {"ap_ada": doc()}, NOW)
    assert any("below the 'fair' floor" in n for n in fn.notes)
    assert any("older than 90 days" in n for n in fn.notes)
    none_floor = manifest(ledger_quality={"include": True, "quality_floor": "none"})
    assert not any("floor" in n for n in assess(none_floor, state(ledger_quality=lq), {"ap_ada": doc()}, NOW).notes)


def test_fetch_failure_sentinel_and_opt_outs_are_notes():
    m = manifest(warehouse_findings={"include": False, "opted_out": True})
    s = state(page_error="HTTP 503", warehouse_findings="not available", warehouse_sentinel=True)
    fn = assess(m, s, {"ap_ada": doc()}, NOW)
    assert any("Website fetch failed" in n for n in fn.notes)
    assert any("sentinel" in n for n in fn.notes)
    assert any("Opted out at intake: warehouse_findings" in n for n in fn.notes)


def test_text_orders_holds_before_notes():
    fn = assess(manifest(request_text="rate?"), state(), {"ap_ada": doc(qualified=False)}, NOW)
    lines = fn.text.splitlines()
    assert lines[0].startswith("HOLD — ") and lines[-1].startswith("Note — ")
    assert fn.as_dict()["status"] == STATUS_NEEDS_REVIEW


def test_no_founder_named_is_a_note():
    m = manifest()
    del m["request"]["requester"]
    review = assess(m, state(), {"ap_ada": doc()}, NOW)
    assert review.status == STATUS_DONE and review.holds == []
    assert any("No founder named" in n for n in review.notes)
    m["request"]["founder"] = {"name": "Ada Lovelace"}
    assert not any("No founder named" in n for n in assess(m, state(), {"ap_ada": doc()}, NOW).notes)

