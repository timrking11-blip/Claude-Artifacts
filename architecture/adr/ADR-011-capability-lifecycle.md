# ADR-011 — Capability lifecycle and reconciliation

Status: Proposed
Owner: Timothy King
Origin: 14 — Governance Amendment (PROPOSED), sections 6 and 8. Revised 9 Oct 2026.

## Revision note

Page 14 had a single capability-status ladder, PROPOSED → ACCEPTED →
IMPLEMENTED → CONFIGURED → EXECUTED → PRODUCTION_VERIFIED → RETIRED. That
ladder mixes four separate questions: what was decided, what was built,
where it runs, and what proves it. For example, branch code can exist
without being deployed. A decision can be accepted before any merge. A run
can execute without being verified for production. This revision keeps the
questions apart.

`architecture-manifest.yaml` already records them as four separate fields.
They are used descriptively, without accepting this ADR.

## Proposed decision

Each capability records four separate facts:

1. **`decision_status`**: Proposed, Accepted, Superseded, Deferred or Not
   written. Acceptance is the owner's and does not depend on a merge.
2. **`implementation_state`**: none, DESIGNED, CODE_EXISTS, CONFIGURED,
   EXECUTED, PRODUCTION_VERIFIED or RETIRED. This is what an audit observed.
   - CODE_EXISTS says nothing about deployment.
   - EXECUTED means at least one dated run and says nothing about
     verification.
   - PRODUCTION_VERIFIED needs written acceptance criteria met in the
     operating environment over a stated window, plus a reviewer. No script
     here can claim it.
3. **`deployment`**: where it lives:
   - a branch;
   - the default branch;
   - a routine;
   - an artifact;
   - an external system;
   - nowhere.
4. **`evidence`**: commit-pinned code, tests, runlog ids, trigger ids, dates.

Documentation currency (when a page was last reviewed) is a fifth, separate
fact. It never stands in for capability verification.

**Registry mapping (Notion Architecture Registry).**
- "Current" requires PRODUCTION_VERIFIED.
- "Implemented" requires CODE_EXISTS on the default branch.
- "Verified" requires PRODUCTION_VERIFIED.
- A correction applies only on current evidence and keeps the prior value
  in the row's history.

**Reconciliation loop.** Accepted decision, then executable contract, then
implementation and runtime, then the CRM Systems Atlas observed status, then
a reconciliation audit, then a gap and its remediation, then owner approval,
then an updated decision when the architecture changes.
