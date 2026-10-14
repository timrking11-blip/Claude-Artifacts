---
name: evidence-ledger
description: Keep the source register, claim ledger and search log for any research output, and assess evidence strength. Use whenever a factual claim, market figure, statistic, price, regulation or competitor fact will appear in a deliverable, when sources disagree, or when someone asks "where does this number come from", "is this verified", "cite this", or "check these sources".
---

# Evidence ledger

A deliverable is only as good as the ledger behind it. Every material factual
statement traces to a source record or is labelled as something other than
fact. The ledger is kept separate from the narrative so it can be reviewed and
reused. The machine-readable shape is in `schemas/ledger.schema.json` at the
root of this plugin.

## Source register

One record per source used:

- `SRC-001`: title; author or issuing organization; source type
- URL or stable identifier; publication or effective date; date accessed
- Locator: page, section, table, endpoint, figure
- A short quotation or faithful description of the passage relied on
- What it supports, and what it does not establish
- Access, version, licence or coverage limits you actually verified

Source preference, judged against the question: primary materials (statutes,
regulations, agency guidance, court decisions, official datasets, original
research, official API docs, first-party company disclosures); then
peer-reviewed research and systematic reviews; then transparent institutional
and industry reports; then quality journalism (for context and leads); then
commentary, marketing and forums, labelled and never authoritative.

## Claim records

One record per important claim:

- `CLAIM-001`: the claim, stated narrowly
- Source IDs with exact locators
- Evidence type: causal, quasi-experimental, descriptive, qualitative, expert
  guidance, legal text, other
- Population, market, place and period the evidence covers
- Applies directly, or needs extrapolation (say how far)
- Conflicting or qualifying evidence
- Confidence high, medium or low, with the reason
- Status: `FACT` (sourced), `INFERENCE`, `ASSUMPTION`, or `UNVERIFIED LEAD`

## Hard rules

1. Never invent a quotation, page number, statistic, API field, licence term,
   study result or date. If a tool could not open a source, say so.
2. A search-result snippet is a lead, not a reviewed source. Open the page
   before quoting it, or label the claim `UNVERIFIED LEAD`.
3. Keep these apart, always:
   - correlation and causation;
   - a list price and a completed transaction;
   - an API's advertised capability and data the project may actually access;
   - a model's prediction and a causal explanation;
   - a standard or certification and a legal requirement;
   - no search results and proof that no evidence exists.
4. When sources disagree, show both, and give the likely reason (definition,
   period, geography, method, sponsor). Do not drop the inconvenient one.
5. Never claim an exhaustive search unless the method supports it. State the
   scope and its limits.
6. Record a checksum or archive copy only if a tool actually produced one.

## Search log

One line per search: date · tool or database · query or strategy · filters ·
what was kept and why · what was excluded and why · sources that could not be
opened. End with the material gaps that remain.

## Change control

Never overwrite a prior conclusion silently. When a conclusion changes, keep
the old record, mark it `SUPERSEDED by CLAIM-0NN`, and give the reason. Flag
claims that rest on a law, API, dataset or price that may since have changed,
with the date by which each should be rechecked.
