# Gap index

A gap is a place where the accepted architecture, the code and the runtime
disagree, or a question the evidence cannot settle. Every gap is listed here
with what would close it. A gap is never resolved by guessing: decisions go to
the owner, and evidence goes in the gap.

Each entry gives:
- **Governs:** the decision behind it.
- **Now:** the current state, with evidence.
- **Target**
- **Closes when:** testable acceptance criteria.
- **Needs:** whose approval or action is required.

The manifest's `capabilities[].gap` and the matrix point here.
`scripts/validate_architecture.py` fails on a reference to a gap that is not
listed.

Status as of 9 Oct 2026.

## GAP-001 — ADR-007 transition pending merge

- **Governs:** ADR-007 (Accepted 1 Oct 2026).
- **Now:** this folder exists on branch `claude/architecture-authority-cost-basis` and in its pull request. Notion is the effective authority.
- **Target:** this folder governs on the default branch; Notion is the readable view.
- **Closes when:**
  - the pull request is merged by the owner;
  - a follow-up commit records the merge commit and date in ADR-007 and in `authority.effective_commit` and `effective_date`, and sets `transition: effective`;
  - the validator passes;
  - Notion 00 and 10 get a dated line naming the effective commit.
- **Needs:** the owner's review and merge. Claude does not merge.

## GAP-002 — "Atlas" naming

- **Governs:** ADR-001 (Accepted); ADR-010 (Proposed).
- **Now:** bare "Atlas" names the logical system in ADR-001, 01, ADR-003, 04, 07, 09 and the Architecture Registry ("Atlas" surface option, "Related Atlas Objects"). "atlas" in the repository means the CRM Systems Atlas.
- **Target:** names qualified as in `architecture/README.md`, Names.
- **Closes when:** ADR-010 is accepted or rejected. Until then, notices only; nothing is renamed.
- **Needs:** the owner's decision on ADR-010.

## GAP-003 — Architecture Registry status metadata

- **Governs:** Architecture Registry rule "No silent contradictions"; ADR-011 (Proposed).
- **Before (read 9 Oct):**
  - ARC-001: Current / Implemented, but it spans proposed capabilities.
  - SPEC-002 Signal Model: Current / Implemented, with a blank specification and no Signal records (INV-01 MISSING).
  - ADR-001: Implemented, though only its commercial part is EXECUTED.
  - ADR-002: In Progress, though it is DESIGNED.
