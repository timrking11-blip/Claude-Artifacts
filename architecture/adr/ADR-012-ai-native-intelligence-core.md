# ADR-012 — AI-Native Intelligence Core (target)

Status: Proposed
Owner: Timothy King
Origin: 14 — Governance Amendment (PROPOSED), section 8,
https://app.notion.com/p/3ec7ecee36a9814aa01ffdf64313dfc6. Carried here 9 Oct 2026.
Executable rules: `architecture/invariants.yaml` (INV-01 to INV-05,
INV-11, INV-12, INV-15).

No acceptance evidence exists, so this ADR stays Proposed. It is not
production authority, and nothing in it authorizes a store, a tool, outreach,
enrichment spend or an autonomous write.

## Proposed decision

**Target object model.** It extends existing records and adds no parallel
store unless an audit proves one is needed.

| Object | Extends today |
|---|---|
| Entity | Custom CRM accounts and contacts; `org_id`, `master_id` |
| Signal | new, as SPEC-002 specifies |
| Observation | composition run sources and coverage; captured activity rows |
| Evidence | field `provenance`; proposal citations |
| Claim | proposal statements with citations |
| Hypothesis | new: the qualification reasoning, kept apart from evidence |
| Contradiction | held merge conflicts (`data/master/review.json`, `held`); HOLD lines |
| IntelligenceObject | new: a typed envelope over Signal … Evaluation |
| StateSnapshot | the scorecard computed from activity |
| Recommendation | the proposal's next step |
| Decision | "Review before sending"; HOLD clearance; runlog confirmations |
| ActionAuthorization | `crm.broker.approve`; runlog exact-count confirm |
| Action | `jobs/` rows; pinned CRM batch writes; sends |
| Outcome | captured replies and meetings (`channel_ref`) |
| Evaluation | new |
| ProvenanceEdge | `provenance`, stored keys, run `manifest.json` |

**First work package.** WP-IC-1, one narrow evidence loop, is defined in
`architecture/target-state.md`. It needs a go or no-go from the owner, and
this ADR's acceptance does not start it.

**No new tool** is adopted without a demonstrated gap, an owner, a boundary,
a cost and an acceptance test. This covers Clay, n8n, Dagster, LangGraph,
Langfuse, Replit, a new CRM, a warehouse and paid enrichment.
