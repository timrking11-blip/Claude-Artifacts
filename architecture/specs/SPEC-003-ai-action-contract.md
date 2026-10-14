# SPEC-003 — AI Action Contract and decision record

Status: Accepted with ADR-006 (owner, 14 Oct 2026). This text takes effect when the pull request carrying it merges
Implementation: CODE_EXISTS. `crm/decision.py` and `tests/test_decision.py`; no store, no writer
Decision: ADR-006 — AI Action Contract (Notion 02), accepted 14 Oct 2026

## The contract (ADR-006, field for field)

`ActionContract`: `inputs`, `evidence`, `confidence`, `interpretation`,
`proposed_action` (`kind`, `target`, `summary`), `write_scope`,
`approval_requirement` (`human` or `none`), `execution_result`,
`observed_outcome`, and `contract_version` ("1").

Action kinds:
- **consequential:** `send`, `spend`, `stage_change`, `bulk_create`,
  `publish`, `external_write`. These always need `human` approval (INV-07,
  INV-08).
- **routine:** `crm_field_fill`, `note_append`, `activity_append`,
  `ledger_write`, `report`. These are bounded by an existing control such as
  pinned writes, empty-never-overwrites or append-only activity.

## The decision record

`DecisionRecord` keeps what a decision on one contract leaves behind:

- `id`: opaque (`dec_` + random). It never encodes the inputs.
- `fingerprint`: `fp_` + SHA-256 of the inputs, policy version, model and
  prompt version. It is stored separately from the id (INV-06).
- `subject_ids`: stored keys of the records the decision is about.
- `policy_version`, `model`, `prompt_version`: what produced the decision.
  For a deterministic rule, `model` is `rule` and `prompt_version` is the
  rule's version (INV-16).
- `rationale`, `alternatives`.
- `decision`: `pending`, `approved`, `rejected` or `deferred`.
- `reviewer`, `decided_at`: required on any decided record that needs human
  approval.
- `execution_id`, `supersedes`.

## Rules (`crm.decision.validate`, `crm.decision.append`)

1. A consequential action requires human approval. An approved one names
   its reviewer and the time, with a time zone.
2. An execution result exists only for an approved contract. An observed
   outcome exists only for an executed one.
3. A write scope is always named.
4. The ledger is append-only. A change is a new record that supersedes the
   old one. A record is superseded at most once, and never edited or written
   twice.

## Boundaries

- There is no store and no writer. Where decision records are kept is the
  producer's concern, under its own rules. Nothing writes them to the CRM
  today.
- The existing controls are not replaced: the bulk-create hold, the HOLD
  check, "Review before sending", and broker approval. A future executor
  would sit behind them (INV-09, probe P-09c).

## Tests

- `tests/test_decision.py` (16 cases).
- INV-06 to INV-10 and INV-16 are normative from 14 Oct 2026. CI holds each at
  its expected level, and probe P-06c holds the id, fingerprint and
  append-only rules.
