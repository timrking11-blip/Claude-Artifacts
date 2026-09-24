"""'web_research' tool: outward-facing research on an account, from the open web.

The ledger only knows the people we already have. A prequalification
proposal has to argue from the prospect's own world -- what they sell, who
buys it, what is changing around them -- so this tool sends one Claude
request with the server-side web search and web fetch tools and returns a
sourced research memo. Claude runs both tools on Anthropic's servers, so the
account's site is read from there even where this process has no outbound
network of its own.

Only the standard library is imported at module load; the Anthropic SDK is
imported when the tool runs, so the ledger and proposal tests stay SDK-free.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # annotation only; keeps ADK out of the import path
    from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

#: Server tool versions with dynamic filtering (Opus 5 / 4.6+, Sonnet 5 / 4.6).
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}
WEB_FETCH = {
    "type": "web_fetch_20260209",
    "name": "web_fetch",
    "max_uses": 10,
    "citations": {"enabled": True},
}
#: A server-tool turn pauses after its own iteration limit; resume at most this often.
MAX_CONTINUATIONS = 5

SYSTEM = """You are the research desk for Strategic Marketing Insights (SMI), an
independent strategy advisor. You gather the outside-in evidence a short,
persuasive prequalification proposal is argued from. You never write the
proposal itself.

Work outward from the company's own site, then the wider web:
1. Fetch the company's site first: the home page, then any about, product,
   solutions, pricing, customers, team, careers, blog or news pages it links to.
2. Search for the company by name and domain: news, funding, launches,
   partnerships, hiring, leadership, regulatory or registry listings, reviews,
   and the LinkedIn company page.
3. Search the market it sells into: the buyer, the forces moving that buyer's
   budget this year, named competitors, and any rule or standard that constrains
   how the product is bought.
4. Search the adjacent ground: parent company, subsidiaries, partners and
   integrations, named customers and case studies, investors, board and
   leadership backgrounds, job postings (what they are hiring for says what
   they are building), reviews, and conference or press appearances.
5. Build the macroeconomic picture of the business, ValueFirst-grade: what
   drives demand in its sector (end-market growth, capital spending, budgets),
   what drives its costs (labor, inputs, compute, rates and credit), the
   policy and regulatory calendar, and where the sector sits in the cycle.
   Prefer dated primary sources -- BLS, BEA, Census, FRED / Federal Reserve,
   SEC filings, industry associations, reputable analysts -- and state the
   date of every figure.

Report in Markdown under exactly these headings:
## Company -- what it does, in its own words, and who it sells to
## Evidence of stage -- founding date, size, funding, leadership, hiring
## Market and buyer -- the forces on the buyer that make this a live problem now
## Competitors -- named, with one line each on how they position
## Adjacent -- parent, partners, customers, investors, hiring, leadership backgrounds
## Macroeconomic context -- demand drivers, cost drivers, rates and credit, policy calendar, cycle position; every figure dated
## Signals worth a conversation -- three to five specific facts a proposal can lead with
## Gaps -- what you looked for and could not find

Rules:
- Research only the company at the given domain. A company with a similar
  name at a different domain is NOT a match, even if a search result says it
  is: list it under Gaps as "similarly named, not this company" and use
  nothing from it. When the domain itself yields nothing, the memo says so;
  it never substitutes a lookalike.
- Every factual sentence ends with its source as a Markdown link to a page you
  actually fetched or a search result you read, followed by one evidence tag:
  [supported] when a named source states it, [needs stipulation] when it is
  inferred or dated and the client must confirm it, [unsupported] when it is a
  hypothesis with no source.
- If a page cannot be fetched or a fact cannot be found, say "not found" under
  Gaps. Never guess a number, a name or a date.
