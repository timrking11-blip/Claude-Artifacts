"""crm/note_to_founder.py: the cover note addressed to the founder (the requester)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm.note_to_founder import BRAND, draft, first_name, founder_of  # noqa: E402

def manifest(text="Need help taking Acme to market.", founder=None, requester=None):
    req = {"text": text}
    if founder is not None:
        req["founder"] = founder
    if requester is not None:
        req["requester"] = requester
    return {"request": req}


def test_founder_is_the_requester():
    m = manifest(requester={"name": "Kristin Ludwick", "linkedin_url": "https://www.linkedin.com/in/x/"})
    assert founder_of(m) == {"name": "Kristin Ludwick", "linkedin_url": "https://www.linkedin.com/in/x/"}
    both = manifest(founder={"name": "Ada Lovelace"}, requester={"name": "Someone Else"})
    assert founder_of(both)["name"] == "Ada Lovelace", "an explicit founder field wins"
    assert first_name("Kristin Ludwick") == "Kristin" and first_name(None) is None
    assert BRAND == "Strategic Market Insights"


def test_note_is_addressed_and_honest_about_gaps():
    m = manifest(requester={"name": "Kristin Ludwick"})
    text = draft(m, "Claridi.ai", True, ["On IP: we map what is protectable; the filings need patent counsel"])
    assert text.startswith("Kristin —\n")
    assert "could not find public information about Claridi.ai" in text
    assert "patent counsel." in text and text.rstrip().endswith("Tim\nStrategic Market Insights")
    for internal in ("CRM", "Apollo", "warehouse", "sync", "HOLD", "Note —"):
        assert internal not in text


def test_no_gap_line_when_something_was_found():
    text = draft(manifest(requester={"name": "Ada"}), "Acme", False, [])
    assert "could not find" not in text


def test_pricing_ask_gets_a_scoping_line_and_money_is_refused():
    text = draft(manifest("What is your hourly rate?", requester={"name": "Ada"}), "Acme", False, [])
    assert "we scope before we quote" in text
    with pytest.raises(ValueError):
        draft(manifest(requester={"name": "Ada"}), "Acme", False, ["We charge $5,000"])


def test_no_name_and_no_request():
    text = draft(manifest(text=""), "Acme", True, [])
    assert text.startswith("Hello —\n") and "Following our LinkedIn contact" in text


def test_word_cap():
    with pytest.raises(ValueError):
        draft(manifest(requester={"name": "Ada"}), "Acme", True, ["word " * 200])
