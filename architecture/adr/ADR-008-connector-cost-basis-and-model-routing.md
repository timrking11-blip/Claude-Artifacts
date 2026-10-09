# ADR-008 — Connector cost basis and model routing

Status: Accepted
Decided: 2026-10-01
Owner: Timothy King

## Where this text comes from

The owner accepted this ADR in the 1 Oct 2026 Cowork session, alongside
ADR-007. The original file, from the unpushed commit 5613bc9, was not
available on 9 Oct 2026. The decision below is as recorded on 1 Oct in
Notion: 10 — Architecture Change Log, 00 — Architecture Hub, and the
contingency table in 13 — Cost Audit Log. The audit page is private and its
receipts stay out of this public repository.

Acceptance evidence, checked 9 Oct 2026:
- Change Log 10, 1 Oct: "ADR-008 (connector cost basis and model routing,
  Accepted)". Claude wrote this entry.
- 00 Hub: "ADR-008 Connector cost basis and model routing — Accepted
  (1 Oct 2026)".
- The routine changes it records were applied on 1 Oct and were observed on
  9 Oct. The CRM Systems Atlas refresh runs on `claude-opus-5-5`; the morning
  brief runs on `claude-sonnet-5-5` and succeeded on 9 Oct.
- Open: 14 — Governance Amendment asked the owner to confirm this status or
  downgrade it to Proposed (A5). On 9 Oct the owner directed that ADR-001 to
  ADR-008 keep their original statuses. No owner-written acceptance record
  exists beyond those, so the question is tracked in GAP-012.

## Decision

1. **Cost basis for every connector and routine.** Each connector and
   scheduled routine carries a cost basis in `architecture-manifest.yaml`:
   free, plan-included, credits, or API list rate. Each routine also carries
   its model. A new connector or routine is added with its row.
2. **Model routing.**
   - Routines that only read and summarize may run on Sonnet (the morning
     brief, applied 1 Oct).
   - The governed writers stay on Opus-class models. These are the Apollo
     sync, the Command Center refresh and the Monday Data Sync. Routing them
     to Sonnet was rejected, because an invariant breach costs more than the
     saving.
   - The CRM Systems Atlas refresh moved from Opus 5 to Opus 5.5 (applied
     1 Oct).
   - The daily site check runs a fixed script and should move to Sonnet. The
     routine is tied to the owner's computer, so the owner makes this change.
3. **Composition soft cap.** The account composition run, the one proposal
   process, has a monthly soft cap of 5 runs. The 6th run in a month holds
   until the owner confirms it.
4. **Fable on a Pro plan.** Composition on Fable, paid with usage credits, is
   rejected while the plan is Pro, where every Fable token is billed.

## Consequences

- The cap and the price table are in code: `crm/costs.py`,
  `scripts/compose_account.py prepare`, `scripts/cost_report.py`.
  `scripts/validate_architecture.py` checks that they agree with the
  manifest.
- Figures in the manifest are API list-price estimates, dated and sourced.
  Plan billing (included usage, then usage credits "at standard API rates")
  is a different basis, and the estimates are upper bounds where included
  usage covers the work. Actual spend and receipts are not kept in this
  repository.

## Annotations

- **2026-10-09.** Prices and model ids were re-read from Anthropic's official
  pages:
  - https://platform.claude.com/docs/en/about-claude/pricing
  - https://platform.claude.com/docs/en/about-claude/models/overview
  - https://claude.com/pricing

  The 1 Oct cache-read figures still hold: Opus 5 $0.50/MTok, Opus 5.5
  $0.20/MTok.
