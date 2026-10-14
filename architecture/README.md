# Architecture

## Authority

**ADR-007 is Accepted (1 Oct 2026) and effective since 9 Oct 2026.** Pull
request #24 carried this folder into the default branch
`claude/explorium-docs-mcp-brregp` on 9 Oct 2026 at 21:04 UTC (merge commit
`1e8104bad9fff2ebb43883f99ccc12798e522ea1`). That met ADR-007's condition.
The effective commit and date were recorded on 14 Oct 2026, in the manifest's
`authority` block and on ADR-007's page, and are not backdated.

- This folder is the architecture authority. The Notion architecture space
  (INTEGRATED GTM ARCHITECTURE) is its readable view.
- **ADR texts live in Notion 02, not here (ADR-014, Accepted 14 Oct 2026).**
  The manifest's `decisions` is the index: id, title, status, decided date and
  Notion URL. The owner decides on an ADR's page, and the index is updated in
  the same session. Until it is, a disagreement between page and index is a
  gap. ADR-014 takes effect when the pull request that removes
  `architecture/adr/` merges.

No change to system-of-record ownership, authority boundaries or canonical
ontology is made without an accepted ADR (ADR-007).

## Files

| File | Holds |
|---|---|
| `README.md` | This page: authority, names, status vocabulary, controls |
| `current-state.md` | What exists, with commit-pinned evidence and nothing aspirational |
| `target-state.md` | The accepted target, the proposed target kept apart, work packages, WP-IC-1 |
| `architecture-manifest.yaml` | Machine-readable index: authority, decisions, systems, capabilities, routines, cost basis, composition cap, protected digest |
| `system-of-record.yaml` | **The one ownership definition**: current, accepted target and proposed, with field groups tied to code |
| `invariants.yaml` | Implementation-independent rules per decision, with probes (`scripts/check_architecture.py`; rendered to `docs/architecture-invariants.md`) |
| `specs/` | Specifications with an executable form: SPEC-002 Signal Model (`crm/signal.py`), SPEC-003 AI Action Contract (`crm/decision.py`) |
| `schemas/` | `evidence-ledger.schema.json`: the one schema for research ledgers, both profiles (`docs/research-profiles.md`, `crm/ledger.py`) |
| `audits/README.md` | Audit index |
| `gaps/README.md` | Gap index: open questions and disagreements, each with what closes it |

## Names

Names are used by evidence, and nothing is renamed. ADR-010 (Proposed) would
make these rules binding.

| Name | Means | Not |
|---|---|---|
| **CRM Systems Atlas** | The stack inventory: an artifact whose database holds `registry/main` (systems, routines, connectors, observed status), plus its refresh routine | The contact database; the architecture authority |
| **Custom CRM** | The operational GTM system of record. Today this is the CRM System artifact and its database (contacts, accounts, activity, runlog, jobs, credits) | Architecture; intelligence objects |
| **"Atlas"** alone | Historical. In ADR-001, ADR-003 and Notion 01 it names the logical commercial and intelligence system, whose commercial part is the Custom CRM today. In this repository and CLAUDE.md, "atlas" means the CRM Systems Atlas | — |
| **GTM Command Center** | The status dashboard artifact (`dashboard/stack`, Gate 0 card, scorecard) | The governance space. Notion 01's "Notion GTM Command Center" row means the Notion architecture space |
| **Notion architecture space** | INTEGRATED GTM ARCHITECTURE, pages 00–14 | — |
| **Architecture Registry** | The Notion catalog of governed artifacts (ARC, ADR, SPEC rows) | The CRM Systems Atlas registry |
| **Ledgers** | Several different things, so always qualified:<br>- Master Contact Ledger: retired<br>- git master: `data/master/`<br>- credit ledger: `meta/credits`<br>- LEDGER_ENTRY: a proposed record type | — |
| **AI-Native Intelligence Core** | The proposed intelligence domain (ADR-012). Older text says "Intelligence Layer" | Anything in production |
| **SWAT Engine** | A proposed hosted successor implementation of the Custom CRM | A new authority |

## Status vocabulary

A capability carries four separate facts, which are never collapsed into one
label. The manifest's `capabilities` records them.

1. **Decision status.** Proposed, Accepted, Superseded, Deferred, or Not
   written. Acceptance is the owner's act and does not depend on a merge.
2. **Implementation state.** What evidence shows: DESIGNED, CODE_EXISTS,
   CONFIGURED, EXECUTED or PRODUCTION_VERIFIED.
   - Code on a branch is CODE_EXISTS, not deployed.
   - EXECUTED means one dated run, not verification.
   - PRODUCTION_VERIFIED needs written acceptance criteria met in the
     operating environment over a stated window, plus a reviewer. No script
     here claims it.
3. **Deployment.** Where it lives: branch, default branch, routine,
   artifact, GitHub Actions, external, or none.
4. **Evidence.** Commits, tests, runlog ids, trigger ids, dates.

