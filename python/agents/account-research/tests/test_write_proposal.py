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
# Acme -- Prequalification Proposal
Prepared by Strategic Market Insights

## Engagement summary
By a date we set together, Acme decides whether to enter the northeast market.

## What we heard
You asked for help sizing the northeast market.

| Signal | Source | What SMI reads into it |
| --- | --- | --- |
| New Boston office | [press](https://acme.example/news) | Expansion is funded. |

## Why now: the market and the economy
Northeast construction spending rose in 2026 ([census](https://census.example/c30)) [supported].

## The problem in front of Acme
1. Two incumbents hold the channel ([report](https://example.org/r)) [supported]

## Approach
**Market scan** (3 weeks). Gate: Acme approves the segment.

## What we'd need to qualify this
1. What decision closes this, and by when?

## Next step
A 30-minute call with Ada Lovelace, CEO.

## Sources
- https://acme.example/news
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
    assert rec["account"] == {"name": "Acme", "domain": "acme.example", "prospect": False}
    assert rec["contact_ids"] == ["c_ada"] and rec["apollo_contact_ids"] == ["ap_ada"]
    assert rec["request_text"].startswith("Need help")
    assert "## The problem in front of Acme" in rec["proposal_markdown"]
    assert rec["sources"] == ["https://acme.example/news", "https://census.example/c30", "https://example.org/r"]
    md = Path(out["markdown"]).read_text()
    assert md.startswith("# Prequalification proposal — Acme")
    assert ctx.state["proposal_id"] == rec["proposal_id"]
    assert Path(out["json"]).name.startswith("acme-")


def test_refuses_a_missing_section(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNT_RESEARCH_PROPOSALS", str(tmp_path))
    out = wp.write_proposal_tool(GOOD.replace("## Next step", "## Then"), _ctx())
    assert out["status"] == "ERROR" and "Next step" in out["message"]
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


def test_refuses_an_overlong_proposal(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNT_RESEARCH_PROPOSALS", str(tmp_path))
    out = wp.write_proposal_tool(GOOD + ("word " * wp.MAX_WORDS), _ctx())
    assert out["status"] == "ERROR" and "words" in out["message"]


def test_refuses_uncited_when_research_found_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNT_RESEARCH_PROPOSALS", str(tmp_path))
    ctx = _ctx()
    ctx.state["web_sources"] = ["https://acme.example/news"]
    bare = "\n".join(l for l in GOOD.splitlines() if "http" not in l)
    out = wp.write_proposal_tool(bare, ctx)
    assert out["status"] == "ERROR" and "cites none" in out["message"]


def test_records_lead_source_and_request(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNT_RESEARCH_PROPOSALS", str(tmp_path))
    ctx = _ctx()
    ctx.state.update(lead_source="linkedin", request_id="acme-2026-09-24")
    rec = json.loads(Path(wp.write_proposal_tool(GOOD, ctx)["json"]).read_text())
    assert rec["lead_source"] == "linkedin" and rec["request_id"] == "acme-2026-09-24"
