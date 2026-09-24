"""crm/guardrails.py: the intake-form guardrails, one rule at a time."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm.guardrails import (  # noqa: E402
    check_run,
    credit_spend_allowed,
    found_on_intake_domain,
    is_lookalike,
    is_primary_macro,
    lookalike_hosts,
    registrable_label,
)


def test_registrable_label():
    assert registrable_label("www.clarid.ai") == "clarid"
    assert registrable_label("news.example.co.uk") == "example"
    assert registrable_label("fdic.gov") == "fdic"


def test_lookalike_is_a_different_domain_with_a_near_label():
    assert is_lookalike("www.clarid.ai", "claridi.ai")          # one edit away
    assert is_lookalike("claridi.com", "claridi.ai")            # same label, other TLD
    assert is_lookalike("claridi-ai.com", "claridi.ai")         # contains
    assert not is_lookalike("claridi.ai", "claridi.ai")         # the domain itself
    assert not is_lookalike("app.claridi.ai", "claridi.ai")     # a subdomain of it
    assert not is_lookalike("fdic.gov", "claridi.ai")
    assert not is_lookalike("clarifai.com", "abc.ai")           # short labels never match
    assert lookalike_hosts(["https://www.clarid.ai/x", "https://fdic.gov"], "claridi.ai") == ["clarid.ai"]


def test_primary_macro_hosts():
    assert is_primary_macro("www.fdic.gov") and is_primary_macro("ffiec.cfpb.gov")
    assert is_primary_macro("www.kansascityfed.org") and not is_primary_macro("mercercapital.com")


def test_found_on_intake_domain():
    assert found_on_intake_domain({"apollo": "ok: found"}, [], "x.example")
    assert found_on_intake_domain({}, ["https://www.x.example/about"], "x.example")
    assert not found_on_intake_domain({"apollo": "none: no"}, ["https://other.example"], "x.example")


def test_check_run_rules():
    m = {"state": {"account": {"domain": "claridi.ai"}}, "data_sources": {"allow_credit_spend": False}}
    # lookalike in research
    p = check_run(m, {}, "([site](https://www.clarid.ai/)) [supported]", "", "x not found", [])
    assert any("domain lock" in x for x in p)
    # nothing found: non-primary citations refused, primary allowed, must say not found
    p = check_run(m, {"apollo": "none"}, "", "", "## What we know\nnot found", ["https://www.fdic.gov/a"])
    assert p == []
    p = check_run(m, {"apollo": "none"}, "", "", "## What we know\nGreat company", ["https://kadince.com/a"])
    assert any("empty means empty" in x and "kadince.com" in x for x in p)
    assert any("must say so" in x for x in p)
    # found on the domain: other citations are fine
    p = check_run(m, {}, "", "", "x", ["https://claridi.ai/about", "https://kadince.com/a"])
    assert p == []
    # credit spend without the tick
    p = check_run(m, {"apollo": "ok: enriched"}, "", "", "x", ["https://claridi.ai/"])
    assert any("credit spend" in x for x in p)
    assert credit_spend_allowed({"data_sources": {"allow_credit_spend": True}})
    assert not credit_spend_allowed({})
