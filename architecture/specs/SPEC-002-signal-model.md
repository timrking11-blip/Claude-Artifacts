# SPEC-002 — Signal Model

Status: Proposed (governed by ADR-012, Proposed)
Implementation: CODE_EXISTS. `crm/signal.py` and `tests/test_signal.py`; no store, no producer
Registry row: Architecture Registry (Notion), SPEC-002. Relabelled 14 Oct 2026 from
"Current / Implemented" to "Proposed / In Progress", with the prior values kept on the row
Written: 14 Oct 2026. Until then the Notion page was blank (review flag of 1 Oct 2026)

## What a signal is

One observed commercial event about one subject: a funding round, a hiring
burst, an executive change, a site visit, a product launch, an expansion. The
sources are those the blueprint names: Vibe business events, Apollo website
visitors, and the other connectors listed below. A signal records what was
observed. It is not a score, a stage or a recommendation. Those are derived
from signals, under their own decisions (ADR-004 scoring, ADR-006 actions).

## Record

| Field | Required | Rule |
|---|---|---|
| `id` | yes | `sig_` + 16 hex: a hash of kind, subject, source, source_ref and observed_at. The same event reported twice has the same id |
| `kind` | yes | one of `funding`, `hiring`, `exec_change`, `site_visit`, `product_launch`, `expansion`, `other`. A new kind is a change to this specification |
| `subject_type`, `subject_id` | yes | `org` with an `org_id`, or `person` with a `master_id`. Stored keys only; never an email or a company name |
| `source` | yes | one of `apollo`, `vibe`, `explorium`, `crunchbase`, `web`, `gmail`, `gcal`, `manual` |
| `source_ref` | yes | the vendor event id, message id or URL it came from |
| `observed_at` | yes | ISO 8601 with a time zone |
| `hint` | no | a headline of at most 140 characters, never a page or a message body |
| `evidence` | no | ids of supporting records, such as `SRC-001` in an evidence ledger |
| `strength`, `confidence` | no | numbers from 0 to 1 |
| `expires_at` | no | after `observed_at`. A signal with no expiry never expires |
| `interpretation` | no | `{text, producer, version, at}`, kept apart from the observation. Interpreting a signal never changes its id |
| `recommended_action` | no | only together with the interpretation that produced it |

Records are immutable. A correction is a new record.

## Boundaries

- No store and no writer exist. Where signals are kept, and who may write
  them, is ADR-012's question (system-of-record matrix, `proposed` tier). Until
  then, a producer may keep signals only in files (an evidence ledger, a run
  folder), never in the CRM.
- Signals do not change stage, qualification or any CRM-owned field (Contract
  C1, ADR-006 guardrails).

## Tests

`tests/test_signal.py` (18 cases). `architecture/invariants.yaml` INV-01 (candidate,
under ADR-012): probe P-01a finds `crm.signal.Signal`.

## What moves it on

- **Accepted:** ADR-012 accepted, or SPEC-002 accepted on its own by the owner.
- **EXECUTED:** a producer (the Enrichment Broker on Vibe events, or a research
  run) writes signal files, with a dated run.
- **PRODUCTION_VERIFIED:** written acceptance criteria met over a stated window,
  with a reviewer.
