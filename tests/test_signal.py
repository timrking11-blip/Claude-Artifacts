"""The Signal record (SPEC-002). Each test pins one rule the specification states."""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm import signal as sg  # noqa: E402

OBS = dict(kind="funding", subject_type="org", subject_id="org_8f3a", source="vibe",
           source_ref="vibe:event:12345", observed_at="2026-10-01T14:00:00Z")
INTERP = {"text": "Series A means budget for a GTM plan", "producer": "claude-opus-5-5",
          "version": "prompt:3b9c1e", "at": "2026-10-02T09:00:00Z"}


def test_a_minimal_observation_is_complete():
    s = sg.make(**OBS)
    assert sg.validate(s) == []
    assert s.interpretation is None and s.strength is None


def test_id_is_deterministic_and_names_the_observation():
    a, b = sg.make(**OBS), sg.make(**OBS, hint="Raised $4M")
    assert a.id == b.id and a.id.startswith("sig_")
    assert sg.make(**{**OBS, "source_ref": "vibe:event:99"}).id != a.id


def test_a_tampered_id_is_refused():
    s = replace(sg.make(**OBS), id="sig_0000000000000000")
    assert "id does not match the observation it names" in sg.validate(s)


@pytest.mark.parametrize("field,value,needle", [
    ("kind", "rumour", "kind"),
    ("source", "linkedin_scrape", "source"),
    ("subject_type", "email", "subject_type"),
    ("subject_id", "ceo@example.com", "stored key"),
    ("subject_id", "Example Co", "stored key"),
    ("source_ref", "", "source_ref"),
    ("observed_at", "2026-10-01T14:00:00", "time zone"),
])
def test_an_observation_outside_the_spec_is_refused(field, value, needle):
    with pytest.raises(ValueError, match=needle):
        sg.make(**{**OBS, field: value})


def test_a_hint_is_a_headline_not_a_body():
    with pytest.raises(ValueError, match="headline"):
        sg.make(**OBS, hint="x" * (sg.HINT_LIMIT + 1))


@pytest.mark.parametrize("name", ["strength", "confidence"])
def test_scores_stay_between_zero_and_one(name):
    assert sg.make(**OBS, **{name: 0.7})
    with pytest.raises(ValueError, match=name):
        sg.make(**OBS, **{name: 1.5})


def test_expiry_follows_observation():
    with pytest.raises(ValueError, match="after observed_at"):
        sg.make(**OBS, expires_at="2026-09-30T00:00:00Z")
    s = sg.make(**OBS, expires_at="2026-12-31T00:00:00Z")
    assert not s.expired("2026-12-30T23:59:59Z")
    assert s.expired("2026-12-31T00:00:00Z")
    assert not sg.make(**OBS).expired("2099-01-01T00:00:00Z")


def test_interpretation_is_kept_apart_and_names_its_producer():
    s = sg.make(**OBS, interpretation=INTERP, recommended_action="Ask about the hiring plan")
    assert s.interpretation.producer == "claude-opus-5-5"
    assert s.id == sg.make(**OBS).id  # interpreting a signal never changes what was observed
    with pytest.raises(ValueError, match="producer"):
        sg.make(**OBS, interpretation={**INTERP, "producer": ""})


def test_a_recommendation_needs_its_interpretation():
    with pytest.raises(ValueError, match="needs the interpretation"):
        sg.make(**OBS, recommended_action="Call the founder")


def test_round_trip_and_unknown_fields():
    s = sg.make(**OBS, evidence=["SRC-001"], interpretation=INTERP)
    back = sg.from_dict(s.to_dict())
    assert back == s and sg.validate(back) == []
    with pytest.raises(ValueError, match="unknown signal fields"):
        sg.from_dict({**s.to_dict(), "stage": "won"})


def test_signals_are_immutable():
    s = sg.make(**OBS)
    with pytest.raises(Exception):
        s.kind = "hiring"  # type: ignore[misc]