- Be terse: short sentences, no marketing language, under 1,000 words.
"""


def _model() -> str:
    return os.getenv("ACCOUNT_RESEARCH_RESEARCH_MODEL") or os.getenv(
        "ACCOUNT_RESEARCH_CLAUDE_MODEL", "claude-opus-5"
    )


def _prompt(name: str | None, domain: str | None, focus: str) -> str:
    who = name or domain or "the account"
    site = f"https://{domain}" if domain else "(no domain on file -- find the official site first)"
    lines = [f"Company: {who}", f"Website: {site}"]
    if focus.strip():
        lines.append(f"Focus for this proposal: {focus.strip()}")
    lines.append("Research this company and its market now, then write the memo.")
    return "\n".join(lines)


def _sources(content: list[Any]) -> list[str]:
    """Every URL the server tools returned or the answer cited, in first-seen order."""
    seen: list[str] = []

    def add(url: Any) -> None:
        if isinstance(url, str) and url.startswith("http") and url not in seen:
            seen.append(url)

    for block in content:
        btype = getattr(block, "type", None)
        if btype == "web_search_tool_result":
            results = getattr(block, "content", None)
            if isinstance(results, list):  # an error result is a single object, not a list
                for r in results:
                    add(getattr(r, "url", None))
        elif btype == "web_fetch_tool_result":
            add(getattr(getattr(block, "content", None), "url", None))
        elif btype == "text":
            for cite in getattr(block, "citations", None) or []:
                add(getattr(cite, "url", None))
    return seen


def research_account(name: str | None, domain: str | None, focus: str = "",
                     client: Any = None) -> dict[str, Any]:
    """Runs one web-researched memo on the account.

    Returns status "OK" with "memo" (Markdown) and "sources" (URLs), or
    status "ERROR" with a message. `client` is injectable for tests.
    """
    if not (name or domain):
        return {"status": "ERROR", "message": "No account name or domain to research."}
    if client is None:
        import anthropic  # deferred: see the module docstring

        client = anthropic.Anthropic()

    messages: list[dict[str, Any]] = [{"role": "user", "content": _prompt(name, domain, focus)}]
    content: list[Any] = []
    response = None
    for _ in range(MAX_CONTINUATIONS + 1):
        # Server-side fallbacks: a policy decline is re-run on a fallback model
        # inside the same call instead of ending the research.
        response = client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            model=_model(),
            max_tokens=16000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"effort": os.getenv("ACCOUNT_RESEARCH_RESEARCH_EFFORT", "high")},
            tools=[WEB_SEARCH, WEB_FETCH],
            messages=messages,
        )
        content.extend(response.content)
        if response.stop_reason != "pause_turn":
            break
        # Resume the paused server-tool turn: resend it as-is, no extra user message.
        messages = messages + [{"role": "assistant", "content": response.content}]

    if response is None:
        return {"status": "ERROR", "message": "No response from the model."}
    if response.stop_reason == "refusal":
        category = getattr(getattr(response, "stop_details", None), "category", None)
        return {"status": "ERROR", "message": f"The model declined the research request ({category})."}
    if response.stop_reason == "pause_turn":
        return {"status": "ERROR", "message": "Research still paused after the continuation limit."}

    memo = "\n".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text").strip()
    if not memo:
        return {"status": "ERROR", "message": f"Empty research memo (stop_reason={response.stop_reason})."}
    return {"status": "OK", "memo": memo, "sources": _sources(content)}


def web_research_tool(focus: str, tool_context: "ToolContext") -> dict[str, Any]:
    """Researches the stored account on the open web, starting from its own site.

    Args:
      focus: What the proposal needs to argue, in a sentence -- usually the
        request text. May be empty.
      tool_context: ToolContext object; reads "account", writes "web_research"
        and "web_sources".

    Returns:
      status "OK" with the number of sources read, or status "ERROR".
    """
    account = tool_context.state.get("account") or {}
    out = research_account(account.get("name"), account.get("domain"), focus or "")
    if out["status"] != "OK":
        tool_context.state.update({"web_research": f"Web research failed: {out['message']}", "web_sources": []})
        logger.error("web_research_tool(): %s", out["message"])
        return out
    tool_context.state.update({"web_research": out["memo"], "web_sources": out["sources"]})
    logger.info("web_research_tool(): %d sources", len(out["sources"]))
    return {"status": "OK", "sources": len(out["sources"])}
