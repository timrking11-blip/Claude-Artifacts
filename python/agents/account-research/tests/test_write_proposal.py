"""The proposal writer -- pure Python, no ADK, no credentials."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from account_research.tools import write_proposal as wp  # noqa: E402


class FakeToolContext:
    def __init__(self, **state):
        self.state = dict(state)


GOOD = """
## What we understand you're asking for
You asked for help sizing the northeast market.

## What we know about you
Acme builds HVAC controls. We know Ada Lovelace, CEO.

## Where we can help
- Market sizing from the ledger and public filings.

## What we'd need to qualify this
1. Which segments matter most?

## Proposed next step
A 30-minute call with Ada.
"""


def _ctx():
    return FakeToolContext(
        account={"key": "domain:acme.example", "name": "Acme", "domain": "acme.example"},
        account_contacts=[{"contact_id": "c_ada", "apollo_contact_id": "ap_ada", "name": "Ada Lovelace"}],
        request_text="Need help sizing the northeast market.\nBudget TBD.",
    )


def test_writes_json_and_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNT_RESEARCH_PROPOSALS", str(tmp_path))
    ctx = _ctx()
    out = wp.write_proposal_tool(GOOD, ctx)
    assert out["status"] == "OK", out
    rec = json.loads(Path(out["json"]).read_text())
    assert rec["proposal_id"].startswith("prq_")
    assert rec["account"] == {"name": "Acme", "domain": "acme.example"}
    assert rec["contact_ids"] == ["c_ada"] and rec["apollo_contact_ids"] == ["ap_ada"]
    assert rec["request_text"].startswith("Need help")
    assert "## Where we can help" in rec["proposal_markdown"]
    md = Path(out["markdown"]).read_text()
    assert md.startswith("# Prequalification proposal — Acme")
    assert ctx.state["proposal_id"] == rec["proposal_id"]
    assert Path(out["json"]).name.startswith("acme-")


def test_refuses_a_missing_section(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNT_RESEARCH_PROPOSALS", str(tmp_path))
    out = wp.write_proposal_tool(GOOD.replace("## Proposed next step", "## Next"), _ctx())
    assert out["status"] == "ERROR" and "Proposed next step" in out["message"]
    assert not list(tmp_path.glob("*"))


def test_refuses_money(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNT_RESEARCH_PROPOSALS", str(tmp_path))
    out = wp.write_proposal_tool(GOOD + "\nOur rate is $4,800 per month.", _ctx())
    assert out["status"] == "ERROR" and "money" in out["message"]


def test_refuses_without_an_account(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNT_RESEARCH_PROPOSALS", str(tmp_path))
    out = wp.write_proposal_tool(GOOD, FakeToolContext())
    assert out["status"] == "ERROR" and "find_account" in out["message"]


def test_same_request_same_day_is_the_same_id(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNT_RESEARCH_PROPOSALS", str(tmp_path))
    a = wp.write_proposal_tool(GOOD, _ctx())["proposal_id"]
    b = wp.write_proposal_tool(GOOD, _ctx())["proposal_id"]
    assert a == b  # re-running the agent does not create a second proposal for the CRM
