# Architecture invariants

Rendered by `scripts/check_architecture.py --render-md` from `architecture/invariants.yaml`; CI fails when this file and the YAML disagree. Do not edit by hand.

Decisions are governed in Notion; the repository holds their executable form. Conformance is ENFORCED, PARTIAL, MISSING, or UNVERIFIED (needs `--crm-dump`). Maturity uses ADR-011's evidence levels; this check never claims PRODUCTION_VERIFIED. Status below is the offline run.

## Governing decisions

| ADR | Title | Status (as of) |
|---|---|---|
| ADR-006 | [AI Action Contract](https://app.notion.com/p/a749895b8af44375a86cba7edd7c298f) | Proposed (2026-10-02) |
| ADR-012 | [AI-Native Intelligence Core (target)](https://app.notion.com/p/3ec7ecee36a9814aa01ffdf64313dfc6) | Proposed (draft in 14 — Governance Amendment; not yet filed in 02) (2026-10-02) |
| ADR-013 | Learning and research optimisation (future) | Not written (2026-10-02) |

## Invariants

| ID | Decision | ADR | Rule | Expected | Offline | Maturity |
|---|---|---|---|---|---|---|
| INV-01 | Signal is first-class | ADR-012 | ∀ s ∈ Signal: s.id ∧ s.subject ∧ s.source ∧ s.observed_at ∧ s.kind ∈ SignalKinds, stored as a record of its own, never only as text inside another record | MISSING | MISSING | DESIGNED |
| INV-02 | Observation is not interpretation | ADR-012 | an Observation records only what a source reported (value, source, observed_at); stance and meaning attach only through Evidence(observation, hypothesis, stance) | PARTIAL | PARTIAL | CODE_EXISTS |
| INV-03 | Hypotheses are explicit | ADR-012 | Hypothesis is versioned: an edit creates version v+1 with parent = v, and no version is ever overwritten or deleted | MISSING | MISSING | DESIGNED |
| INV-04 | Negative evidence counts | ADR-012 | Evidence.stance ∈ {supports, contradicts}; contradicting input is kept, never silently discarded, and a hypothesis with unresolved contradicting evidence is never reported as supported | PARTIAL | PARTIAL | CODE_EXISTS |
| INV-05 | Temporal intelligence | ADR-012 | the state recorded at time t is an immutable snapshot: no write at t' > t alters what t recorded | PARTIAL | PARTIAL | CODE_EXISTS |
| INV-06 | Decisions are reproducible | ADR-006 | Decision.id is unique and opaque; Decision.fingerprint = H(inputs, policy_version, model, prompt) is stored separately; equal fingerprints yield equal outcomes; the ledger is append-only | PARTIAL | PARTIAL | CODE_EXISTS |
| INV-07 | Human in the loop is required | ADR-006 | ∀ action a with risk(a) ≥ threshold(kind(a)): executed(a) ⇒ ∃ authorization(a) by a human that records the check performed and covers exactly a | PARTIAL | UNVERIFIED | CODE_EXISTS |
| INV-08 | Policies are enforced | ADR-006 | every write is preceded by exactly one verdict ∈ {allow, hold, refuse} from a single policy gate, recorded with the policy version | PARTIAL | PARTIAL | CODE_EXISTS |
| INV-09 | Agents cannot bypass gates | ADR-006 | the executor refuses any action that does not carry a valid authorization id bound to that action | PARTIAL | PARTIAL | CODE_EXISTS |
| INV-10 | Execution is verified | ADR-006 | each action kind declares postconditions; after execution they are read back from the target and must hold, else the action is marked failed | PARTIAL | PARTIAL | CODE_EXISTS |
| INV-11 | Outcomes are captured | ADR-012 | Outcome(action_ref, effect, observed_at) is append-only and every outcome references the action or decision it follows | PARTIAL | PARTIAL | CODE_EXISTS |
| INV-12 | Learning is measured | ADR-012 | Evaluation(subject, metric, cohort, window, value, n, baseline) is computed from outcome records only, never typed in | PARTIAL | PARTIAL | CODE_EXISTS |
| INV-13 | Signal performance is learned | ADR-013 | signal performance is computed per (signal kind, cohort, time window) with n ≥ n_min against a baseline by a scheduled job, and stored as Evaluation records | MISSING | MISSING | DESIGNED |
| INV-14 | Research is optimized | ADR-013 | the next research step maximises expected information gain per unit cost, within the authorized budget | MISSING | MISSING | DESIGNED |
| INV-15 | Provenance is preserved | ADR-012 | every stored value has a path value → transform* → source, with observation time at the source | PARTIAL | UNVERIFIED | CODE_EXISTS |
| INV-16 | Auditability | ADR-006 | every decision, output and write carries {model, prompt_hash, policy_version, code_version} | PARTIAL | PARTIAL | CODE_EXISTS |

## Probes

MNR = MUST_NOT_REGRESS: an existing hard control that CI never lets weaken.

| Probe | Rule | Kind | Scope | MNR | What it checks | Target today |
|---|---|---|---|---|---|---|
| P-01a | INV-01 | static | core |  | a Signal record type with id | `crm.signal.Signal` |
| P-02a | INV-02 | unit | core | yes | field-level provenance carries no interpretive field (source | `crm.schema.Provenance` |
| P-02b | INV-02 | static | core |  | an Evidence record linking an observation to a hypothesis with a stance exists | `crm.evidence.Evidence` |
| P-03a | INV-03 | static | core |  | a Hypothesis record with version and parent exists | `crm.hypothesis.Hypothesis` |
| P-04a | INV-04 | unit | core | yes | a conflicting value of equal trust is held and reported | `crm.master.merge_all (conflicts_held)` |
| P-04b | INV-04 | unit | core | yes | research citing a lookalike of the specified domain is refused | `crm.guardrails.check_run` |
| P-04c | INV-04 | static | core |  | Evidence carries a stance of supports or contradicts | `crm.evidence.Evidence.stance` |
| P-05a | INV-05 | unit | core | yes | a filed run cannot be filed again | `scripts/compose_account.py finalize (run_final.json)` |
| P-05b | INV-05 | unit | core | yes | a record's notes are only ever appended to | `scripts/compose_account.py plan_account_write` |
| P-05c | INV-05 | static | core |  | a StateSnapshot record exists | `crm.snapshot.StateSnapshot` |
| P-06a | INV-06 | unit | core | yes | the same inputs give the same proposal id | `scripts/compose_account.py proposal_record` |
| P-06b | INV-06 | static | core |  | decision records carry a fingerprint separate from their id | `proposal record key "fingerprint"` |
| P-07a | INV-07 | unit | core | yes | bulk creation over the threshold holds until that exact count is confirmed | `crm.runlog.held` |
| P-07b | INV-07 | unit | core | yes | credit spend needs an approved job and a passing budget; settling an unapproved job is refused | `crm.broker.approve / crm.broker.settle` |
| P-07c | INV-07 | unit | core | yes | a HOLD names the independent check that clears it | `crm.review.with_check` |
| P-07d | INV-07 | static | core | yes | the CRM page's confirm requires a written note of the check | `artifact/crm-system.html` |
| P-07e | INV-07 | runtime | core | yes | every confirmed or applied held run records its check and confirmed_count equals created | `CRM runlog collection` |
| P-07f | INV-07 | static | core |  | a general ActionAuthorization record exists | `crm.authorization.ActionAuthorization` |
| P-08a | INV-08 | unit | core | yes | research about a lookalike domain is refused | `crm.guardrails.check_run` |
| P-08b | INV-08 | unit | core | yes | when nothing is found on the specified domain the output must say so | `crm.guardrails.check_run` |
| P-08c | INV-08 | unit | core | yes | paid enrichment without the form's permission is refused | `crm.guardrails.check_run` |
| P-08d | INV-08 | unit | core | yes | a write touching a human-owned field is refused | `crm.crm_sync.assert_not_owned` |
| P-08e | INV-08 | unit | core | yes | a proposal naming a price is refused | `account_research.tools.write_proposal._MONEY` |
| P-08f | INV-08 | static | core |  | a single policy gate returning a recorded verdict exists | `crm.policy.PolicyGate` |
| P-09a | INV-09 | unit | core | yes | settling a job that was not approved raises | `crm.broker.settle` |
| P-09b | INV-09 | unit | core | yes | a merge that would create more than the threshold writes no master | `scripts/merge_master.py` |
| P-09c | INV-09 | static | core |  | an executor that requires an authorization id exists | `crm.executor.execute` |
| P-10a | INV-10 | unit | core | yes | a write to a document of known version is pinned to that version | `crm.crm_sync.pinned` |
| P-10b | INV-10 | unit | core | yes | the data-layer validator fails on a duplicate identity | `scripts/validate_sync.py check_master` |
| P-10c | INV-10 | static | core |  | action kinds declare postconditions checked by read-back | `crm.executor.POSTCONDITIONS` |
| P-11a | INV-11 | static | core | yes | outcome kinds exist (replies | `crm.activity.TYPES / crm.crm_sync.PROPOSAL_STATUSES` |
| P-11b | INV-11 | static | core |  | a captured outcome carries a reference to its action or decision | `crm.activity.row action_ref` |
| P-12a | INV-12 | unit | core | yes | the scorecard is computed from recorded activity | `crm.activity.scorecard` |
| P-12b | INV-12 | static | core |  | an Evaluation record with cohort | `crm.evaluation.Evaluation` |
| P-13a | INV-13 | static | core |  | a calibration job computing cohort and window aware signal performance exists | `crm.calibration` |
| P-14a | INV-14 | static | core |  | an information-gain planner exists | `crm.research_planner` |
| P-14b | INV-14 | unit | guard | yes | spending fails closed without a balance | `crm.broker.budget_check` |
| P-15a | INV-15 | unit | core | yes | every merged field records its source and observation time | `crm.master.merge_all (provenance)` |
| P-15b | INV-15 | runtime | core | yes | every CRM contact carries provenance and its master key | `CRM contacts collection` |
| P-15c | INV-15 | static | core |  | transformation edges are recorded | `crm.provenance.ProvenanceEdge` |
| P-16a | INV-16 | unit | core | yes | a proposal record carries the model that produced it | `scripts/compose_account.py proposal_record` |
| P-16b | INV-16 | unit | core |  | records carry a prompt hash | `proposal record keys` |

## Gaps to ENFORCED

- **INV-01** (ADR-012): no Signal record type or store; signals exist only as rows in proposal prose and vendor fields
- **INV-02** (ADR-012): no Evidence link; stances exist only as prose tags in proposals
- **INV-03** (ADR-012): no Hypothesis record; qualification reasoning lives in proposal prose
- **INV-04** (ADR-012): no evidence edges or stance; contradictions are held only for field values and domains
- **INV-05** (ADR-012): no StateSnapshot record; CRM documents change in place under version numbers
- **INV-06** (ADR-006): the proposal id is deterministic but mixes identity with inputs; no separate fingerprint; run log status changes in place
- **INV-07** (ADR-006): no general ActionAuthorization record or approval queue; only bulk creation
- **INV-07** (ADR-006): credit spend and HOLD clearance are gated
- **INV-08** (ADR-006): policies are enforced in several places; no single gate and no recorded verdict or policy version
- **INV-09** (ADR-006): CRM writes from sessions are not executor-gated; no authorization id
- **INV-10** (ADR-006): no declared postconditions; written fields are not read back
- **INV-11** (ADR-012): outcomes are recorded but not linked to an action or decision id
- **INV-12** (ADR-012): no Evaluation record
- **INV-12** (ADR-012): cohort or baseline; only a computed scorecard
- **INV-13** (ADR-013): no calibration job; depends on INV-01 and INV-12
- **INV-14** (ADR-013): research follows a fixed cheapest-first order; no gain model
- **INV-15** (ADR-012): no transformation edges; provenance names the source but not the steps between
- **INV-16** (ADR-006): only the model is recorded
- **INV-16** (ADR-006): often as "session"; no prompt hash
- **INV-16** (ADR-006): policy version or code version
