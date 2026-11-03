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

Status as of 15 Oct 2026. A closed gap stays listed, with what closed it.

## GAP-001 — ADR-007 transition pending merge (closed 14 Oct 2026)

- **Governs:** ADR-007 (Accepted 1 Oct 2026).
- **Closed by:** pull request #24 merged into the default branch on 9 Oct 2026 at 21:04 UTC (merge commit `1e8104bad9fff2ebb43883f99ccc12798e522ea1`). The follow-up the gap called for was made on 14 Oct 2026:
  - the manifest's `authority` reads `transition: effective` with that commit and the date 2026-10-09;
  - ADR-007's page in Notion 02 records the same;
  - the matrix gives architecture decisions to `repository-architecture`;
  - the validator passes and checks that the commit is in this history.
- **Notion 00 and 10** carry dated lines naming the effective commit (14 Oct 2026).

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
- **Applied 14 Oct 2026, on the owner's direction ("relabelling Notion as proposed or in progress").** Each row's prior value is kept on its page:
  - SPEC-002: Proposed / In Progress (record type `crm/signal.py` on this change; no store or producer).
  - ARC-001: Accepted / In Progress.
  - ADR-001: In Progress (Architecture Status stays Accepted).
  - ADR-002: In Design.
  - ADR-006: Accepted (owner, 14 Oct). SPEC-003: Accepted / In Progress.
- **Still open:** the Architecture Registry is not the authority (ADR-007), so its rows can drift again. Nothing checks them automatically.
- **Closes when:** the next reconciliation audit finds every row matching the manifest's capabilities.
- **Needs:** a reconciliation audit; no owner decision.

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

## GAP-007 — Pinned writes not universal (closed 14 Oct 2026)

