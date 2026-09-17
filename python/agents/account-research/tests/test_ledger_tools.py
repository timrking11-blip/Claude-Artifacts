"""Tests for the ledger tools -- pure Python, no ADK or Google credentials."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from account_research.tools import ledger  # noqa: E402


class FakeToolContext:
    """The only part of ADK's ToolContext the ledger tools touch."""

    def __init__(self):
        self.state = {}


def contact(**kw):
    base = {
        "contact_id": kw.get("contact_id", "c_" + kw.get("last_name", "x").lower()),
        "first_name": None, "last_name": None, "email": None, "phone": None,
        "title": None, "seniority": None, "linkedin_url": None, "location": None,
        "company_name": None, "company_domain": None, "industry": None,
        "employee_count": None, "technologies": [], "sources": ["apollo"],
        "provenance": {}, "first_seen": "2026-09-01T00:00:00+00:00",
        "last_updated": "2026-09-14T06:00:00+00:00",
    }
    base.update(kw)
    return base


@pytest.fixture
def ledger_file(tmp_path, monkeypatch):
    contacts = [
        contact(first_name="Ada", last_name="Lovelace", title="CTO", seniority="c_suite",
                email="ada@example.com", phone="+1", company_name="Example Co",
                company_domain="https://www.example.com", sources=["apollo", "explorium"]),
        contact(first_name="Grace", last_name="Hopper", title="Engineer", seniority="senior",
                company_name="Example Co", company_domain="example.com",
                last_updated="2026-01-01T00:00:00+00:00",
                provenance={"title": {"source": "manual", "observed_at": "2026-09-15T00:00:00+00:00"}}),
        contact(first_name="Linus", last_name="Torvalds", title="Fellow", seniority="vp",
                email="l@kernel.example", company_name="Kernel Org", company_domain="kernel.example"),
        contact(first_name="Ken", last_name="Thompson", company_name="Example Labs"),
    ]
    path = tmp_path / "contacts.json"
    path.write_text(json.dumps({"contacts": contacts}))
    monkeypatch.setenv("ACCOUNT_RESEARCH_LEDGER", str(path))
    return path


def test_find_by_domain_variants(ledger_file):
    for q in ("example.com", "https://www.example.com/about", "EXAMPLE.COM"):
        ctx = FakeToolContext()
        out = ledger.find_account_tool(q, ctx)
        assert out["status"] == "OK", q
        assert ctx.state["account"]["domain"] == "example.com"
        assert ctx.state["account"]["contact_count"] == 2


def test_find_by_exact_name(ledger_file):
    ctx = FakeToolContext()
    out = ledger.find_account_tool("example co", ctx)
    assert out["status"] == "OK"
    assert ctx.state["account"]["name"] == "Example Co"


def test_substring_match_is_ambiguous_when_several(ledger_file):
    ctx = FakeToolContext()
    out = ledger.find_account_tool("example", ctx)
    assert out["status"] == "AMBIGUOUS"
    names = {c["name"] for c in out["candidates"]}
    assert names == {"Example Co", "Example Labs"}
    assert "account" not in ctx.state, "ambiguity must not store an account"


def test_not_found(ledger_file):
    out = ledger.find_account_tool("Nonexistent Inc", FakeToolContext())
    assert out["status"] == "NOT_FOUND"


def test_contacts_ordered_by_seniority(ledger_file):
    ctx = FakeToolContext()
    ledger.find_account_tool("example.com", ctx)
    out = ledger.list_account_contacts_tool(ctx)
    assert out == {"status": "OK", "count": 2}
    rows = ctx.state["account_contacts"]
    assert [r["name"] for r in rows] == ["Ada Lovelace", "Grace Hopper"]
    assert rows[0]["has_email"] and rows[0]["has_phone"]
    assert not rows[1]["has_email"]


def test_quality_flags(ledger_file):
    ctx = FakeToolContext()
    ledger.find_account_tool("example.com", ctx)
    out = ledger.assess_ledger_quality_tool(ctx)
    assert out["status"] == "OK"
    q = ctx.state["ledger_quality"]
    assert q["missing_email"] == ["Grace Hopper"]
    assert q["stale_over_90_days"] == ["Grace Hopper"]
    assert q["manually_edited"] == ["Grace Hopper"]
    assert q["not_yet_enriched"] == ["Grace Hopper"]
    assert q["single_source_only"] == ["Grace Hopper"]


def test_tools_require_find_account_first(ledger_file):
    ctx = FakeToolContext()
    assert ledger.list_account_contacts_tool(ctx)["status"] == "ERROR"
    assert ledger.assess_ledger_quality_tool(ctx)["status"] == "ERROR"


def test_missing_ledger_is_empty_not_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNT_RESEARCH_LEDGER", str(tmp_path / "nope.json"))
    assert ledger.find_account_tool("anything", FakeToolContext())["status"] == "NOT_FOUND"


def test_default_ledger_path_points_at_repo_master(monkeypatch):
    monkeypatch.delenv("ACCOUNT_RESEARCH_LEDGER", raising=False)
    p = ledger.default_ledger_path()
    assert p.parts[-3:] == ("data", "master", "contacts.json")
    assert p.exists(), "should resolve to this repo's committed master"
