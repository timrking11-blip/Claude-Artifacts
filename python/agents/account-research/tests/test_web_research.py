"""The web research tool against a fake Anthropic client -- no network, no key."""

import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from account_research.tools import ledger  # noqa: E402
from account_research.tools import web_research as wr  # noqa: E402


class FakeMessages:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.beta = NS(messages=FakeMessages(responses))


class Ctx:
    def __init__(self, **state):
        self.state = dict(state)


SEARCH = NS(type="web_search_tool_result", content=[NS(url="https://news.example/a"), NS(url="https://acme.example/")])
FETCH = NS(type="web_fetch_tool_result", content=NS(url="https://acme.example/about"))
MEMO = NS(type="text", text="## Company\nAcme sells HVAC controls ([site](https://acme.example/)) [supported]",
          citations=[NS(url="https://acme.example/about")])


def test_resumes_a_paused_turn_and_collects_sources():
    paused = NS(stop_reason="pause_turn", content=[SEARCH])
    done = NS(stop_reason="end_turn", content=[FETCH, MEMO])
    client = FakeClient([paused, done])
    out = wr.research_account("Acme", "acme.example", "pricing", client=client)
    assert out["status"] == "OK"
    assert out["memo"].startswith("## Company")
    assert out["sources"] == ["https://news.example/a", "https://acme.example/", "https://acme.example/about"]
    calls = client.beta.messages.calls
    assert len(calls) == 2
    # the resume re-sends the paused assistant turn and adds no user message
    assert [m["role"] for m in calls[1]["messages"]] == ["user", "assistant"]
    assert {t["type"] for t in calls[0]["tools"]} == {"web_search_20260209", "web_fetch_20260209"}
    assert "Website: https://acme.example" in calls[0]["messages"][0]["content"].splitlines()
    assert calls[0]["fallbacks"] == "default"


def test_an_error_search_result_is_not_a_source():
    err = NS(type="web_search_tool_result", content=NS(error_code="max_uses_exceeded"))
    client = FakeClient([NS(stop_reason="end_turn", content=[err, MEMO])])
    out = wr.research_account("Acme", "acme.example", client=client)
    assert out["sources"] == ["https://acme.example/about"]


def test_refusal_is_an_error_not_a_memo():
    client = FakeClient([NS(stop_reason="refusal", content=[], stop_details=NS(category="cyber"))])
    out = wr.research_account("Acme", "acme.example", client=client)
    assert out["status"] == "ERROR" and "declined" in out["message"]


def test_needs_a_name_or_domain():
    assert wr.research_account(None, None, client=FakeClient([]))["status"] == "ERROR"


def test_tool_writes_state(monkeypatch):
    monkeypatch.setattr(wr, "research_account",
                        lambda n, d, f: {"status": "OK", "memo": "memo", "sources": ["https://a.example"]})
    ctx = Ctx(account={"name": "Acme", "domain": "acme.example"})
    assert wr.web_research_tool("pricing", ctx) == {"status": "OK", "sources": 1}
    assert ctx.state["web_research"] == "memo" and ctx.state["web_sources"] == ["https://a.example"]


def test_register_prospect_stores_an_account_with_no_contacts():
    ctx = Ctx()
    out = ledger.register_prospect_tool("Claridi.ai", "https://www.claridi.ai/", ctx)
    assert out["status"] == "OK"
    acct = ctx.state["account"]
    assert acct["key"] == "domain:claridi.ai" and acct["domain"] == "claridi.ai"
    assert acct["contact_count"] == 0 and acct["prospect"] is True
    assert ledger.register_prospect_tool("", "", Ctx())["status"] == "ERROR"