- **Governs:** CLAUDE.md (version-pinned CRM writes); INV-10.
- **Was:** `crm.crm_sync.pinned` attached `if_version` only when a version was supplied (audit 12).
- **Closed by:** `pinned` raises `UnpinnedWrite` for an update with no known version. Every apply path builds its updates through it: enrichment push, proposal push, key backfill, activity capture and the composition run's account write. A dump taken without its versions file therefore stops the plan before any batch is written.
  - `tests/test_crm_sync.py::test_an_update_without_a_known_version_is_refused`.
  - Probe P-10a (must not regress) now also checks the refusal.
  - A create is not pinned; it has no version.

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
- **Now:** the status is kept as recorded on the owner's 9 Oct direction. The cost code reached the default branch with pull request #24 (1e8104b, 9 Oct 2026). ADR-008 has its own page in Notion 02 since 14 Oct 2026.
- **Target:** an owner-written acceptance record, if the owner wants one beyond the 9 Oct direction.
- **Closes when:** the owner confirms ADR-008 on its Notion page (page 14's A5), or says the 9 Oct direction suffices.
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
  - Observed 14 Oct: the repository is private on GitHub Free, and the rulesets API answers 403 ("Upgrade to GitHub Pro or make this repository public"). Required checks and code-owner review cannot be enforced on this plan.
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
- **Was:** on 1 Oct, the 00 Hub callout and Governance Authority bullet, the AI retrieval contract, and pages 10 and 13 described the repository as already authoritative, citing the unpushed commit 5613bc9 and "172 tests".
- **Now (14 Oct 2026):** the condition was met on 9 Oct, so those 1 Oct statements are now true from 9 Oct, not from 1 Oct. Dated corrections are applied to 00, 10, 12, 13 and 14 on the owner's direction of 14 Oct. They state the effective commit and date, and they correct the earlier claims rather than rewrite them.
- **Closes when:** those corrections are on the pages, which was done on 14 Oct 2026; this entry stays as the record.

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

## GAP-020 — ADR texts move to Notion (ADR-014)

- **Governs:** ADR-014 (Accepted 14 Oct 2026); ADR-007.
- **Now:** pull request #30 merged on 14 Oct 2026 at 11:02 UTC (merge commit `35c5d9e1371e082388d553c066034d9311b3231f`). ADR-014 is in effect from that commit:
  - `architecture/adr/` is gone, and the manifest's `decisions` is a Notion-URL index;
  - ADR-007 to ADR-012 and ADR-014 have pages in Notion 02;
  - the merge commit was recorded on ADR-014's page on 15 Oct 2026.
- **Limit:** CI cannot read Notion. Agreement between an ADR page and its index row is checked by the reconciliation audit, not by the validator.
- **Closes when:** the next reconciliation audit finds every ADR page and index row in agreement.
- **Needs:** a reconciliation audit; no owner decision.

## GAP-021 — Signal record without a store or producer

- **Governs:** SPEC-002, under ADR-012 (Proposed).
- **Now:** `crm/signal.py` defines and validates the record (CODE_EXISTS; `tests/test_signal.py`). Nothing produces or stores signals; they reach the CRM only as proposal prose and vendor fields.
- **Target:** a producer writes signal files (the Enrichment Broker on Vibe business events, or a research run), and ADR-012 decides where they are kept.
- **Closes when:** a dated run writes signal files that pass `validate`, and ADR-012 or SPEC-002 is accepted.
- **Needs:** the owner's decision on ADR-012; a producer in a later pull request.

## GAP-022 — Evidence ledger: first real runs

- **Governs:** the research profiles (`docs/research-profiles.md`), adopted on the owner's direction of 14 Oct 2026.
- **Now:** the schema, the validator and the composition-run gate exist (CODE_EXISTS). No real run has filed a ledger yet.
  - Runs prepared before this change record "absent".
  - The routine prompt was not changed: `prepare` itself tells the session to write `ledger.json`.
- **Target:** every composition run files a full-profile ledger that passes, and lean ledgers accompany development research.
- **Closes when:** a dated composition run finalizes with `evidence_ledger.status` "valid", and its ledger is reviewed by the owner.
- **Needs:** the next composition run; the owner's review of its ledger.

## GAP-023 — Run evidence is no longer preserved

- **Governs:**
  - the composition run's evidence copy (blueprint: "git keeps the evidence copy");
  - the research profiles (`ledger.json` per run);
  - ADR-012's proposed artifact preservation (V2 build plan R16).
- **Now:** pull request #26 (9 Oct 2026, `91979a0`, "Stop tracking local data directories") gitignored `data/runs/` and `data/master/` so the repository can be shared with advisors. Earlier runs stay in history. Since then:
  - a run folder, including its `ledger.json`, exists only in the checkout that ran it;
  - routine checkouts are discarded;
  - the manifest's composition evidence pointed at a run folder that is no longer in the tree.
- **Not the fix:** re-tracking these folders. The repository is shared, and `data/master/` holds contact data.
- **Target:** a private, durable evidence store for run folders and ledgers. The repository keeps only a manifest (run id, file, SHA-256, date) that points into it.
- **Closes when:**
  - the owner picks the store;
  - the composition run writes each run folder there with a hash manifest;
  - one run is read back from it.
- **Options for the owner:**
  - A: a Storage bucket in the existing, empty Supabase project;
  - B: a private Google Drive folder.

  Either holds evidence files only, never CRM records.
- **Needs:** the owner's choice of store.
- **1 Nov 2026:**
  - **Store chosen:** the owner picked option A, a private Supabase Storage bucket, in a Claude Code session. The owner also directed that it be built as a reusable, vendor-independent evidence contract with the composition run as its first consumer. No ADR records this yet: the ADR text goes on its Notion 02 page (ADR-014).
  - **Built:** `crm/evidence_store.py` (contract `evidence-store/1`), on a branch. A run's folder and its proposal record are persisted under a hash manifest, read back and receipted before any CRM batch exists.
  - **The Monday catch-up is gated too.** `scripts/push_proposals_to_crm.py` now applies the same check (`gate_record`), so it no longer pushes a proposal whose evidence is missing, altered or stale.
  - **Tests:** `tests/test_evidence_store.py`, with a local store and a fake Storage API.
- **Owner's decisions, 1 Nov 2026** (`docs/evidence-store.md`):
  - the bucket is `run-evidence`, private;
  - retention is 365 days to start, subject to contractual and regulatory requirements;
  - no overwriting;
  - deletion only through a controlled, auditable process;
  - missing evidence blocks CRM submission;
  - legacy proposals are quarantined;
  - PR #32 stays a draft until live acceptance.
- **Security boundary.** Filing runs sign in as a least-privilege writer (INSERT and SELECT only; `supabase/migrations/20261101000000_evidence_store.sql`), never with the service-role key. Each run also gets an append-only row in `public.evidence_registry`, which the gate cross-checks against the bucket.
- **Still open:**
  - the migration applied;
  - the writer user created;
  - the run environment configured;
  - the live acceptance in `docs/evidence-store.md` (persist, fresh-session replay, live negative checks, one controlled CRM filing);
  - the deletion process designed.

  Until then the gap stays open, and composition runs refuse to file because no store is configured.
- **3 Nov 2026:** the owner merged #32 (merge commit `1fafa9c`, 18:40 UTC) before live acceptance. A read-only check of the Supabase project the same day found:
  - no `run-evidence` bucket;
  - no `evidence_registry` or `evidence_writers` table;
  - no evidence storage policies.

  So the migration is not applied. From the merge until the store is configured:
  - `compose_account.py finalize` refuses to file;
  - the Monday catch-up (`push_proposals_to_crm.py`) pushes nothing and exits 1.

  This is the fail-closed behaviour, not a fault.

## GAP-024 — Weekly GitHub sync cannot complete

- **Governs:** the weekly CRM sync workflow (`weekly-crm-sync.yml`), the data-by-PR path (#23).
- **Now (read 15 Oct 2026, from Actions):** two problems.
  - **Apollo key rejected.** The scheduled runs of 5 and 12 Oct failed. On 12 Oct, Apollo rejected the API key: `401 … AUTH.AUTHENTICATION.API_KEY_INVALID`. In the same run, the test step lacked PyYAML; that was fixed later the same day by #25.
  - **Data step blocked by #26.** Even with a valid key, the data step cannot commit the master: `open_data_pr.sh` runs `git add -- data/master …` without `-f`, and #26 made `data/master/` gitignored. A gitignored path makes `git add` exit 1, which was reproduced locally. The master snapshot still uploads as a 90-day workflow artifact.
- **Target:** the sync completes, and the master lives where GAP-023's store decision puts it.
- **Closes when:**
  - a scheduled run succeeds end to end;
  - its master snapshot is retrievable from the chosen store.
- **Needs:** the owner:
  - a valid `APOLLO_API_KEY` repository secret;
  - the GAP-023 store choice, which decides whether the workflow writes the master to the store or the data PR carries it.
