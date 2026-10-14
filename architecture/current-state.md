# Current state

Evidence only, as of 14 Oct 2026. The baseline is default-branch commit
`6bee998900b9d4488169ed3474e4887690af9184` (the PR #29 merge, 14 Oct 2026).
Anything not observed is marked as not observed. Ownership is in
`system-of-record.yaml`. Each capability's four facts are in the manifest's
`capabilities`.

## Repository

- **Default branch.** `claude/explorium-docs-mcp-brregp`. There is no `main`
  branch; some Notion links to `main` do not resolve (audit 12).
- **Architecture authority.** Effective since 9 Oct 2026. PR #24 merged this
  folder at 21:04 UTC (merge commit `1e8104b`). This is recorded in the
  manifest on 14 Oct 2026.
- **Merged since 9 Oct:** #25 (sync keys), #26 (local data directories
  untracked), #28 and #29 (`drafts/research-design-agents/`, staging only).
- **Open:** #27 (weekly sync: the master stays a candidate until the owner
  merges its data PR).
- **This change adds:**
  - ADR texts move to Notion 02 (ADR-014): `architecture/adr/` is removed and
    the manifest indexes the pages.
  - ADR-006 accepted: `crm/decision.py`, SPEC-003, and INV-06 to INV-10 and
    INV-16 normative.
  - SPEC-002 Signal record (`crm/signal.py`).
  - GAP-007 closed: unpinned updates are refused.
  - The evidence ledger (`architecture/schemas/`, `crm/ledger.py`,
    `scripts/validate_ledger.py`, `docs/research-profiles.md`), with the
    composition run's gate.
- **Invariants, offline run on this branch:**
  - ENFORCED 1 (INV-01: the Signal record type exists), PARTIAL 10,
    MISSING 3, UNVERIFIED 2. No regressions.
  - Six rules are normative and held at `expected`: INV-06 to INV-10, and
    INV-16. Of these, INV-07 needs a CRM dump and is UNVERIFIED offline.

## Tests, run 14 Oct 2026 on this branch (Python 3.13, Windows, local)

- **`python -m pytest tests -q`:** 332 passed, 8 failed.
  - The 8 failures are environment-only. They fail identically on the
    untouched default branch in this environment, where the same command
    gives 266 passed and 8 failed. CI on Linux passes them:
    - the 7 tests in `tests/test_open_data_pr.py` drive a bash script through
      Git for Windows;
    - `test_files_beneath_a_tree_are_checked_through_bare_directory_rules`
      depends on path separators.
  - New tests:
    - `test_signal.py`: 18;
    - `test_decision.py`: 16;
    - `test_ledger.py`: 20;
    - `test_compose_account.py`: 6 (ledger gate);
    - `test_crm_sync.py`: 1 (unpinned update refused);
    - `test_validate_architecture.py`: net 5.
- **`python -m pytest python/agents/account-research/tests -q`:** 26 passed,
  4 skipped (the `anthropic` package is not installed locally).
- **`python scripts/validate_architecture.py`:** 0 errors, 1 warning (the
  daily site check runs on the legacy `claude-opus-5`).
- **`python scripts/check_architecture.py --check-md`:** OK, no regressions.

The tests need `PYTHONUTF8=1` and the `tzdata` package on Windows. CI on the
pull request is the record for its head commit.

## Runtime (observed read-only on 9 Oct 2026; no setting changed)

The routines, their models and their last runs are in the manifest
(`routines`). The facts:
- The governed writers run on `claude-opus-5-5` or in a bound session.
- The morning brief runs on `claude-sonnet-5-5`; its last run was 9 Oct.
- The CRM Systems Atlas refresh runs on `claude-opus-5-5`; its last run was
  1 Oct, and the next is 11 Oct.
- The daily site check runs on `claude-opus-5`.
- The Monday Data Sync (shadow) last ran on 5 Oct, and the next is 12 Oct.
- The routine for Phase 1 close (12 Oct), the Phase 2 cutover routine
  (19 Oct) and the kickoffs for 16 Nov, 4 Jan and 1 Mar are pending.
- The Weekly CRM ledger sync is disabled (retired).

**Repository settings** (read via the API):
- `allow_auto_merge` false;
- one ruleset, "GCP branch ruleset", enforcement disabled;
- branch protection not readable from this session (403).

See GAP-014.

## Records (last read by earlier sessions; not re-read here)

- Custom CRM: 64 contacts keyed by `master_id` (25 Sep runlog), and
  1 account.
- The 34-account promotion was confirmed by the owner but not applied
  (GAP-008).
- Composition runs:
  - two run directories in `data/runs/`, both from September;
  - one filed proposal, with 3 HOLDs;
  - 0 runs in October as counted by `scripts/cost_report.py` from the
    repository (the CRM runlog was not dumped for this read).
