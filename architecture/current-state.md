# Current state

Evidence only, as of 9 Oct 2026. The baseline is default-branch commit
`5cd30d3705dacbc0e60d4734d4d510eceddbe4ed` (the PR #23 merge, 3 Oct 2026).
Anything not observed is marked as not observed. Ownership is in
`system-of-record.yaml`. Each capability's four facts are in the manifest's
`capabilities`.

## Repository

- **Default branch.** `claude/explorium-docs-mcp-brregp`. There is no `main`
  branch; some Notion links to `main` do not resolve (audit 12).
- **Architecture tooling already merged.** From PR #22 (28948f3, 2 Oct):
  - `architecture/invariants.yaml`;
  - `scripts/check_architecture.py`;
  - `docs/architecture-invariants.md`;
  - CI job `architecture`;
  - `.github/CODEOWNERS`.
- **Weekly sync lands data by pull request.** From PR #23 (5cd30d3, 3 Oct);
  no workflow pushes to the default branch.
- **Not on the default branch before this change:** `architecture/adr/`, the
  manifest, the matrix, the cost code and the composition cap. The 1 Oct
  commit 5613bc9 never reached GitHub.
- **Invariants, offline run on this branch:** ENFORCED 0, PARTIAL 10,
  MISSING 4, UNVERIFIED 2 (UNVERIFIED needs a CRM dump); no regressions.
  All sixteen rules are candidates, because their ADRs are Proposed or not
  written. CI holds none of them to `expected`. Their must-not-regress
  probes still fail CI if a control weakens.

## Tests, run 9 Oct 2026 on this branch (Python 3.11, local)

- **`python -m pytest tests -q`:** 261 passed, 0 skipped. The baseline had
  192; this branch adds 69:
  - `tests/test_costs.py`: 25;
  - `tests/test_validate_architecture.py`: 35;
  - cap entry points in `tests/test_compose_account.py`: 4;
  - `tests/test_check_architecture.py`: a net 5 (from 28 to 33). Three
    URL-based standing tests were replaced by tests that only an Accepted
    ADR confers standing and that must-not-regress controls hold under
    candidate rules.
- **`python -m pytest python/agents/account-research/tests -q`:** 26 passed,
  4 skipped. The skips are in `test_model_provider.py`, because the
  `anthropic` package is not installed locally.
- **`python scripts/validate_architecture.py`:** 0 errors, 2 warnings:
  - ADR-007's transition is pending merge;
  - the daily site check runs on the legacy `claude-opus-5`.

CI on the pull request is the record for its head commit.

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
