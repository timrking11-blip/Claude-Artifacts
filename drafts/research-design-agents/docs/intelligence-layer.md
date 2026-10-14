# How this plugin relates to the AI-native intelligence layer

Status: reference only · checked 14 Oct 2026

## Where the layer is defined

| What | Where | Standing on 14 Oct 2026 |
|---|---|---|
| Architecture | Notion, INTEGRATED GTM ARCHITECTURE, page 09 "Architecture Roadmap" (AI-native intelligence layer, proposed scope) | Planning input. The page says it is "not an approved or implemented specification" |
| Target object model | `timrking11-blip/Claude-Artifacts`, `architecture/adr/ADR-012-ai-native-intelligence-core.md` | Proposed, not accepted. "Nothing in it authorizes a store, a tool, outreach, enrichment spend or an autonomous write." |
| System of record | The CRM System artifact on claude.ai, whose database is written from Claude sessions; code in `Claude-Artifacts` | Live |
| Code repository | `timrking11-blip/Claude-Artifacts` | Live |

This plugin is general-purpose and does not depend on any of the above. It
also does not write to any of them.

## Mapping

The ledger these agents produce (`schemas/ledger.schema.json`) lines up with
objects named in ADR-012's proposed model. If ADR-012 is accepted, a ledger
could become input to the layer without reshaping:

| Ledger field | ADR-012 object |
|---|---|
| `sources[]` (with `excerpt`, `locator`, `accessed`) | Evidence, Observation |
| `claims[]` with status `FACT` | Claim |
| `claims[]` with status `INFERENCE` or `ASSUMPTION` | Hypothesis (kept apart from evidence) |
| `claims[].conflicts`, disagreeing sources | Contradiction |
| `claims[].source_ids`, `superseded_by` | ProvenanceEdge |
| The study's recommendations | Recommendation |
| "Decisions that need a human owner" | Decision (made by a person, not the agent) |

## Boundary

- The agents never write to the CRM, Apollo, or any system of record.
- Moving a ledger into the CRM is the owner's decision, made in
  `Claude-Artifacts` under that repo's rules: a runlog line for every run
  that creates records, and a hold when a run would create more than five.
- Nothing here accepts ADR-012 or starts its first work package (WP-IC-1).
  That decision is the owner's.
