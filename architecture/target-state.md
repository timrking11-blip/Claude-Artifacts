# Target state

As of 14 Oct 2026. Ownership targets are in `system-of-record.yaml`
(`accepted_target` and `proposed`). This page gives the accepted target, the
proposals kept apart from it, and the work packages that replace phase
numbers.

## Accepted target

Each of these is accepted. None is a claim that it is built.

- **Architecture authority** is this folder (ADR-007, effective 9 Oct 2026).
  ADR texts live on their Notion 02 pages and are indexed here (ADR-014).
- **AI Action Contract** (ADR-006, accepted 14 Oct 2026): every agent action
  uses the versioned contract, and every decision on one leaves a decision
  record (SPEC-003, `crm/decision.py`). There is no store or executor yet.
- **Commercial records** live in one Custom CRM, with field-level ownership,
  stored keys, reviewed merges and no silent overwrite. Source tools enrich,
  activate, measure or execute; they are never competing authorities
  (ADR-001).
- **Cost basis and routing** (ADR-008):
  - every connector and routine has a cost basis;
  - governed writers run on Opus-class models, and read-and-summarize
    routines may run on Sonnet;
  - a composition soft cap of 5 a month.
- **01 — Living Reference Model**, system-of-record policy:
  - PandaDoc for signed proposals;
  - Operations Workbench for delivery records, after the first signed client;
  - BigQuery parked behind the analytics gate.

  Whether ARC-001 is "Current" is disputed (GAP-003); the targets stand.
- **Blueprint route** (`docs/unified-architecture-blueprint.md`):
  - gate-based expansion;
  - no credit spend without a `jobs/` row, a free estimate and the owner's
    go;
  - the 15 Nov kill check decides whether later work starts.

## Proposed target (not in force)

- **ADR-002 to ADR-005**: journey graph, measurement plane, scoring,
  attribution.
- **ADR-009**: authority roles under ADR-007.
- **ADR-010**: naming.
- **ADR-011**: capability lifecycle, with four separate status facts.
- **ADR-012**: AI-Native Intelligence Core, and WP-IC-1 below.
- **ADR-013**: learning and research optimisation (not written).
- **SPEC-002 Signal Model** (under ADR-012): the record type exists
  (`crm/signal.py`), with no store and no producer (GAP-021).
- **Candidate invariants** for ADR-012 and ADR-013 in `invariants.yaml`.

## Evidence graph: references for the evidence half

ADR-002's journey graph links accounts, contacts, signals and outcomes. Its
evidence half now has an executable shape that needs no store: the evidence
ledger (`schemas/evidence-ledger.schema.json`, `crm/ledger.py`,
`docs/research-profiles.md`). Each research run writes one ledger file:
- Observations: the source register;
- Evidence, with a stance: a claim citing a source;
- Claims and Hypotheses: FACT versus INFERENCE or ASSUMPTION;
- Contradictions;
- ProvenanceEdges: citations and supersessions.

The design draws on the research-design work staged in
`drafts/research-design-agents/`:
- `docs/intelligence-layer.md` maps the ledger onto ADR-012's objects.
- `docs/hermes-runtime.md` records Hermes Agent as a candidate runtime, not
  adopted. Its adoption check needs a demonstrated gap, an owner, a boundary,
  a cost and an acceptance test.
- `schemas/ledger.schema.json` is identical to the schema here.

The agents are given one role. They are research assistants that produce
traceable, reviewable records, and they do not replace subject-matter
experts, counsel, privacy or security reviewers, clinicians or regulators.
They write ledger files and never a system of record. Linking ledgers to the
journey (account to signal to outcome) waits for ADR-002 and ADR-012.

## Work packages (historical phase numbers mapped)

The repository blueprint and Notion 01 number their phases differently
(GAP-010). The numbers stay as history, and new text names the work
package. This mapping is proposed until the owner accepts it.

| Work package | Repository blueprint | Notion 01 | State, 9 Oct 2026 |
|---|---|---|---|
| WP-DRIFT: stop the drift | P0 | Phase 0, Inventory and decisions (part) | Gate passed 28 Sep |
| WP-SURFACE: one surface, one vocabulary | P1 | Phase 1, Stabilize the shipped products (part) | Close and gate check Mon 12 Oct (scheduled routine) |
| WP-KEYS-ACTIVITY: keys, broker, activity | P2 | Phase 2, Instrument demand and lifecycle (part) | Shadow 5 and 12 Oct; cutover 19 Oct; gate by 15 Nov |
| WP-PROPOSAL-RECORDS: proposals and intake as records | P3 | — | Starts only if the 15 Nov kill thresholds did not fire |
| WP-ENGAGEMENTS: won to engagement handoff | P4 | Phase 3, Connect commercial to delivery | Needs a signed or live engagement |
| WP-CANONICAL-STORE: one canonical store | P5 | — | Trigger-gated |
| WP-ANALYTICS: analytical spine | — | Phase 4 | Parked (BigQuery, Vertex) |
| WP-BILLING: billing readiness | — | Phase 5 | Deferred until approvals and reconciliation pass |
| WP-IC-1: one narrow evidence loop | — | — | Proposed (ADR-012); needs the owner's go |

## WP-IC-1: one narrow evidence loop

**Scope.** One Custom CRM account that an intake form names, run once. It
uses only existing components:

1. **Identity.** The stored `org_id` and `master_id`, under the domain lock.
2. **Observation and evidence.** The composition run's sources and coverage,
   recorded with provenance.
3. **Hypothesis.** The qualification hypothesis, recorded separately from
   the evidence.
4. **Proposed action.** The proposal's next step, or the note to the founder.
5. **Decision.** "Review before sending" and HOLD clearance, with the
   independent check that cleared each HOLD.
6. **Action.** A send, made by the owner and recorded with its `channel_ref`.
7. **Outcome.** A captured reply or meeting matched by `channel_ref`, or an
   explicit "no outcome by <date>".
8. **Evaluation.** The outcome against the hypothesis, with the model and
   prompt versions.

**Not in scope.** No new store and no ontology change; records extend the
CRM documents and run files that exist. No outreach is sent by an agent. No
enrichment is bought. No autonomous write: every CRM write is a pinned batch
applied in a session, with a runlog line.

**Acceptance criteria.** All of these must hold:

- Each of steps 1–8 is present for the one account, as a record or a field,
  with a reference to the step before it (INV-11's action reference, INV-02's
  observation and interpretation split).
- The hypothesis is in its own field or record. Rerunning the loop creates a
  new version and never overwrites the first (INV-03).
- Every HOLD shows the check that cleared it, and the reviewer.
- The evaluation is computed from the captured outcome, not typed in
  (INV-12).
- `scripts/check_architecture.py` shows no regression. INV-02, INV-03 and
  INV-11 rise from their current level, or the run explains why not.
- Zero credits spent, zero sends made by an agent, one runlog line per write.

**Approval.** The owner's go or no-go (GAP-004). Starting WP-IC-1 does not
accept ADR-012.