**Documentation currency** (when a page was last reviewed) is separate again
and never counts as capability verification. These are the four facts that
ADR-011 (Proposed) describes, used here descriptively.

A correction to the Notion Architecture Registry is applied only on current
evidence, keeping the prior value (GAP-003).

## Controls

- **`scripts/validate_architecture.py`** (CI job `architecture`). It checks:
  - that the manifest, the ADR files, `system-of-record.yaml`,
    `invariants.yaml` and the code agree;
  - that every gap reference exists;
  - ADR-007's transition fields;
  - that no infrastructure identifiers or personal emails appear;
  - the protected digest.
- **Protected digest.** `protected_digest` in the manifest is a SHA-256 over
  the authority block, the decisions index and `system-of-record.yaml`. It
  detects a protected section that changed without the digest being
  regenerated (`--update-digest`). **It does not authenticate owner
  approval:** anyone who can edit the files can regenerate it.
- **CODEOWNERS.** `.github/CODEOWNERS` names the owner for:
  - the architecture source and the enforcement code (`architecture/`,
    `crm/`, `scripts/`, `.github/`, including the workflows and the
    CODEOWNERS file itself);
  - the tests (`tests/`, `python/agents/account-research/`);
  - the documentation (`docs/`, `CLAUDE.md`, `README.md`);
  - the artifact pages that probes read (`artifact/`).

  No `data/` path is owned, so the automated data pull requests stay outside
  owner review. The validator checks both. CODEOWNERS only assigns
  reviewers; a review is required only if branch protection requires code
  owner review, and none is active (GAP-014).

## Approval and identity

**Facts.**
- In this environment Claude acts on GitHub with the owner's own
  credential. Pull request #24 is authored by `timrking11-blip`, the account
  that owns the repository and is its only code owner.
- GitHub does not count a pull request author's approval, so **the owner
  cannot approve pull requests that Claude opens under the owner's
  account**. "The owner's review approves it" therefore cannot be met by a
  GitHub approval on such a pull request.
- For the same reason, GitHub cannot tell a merge by the owner from a merge
  by the session. "Claude does not merge" is an instruction Claude follows,
  not a control GitHub enforces.

**Possible arrangements.** The owner chooses; none is selected or
configured here.

| Arrangement | What it gives | Limits |
|---|---|---|
| A separate author identity for Claude: a machine-user account, or a GitHub App | The owner can approve as code owner, and required code-owner review becomes meaningful | Someone has to create the identity and manage its credentials, and the session must use only that identity. While the session also holds the owner's credential, it can still act as the owner. The identity needs write access |
| Another eligible reviewer: a second person with write access | A real approval that GitHub counts | Needs a second person, and the approval is theirs, not the owner's. It does not stop an owner-credentialed session from merging |
| Protection without required approvals: require pull requests, the `test` and `architecture` checks, no force pushes | Checks gate every change; the owner's merge is the act of acceptance | GitHub records no approval, and a merge by the session is indistinguishable from the owner's |
| Required approvals with an admin bypass: the owner merges by bypassing | The rule binds everyone else | Anyone acting as an admin can bypass, including a session holding the owner's credential. A bypass is logged, but it is not an approval |

Until the owner chooses, acceptance of a pull request is the owner merging
it. That is recorded in GitHub as the merge, not as an approval.
- **Composition cap (ADR-008).**
  - `scripts/compose_account.py prepare` counts the month's runs, by calendar
    month in America/New_York. The sources are `data/runs/` and the CRM
    runlog dump, and a retried run id counts once.
  - The 6th run holds with exit code 3 and a held runlog entry.
  - It proceeds only with `--cap-confirmation <runlog id>`, naming a held
    entry that the owner confirmed on the CRM page for that run. The dump
    must show it confirmed with a written check.
  - The flag is a reference, not an approval: a CLI flag is never
    authenticated human approval, and the run's line records which
    confirmation it relied on.
  - Counting is not atomic across concurrent sessions (GAP-016).
- **`scripts/cost_report.py`.** Prints:
  - the dated price table;
  - each routine's model and basis;
  - the month's composition count against the cap;
  - an API-list estimate for a usage file.

  These are estimates. Plan billing is not modelled.

## Order an agent reads in

Before a change that touches data models, system-of-record boundaries,
integrations, agents, scoring, attribution, measurement or workflow state:

1. Read this README, the manifest and `system-of-record.yaml`.
2. Read the relevant ADRs on their Notion 02 pages (URLs in the manifest's `decisions`), and other Notion pages for context.
3. Inspect the current implementation and runtime evidence.
4. Log any disagreement as a gap before changing code.
5. Record material changes in Notion 10 — Architecture Change Log.

Where this folder and a Notion page disagree, the disagreement is logged as
a gap and resolved by fixing Notion or by an accepted ADR. ADR text and status
are the exception: they are made on the ADR's Notion page (ADR-014).