- **Prepared 9 Oct, not applied (pending the owner's approval).** These are Implementation Status corrections only, supported by current evidence. If approved, each row's page records the prior value and the evidence:
  - ARC-001: In Progress.
  - SPEC-002: In Design.
  - ADR-001: In Progress.
  - ADR-002: In Design.
- **Still open: Architecture Status.** "Current" on ARC-001 and SPEC-002 means "implemented and authoritative" under the Hub convention, and the evidence does not support it. Changing a decision status is the owner's call.
- **Closes when:** the Implementation Status corrections are approved and applied with their prior values recorded; and the owner sets the Architecture Status of ARC-001 and SPEC-002, or accepts ADR-011's mapping.
- **Needs:** the owner: approval to apply the prepared corrections, and the decision-status part of page 14's A6. As of 9 Oct no registry row has been changed.

## GAP-004 — WP-IC-1, one narrow evidence loop

- **Governs:** ADR-012 (Proposed).
- **Now:** DESIGNED. The work package and its acceptance criteria are in `target-state.md`.
- **Target:** the loop runs once, end to end, on one intake-named account.
- **Closes when:** the WP-IC-1 acceptance criteria in `target-state.md` pass.
- **Needs:**
  - the owner's go or no-go;
  - ADR-012 need not be accepted first, but no new store, ontology change, outreach, enrichment purchase or autonomous write comes with it.

## GAP-005 — Enrichment Broker spend path not executed

- **Governs:** CLAUDE.md, Phase 2 (credit ledger); D1 declined 25 Sep.
- **Now:** `crm/broker.py` plans; one job was estimated and refused; nothing has been bought. CODE_EXISTS.
- **Target:** executed only if the owner approves a job.
- **Closes when:** a future approved job settles through the broker, or the owner retires the spend path.
- **Needs:** the owner. No spend is planned.

## GAP-006 — Activity capture and Monday Data Sync to production

- **Governs:** blueprint decision D2.
- **Now:** EXECUTED. The shadow run on 5 Oct succeeded; the next is 12 Oct; cutover is the 19 Oct routine.
- **Target:** PRODUCTION_VERIFIED.
- **Closes when:**
  - two clean shadow Mondays (5 and 12 Oct) have their runlog lines and heartbeat;
  - exception counts are reported (unmatched and ambiguous identities);
  - the 19 Oct cutover is clean;
  - a reviewer is named.
- **Needs:** the scheduled routines, then the owner's review.

## GAP-007 — Pinned writes not universal

- **Governs:** CLAUDE.md (version-pinned CRM writes); INV-10.
- **Now:** `crm.crm_sync.pinned` attaches `if_version` only when a version is supplied (audit 12).
- **Target:** every apply path refuses a write with no version.
- **Closes when:** a test proves each apply path rejects a missing version.
- **Needs:** a code change in a future pull request.

## GAP-008 — 34-account promotion held

- **Governs:** CLAUDE.md, Phase 2 status (owner confirmed 25 Sep).
- **Now:** not applied. The Apollo connector has no free saved-accounts search, and audit 12 notes the documented zero-credit REST endpoint is untested.
- **Target:** 34 accounts created with validated Apollo account ids.
- **Closes when:** the ids are found by a route the owner chooses and validated, and the creation runs under the bulk-create hold.
- **Needs:** the owner's choice of route:
  - A: saved contacts, free;
  - B: company search, about 34 credits after 11 Oct;
  - C: wait.

## GAP-009 — Kill-threshold metric grain

- **Governs:** blueprint 15 Nov kill check.
- **Now:** the scorecard counts distinct contacts with qualifying activity, not sends or meetings held (audit 12).
- **Target:** the threshold and the metric use the same grain, window and attendance rules.
- **Closes when:** the definitions are written and the scorecard computes them.
- **Needs:** the owner's definitions.

## GAP-010 — Phase numbers versus work packages

- **Governs:** the blueprint phases; 01 — Living Reference Model phases.
- **Now:** Notion 01's Phase 4 is analytics and its Phase 5 is billing. The repository's Phase 4 is Engagements and its Phase 5 is the canonical store.
- **Target:** named work packages, with the phase numbers kept as history.
- **Closes when:** `target-state.md`'s mapping is accepted, and the scheduled kickoffs and Notion refer to work packages.
- **Needs:** the owner's acceptance of the mapping. The routine prompts are not changed by this pull request.

## GAP-011 — Proposal lifecycle authority

- **Governs:** none yet. Blueprint Phase 3 (proposals and intake as records) is unstarted.
- **Now:**
  - The draft text originates in git (`data/proposals/`, written by finalize).
  - The CRM note is an append-only projection of it by the same run and by the idempotent proposal push.
  - `proposal_status` is set to "drafted" by the push only when unset. Later values (sent, accepted, declined) are set on the CRM page, but the field is not in `CRM_OWNED_FIELDS`.
- **Open questions:**
  - Is the git record or the CRM field the authority for status after "drafted"?
  - Should `proposal_status` be CRM-owned in code?
- **Closes when:** the owner decides, and the matrix and code agree.
- **Needs:** the owner's decision.

## GAP-012 — ADR-008: confirmation and landing the cost code

- **Governs:** ADR-008 (Accepted 1 Oct, recorded by Claude in session).
- **Now:** the status is kept as recorded on the owner's 9 Oct direction. The cost code is in this pull request.
- **Target:** the cost code is on the default branch.
- **Closes when:** this pull request merges. If the owner wants an owner-written acceptance record beyond the 9 Oct direction, page 14's A5 stays open until they give it.
- **Needs:** the owner.

## GAP-013 — Routine settings that need the owner

- **Governs:** ADR-008.
- **Now (observed 9 Oct):**
  - The daily site check runs on `claude-opus-5`, a legacy model. Moving it to Sonnet (K5) is the owner's change in the desktop app.
  - The morning brief still lists ZoomInfo, Carly and medical connectors (K7).
- **Target:** the site check on Sonnet 5.5, and connector sets trimmed.
- **Closes when:** `get_trigger` shows the new settings.
- **Needs:** the owner, in the task settings. This pull request changes no routine.

## GAP-014 — Branch protection, approval and identity

- **Governs:** ADR-007, and the rule that no script or merge creates a decision.
- **Now (read 9 Oct):**
  - The only ruleset, "GCP branch ruleset", is disabled.
  - The branch-protection API is not readable from this session (403).
  - `allow_auto_merge` is false.
  - `.github/CODEOWNERS` assigns the owner, but no rule requires its review.
  - Pull requests from this session are authored by the owner's own account (#24: `timrking11-blip`). GitHub does not count an author's approval, so the owner cannot approve them. The session's credential is the owner's, so GitHub cannot tell the owner's merge from the session's.
- **Target:** an approval arrangement the owner chooses from `architecture/README.md` (Approval and identity), with the checks `test` and `architecture` required on the default branch.
- **Closes when:**
  - the owner has chosen and configured an arrangement;
  - a read of the branch rules shows it active;
  - the README records the choice.
- **Needs:** the owner, in repository settings and any account or app setup. Claude does not select or configure it.

## GAP-015 — HubSpot role

- **Governs:** 01 — Living Reference Model ("Resolve HubSpot first").
- **Now:** the repository says HubSpot is not installed. The 01 inventory says it is in use. A HubSpot connector is available to sessions.
- **Target:** a narrow marketing role, or retirement.
- **Closes when:** the owner decides, and the matrix records it.
- **Needs:** the owner.

## GAP-016 — Composition cap is not atomic

- **Governs:** ADR-008.
- **Now:**
  - The cap counts runs from `data/runs/` and the CRM runlog dump at `prepare` time.
  - Two sessions preparing at the same moment can both count 4 and both proceed.
  - A run prepared in another checkout, whose runlog line is not yet in the dump, is not counted.
- **Target:** good enough for a soft cap. A hard cap would need one serialized counter in the CRM.
- **Closes when:** the owner accepts the soft-cap behavior, or asks for a serialized counter.
- **Needs:** the owner.

## GAP-017 — Notion pages ahead of the transition

- **Governs:** ADR-007.
- **Now:** on 1 Oct, the 00 Hub callout and Governance Authority bullet, the AI retrieval contract, and pages 10 and 13 described the repository as already authoritative, citing the unpushed commit 5613bc9 and "172 tests".
- **Target:** Notion states the transition as pending until merge.
- **Closes when:** dated corrections are on 00, 01, 10, 12, 13 and 14 (and an index note on 02), and, after the merge, a line names the effective commit.
- **Needs:** the owner's approval. The corrections are prepared, not applied: as of 9 Oct no Notion page has been changed by this work. The post-merge line also waits on GAP-001.

## GAP-018 — ADR-007 and ADR-008 texts were reconstructed

- **Governs:** ADR-007, ADR-008.
- **Now:** commit 5613bc9 and its patch were not available. The decisions are carried verbatim from Notion 10, 00 and 13, and each file says so.
- **Target:** the original files compared, if the owner supplies the patch.
- **Closes when:** the owner supplies the 1 Oct patch or bundle and any difference is annotated, or the owner accepts the reconstructed text by merging.
- **Needs:** the owner.

## GAP-019 — Composition routine prompt does not know exit 3

- **Governs:** ADR-008.
- **Now:** the Composition run routine (`trig_01W9A9anRnfQxBWhb2FxEoPF`, on demand) treats any non-zero `prepare` exit as a stop. On exit 3 it sees the printed held entry, but its prompt does not tell it to write that entry to the CRM runlog. This change leaves scheduled-task settings untouched.
- **Target:** on exit 3, the routine writes `cap_hold.json` to the CRM runlog and tells the owner. After confirmation it re-runs `prepare` with `--cap-confirmation`.
- **Closes when:** the routine prompt carries those steps, read back with `get_trigger`.
- **Needs:** the owner's go to change the routine prompt.
