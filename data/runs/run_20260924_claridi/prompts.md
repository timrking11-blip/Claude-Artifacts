# Prompts for run run_20260924_claridi

## 0 · Data sources → data_sources.md + coverage.json

Account: Claridi.ai (claridi.ai).
Pull every source that can speak to this account, cheapest first, and surface any credit cost before spending it:
- **Apollo**: apollo_organizations_enrich on the domain (firmographics, funding, headcount, technologies, keywords); apollo_mixed_people_api_search on the domain for leadership and decision-makers (the plan may refuse people search; record that).
- **Vibe Prospecting**: match-business on name + domain, then enrich-business for firmographics, technographics, funding and recent business events; fetch-prospects for decision-makers if the match holds. Use estimate-cost first; stop and record 'no credits' rather than spend blind.
Write what you found to data_sources.md under '## Apollo' and '## Vibe Prospecting', each fact with its source, and never mix up a similarly named company (a name match with the wrong domain is not a match).
Write coverage.json as {"ledger": ..., "apollo": ..., "prospecting": ..., "site": ..., "web": ...}, each value "ok: <what>" or "none: <why>" or "error: <why>" — for example "none: host blocked by the environment's network policy".

## 1 · Web research → web_research.md + web_sources.txt

Answer with your own web search and web fetch tools. Save the memo to web_research.md and every URL you fetched or cited, one per line, to web_sources.txt.

You are the research desk for Strategic Marketing Insights (SMI), an
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
- Every factual sentence ends with its source as a Markdown link to a page you
  actually fetched or a search result you read, followed by one evidence tag:
  [supported] when a named source states it, [needs stipulation] when it is
  inferred or dated and the client must confirm it, [unsupported] when it is a
  hypothesis with no source.
- If a page cannot be fetched or a fact cannot be found, say "not found" under
  Gaps. Never guess a number, a name or a date.
- Be terse: short sentences, no marketing language, under 1,000 words.

---

Company: Claridi.ai
Website: https://claridi.ai
Research this company and its market now, then write the memo.

## 2 · Summarise the page → website_summary.txt

(fetch_page did not run; skip this leg — the research memo covers the site)

## 3 · Draft the proposal

Run `scripts/compose_account.py brief run_20260924_claridi --web-research ... --web-sources ... --data-sources ... --coverage ... [--website-summary ...]`; it writes proposal_prompt.md with the research filled in. Answer that prompt and save the Markdown to proposal.md.
