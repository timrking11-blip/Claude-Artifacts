# ADR-006 — AI Action Contract

Status: Proposed
Owner: Timothy King
Notion: https://app.notion.com/p/a749895b8af44375a86cba7edd7c298f

Imported 9 Oct 2026 from Notion 02 (page last edited 29 Sep 2026), verbatim.
Proposed: editable, not in force. `architecture/invariants.yaml` holds its
executable rules (INV-06 to INV-10, INV-16).

## Decision

Every agent action must use a versioned contract containing inputs, evidence, confidence, interpretation, proposed action, write scope, approval requirement, execution result, and observed outcome.

## Guardrails

- Least-privilege writes
- Human approval for consequential actions
- Idempotency and retry policy
- Full run and decision auditability
- Kill switch and exception queue
