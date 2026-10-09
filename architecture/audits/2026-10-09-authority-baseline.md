# 2026-10-09 — Authority baseline and disposition of page 14

Prepared by Claude (Claude Code) at the owner's request on 9 Oct 2026. The
owner's direction: "Repo governs: accept ADR-007". ADR-007 stays accepted, and
its transition takes effect when the authority change reaches the verified
default branch. A blocked push does not rescind it. ADR-009 is not accepted as
drafted.

## Baseline

**Repository.**
- `timrking11-blip/Claude-Artifacts` is public. Its default branch is
  `claude/explorium-docs-mcp-brregp`, at 5cd30d3 (the PR #23 merge,
  3 Oct 2026).
- No pull requests were open.
- This session can push.
- f0deeaa (the PR #21 merge) is historical evidence: it was the default
  branch when audit 12 and page 14 were written.

**Commit 5613bc9.**
- It is not on GitHub: the commits API returns 422 "No commit found".
- It is not in this checkout.
- Its patch and bundle were delivered only in the 1 Oct Cowork chat. They
  were not found in this container, in Notion attachments or in Google
  Drive.
- This change is therefore built from the recorded decisions (Notion 00, 10,
  13 and 14) and the owner's 9 Oct requirements, and not from the patch
  (GAP-018).

**What landed between 1 and 9 Oct.** From another session, through PR #22
and PR #23:
- `architecture/invariants.yaml`, `scripts/check_architecture.py` and the
  CI job `architecture`;
- CODEOWNERS;
- the weekly sync landing data by pull request.

None of the patch's described files (`architecture/adr/`, the manifest,
`crm/costs.py`, the composition cap) had landed.

**Notion, read 9 Oct.**
- Read: pages 00, 01, 02, 10, 12, 13 and 14, ADR-001 to ADR-006, and the
  Architecture Registry (11 rows).
- On 1 Oct, pages 00, 10 and 13 described the repository as already
  authoritative and cited "172 repository tests". Those tests existed only
  on the unpushed branch.
- On 9 Oct, after this branch's revisions, `tests/` passes 265. That is
  the baseline's 192 plus 73 added here (see `current-state.md`); it is not
  the historical 172.

## Disposition of 14 — Governance Amendment (PROPOSED)

Page 14 stays a proposal. Each recommendation is listed below with its
disposition. "Where" names the repository file that carries it. Notion and
Architecture Registry edits listed below are **prepared and pending the
owner's approval; none has been applied** (GAP-003, GAP-017).

| # | Page 14 recommendation | Disposition | Where |
|---|---|---|---|
| §0 | Correct Claude's 1 Oct overstatement: authority not in force; 5613bc9 unpushed; "172 tests" from an unpushed branch | **Adopted** as fact | ADR-007 (Transition), current-state; Notion 00, 10, 13 corrections prepared, not applied |
| §0, A1 | Reaffirm that Notion governs; ADR-007 "never took effect" and is superseded by ADR-009 | **Not adopted.** ADR-007 stays Accepted with its transition pending merge. Notion governs only until then | ADR-007, README |
| §1.1, §2 | ADR-009 authority hierarchy | **Revised.** The store roles are kept; the Notion-permanent authority and the supersession are removed. Proposed | ADR-009 |
| §1.2, §5 | ADR-010 naming | **Adopted as Proposed.** Used by evidence in the README (Names); nothing renamed; ADR-001 annotated without editing its decision | ADR-010, README, ADR-001/ADR-003 annotations |
| §1.3, §6 | ADR-011 single seven-step status ladder | **Revised** into four separate facts (decision status, implementation state, deployment, evidence), plus documentation currency kept apart. Proposed; the fields are used descriptively in the manifest | ADR-011, manifest |
| §7 | Capability-status corrections | **Adopted as observations** in the manifest's capabilities. Registry Implementation Status corrections prepared on current evidence, not applied; Architecture Status left to the owner | manifest, GAP-003 |
| §1.6, §8 | ADR-012 Intelligence Core and WP-IC-1 | **Adopted as Proposed.** WP-IC-1's acceptance criteria are written; not started; no store, ontology change, outreach, enrichment or autonomous write | ADR-012, target-state, GAP-004 |
| §9 | No `architecture/adr/`; ADRs stay in Notion | **Not adopted.** Under ADR-007 the ADRs live here. ADR-001 to ADR-006 are imported verbatim, with statuses unchanged | adr/ |
| §9 | System-of-record matrix; `audits/`; `gaps/` | **Adopted.** One matrix (the only ownership definition); an index file each for audits and gaps | system-of-record.yaml, audits/, gaps/ |
| §9 | Digest pinned to a Notion ADR reference | **Revised.** The digest covers the repository's protected sections, and is documented as detecting drift, not authenticating approval | README Controls, validate_architecture.py |
| §9 | Cost forecast out of current-state | **Adopted.** No forecast or spend figure is in the repository; prices are dated list prices | manifest cost_basis |
| §9 | `CLAUDE.md` pointer instead of a section | **Adopted** | CLAUDE.md |
| §3 | Hub: restore "Notion is authoritative" | **Not adopted.** A dated correction stating the pending transition is prepared instead, not applied | Notion 00 (pending) |
| §3 | 01, 10, 12, 13 notices | **Adopted, revised wording** (pending transition, not ADR-009); prepared, not applied | Notion (pending) |
| §3 | 02: file ADR-007 as historical and ADR-009 to ADR-012 as child pages | **Revised.** A dated index note pointing to `architecture/adr/` is prepared, not applied; no child pages | Notion 02 (pending) |
| §3 | ADR-001 "clarified by ADR-010" link | **Deferred** until ADR-010 is accepted | GAP-002 |
| §3 | Notes on ADR-003, 04, 07, 09 | ADR-003 annotated in the repository; Notion 04, 07 and 09 **deferred** with GAP-002 | — |
| §3 | Five historical notices on page 11 | **Deferred.** Page 11 was not in this change's scope; the existing 1 Oct reconciliation on it stands | — |
| §3, A6 | Registry: new rows for ADR-007 to ADR-012; new surface options; a "Capability Status" property | Rows **adopted**, prepared, not added. Schema changes (options, property) **deferred** with ADR-010 and ADR-011 | Notion registry (pending) |
| A5 | Confirm ADR-008 or downgrade it | ADR-008 stays Accepted per the owner's 9 Oct direction; the evidence and the open question are in GAP-012 | ADR-008 |
| A8 | Revise the branch and open a pull request | **Pull request opened** (#24) and revised once on the owner's instruction; not merged. Merging is the owner's | — |
| A9 | Keep or revert the model changes | **Unchanged.** Observed on 9 Oct: brief on Sonnet 5.5, atlas refresh on Opus 5.5 | manifest routines |
| §10 | Gap report structure, GAP-001 to GAP-012 | **Adopted, renumbered** to GAP-001 to GAP-018 with what closes each | gaps/README.md |

## Revision 1 (9 Oct 2026, on the owner's instruction; repository only)

- **Completion claims reconciled with execution.** No Notion page or
  Architecture Registry row has been changed by this work. Every Notion and
  registry edit above is prepared and pending approval (GAP-003, GAP-017).
- **CODEOWNERS** now also covers `tests/`, `docs/`, `artifact/`,
  `python/agents/account-research/`, `CLAUDE.md` and `README.md`. No `data/`
  path is owned. The validator checks both.
- **Approval.** This pull request is authored by the owner's account, so the
  owner cannot approve it on GitHub. The README's "Approval and identity"
  describes the possible arrangements and their limits; none is selected or
  configured (GAP-014).
- **Checker defect fixed.**
  - A Notion URL or a filed Proposed ADR no longer confers normative
    (accepted-policy) standing; only an Accepted ADR does.
  - The fourteen rules under ADR-006 and ADR-012 (both Proposed) are now
    candidates, like the two under ADR-013 (not written), so none is held
    to `expected`.
  - Every must-not-regress probe still fails CI under a candidate rule.
    This is tested on the committed source: every offline must-not-regress
    probe, forced to fail, is reported as a regression.

## Revision 2 (9 Oct 2026, on the owner's instruction; repository only)

- **The CODEOWNERS check evaluates ownership, not patterns.**
  - Each rule's owners are read.
  - The last matching rule wins, and a rule with no owners leaves a path
    unowned, as on GitHub.
  - Every required path must resolve to `controls.code_owner`, and no data
    path may resolve to any owner.
  - Negative tests cover ownerless entries, later rules that remove or move
    ownership, data paths matched at any depth, and patterns the checker
    cannot evaluate exactly.
- **ADR-007.** The Consequences wording from the first commit is restored.
  The identity limitation and the interim acceptance arrangement are
  appended as a dated annotation.

## Revision 3 (9 Oct 2026, on the owner's instruction; repository only)

- **CODEOWNERS ownership is checked file by file, not only at the tree
  root.**
  - Every tracked file under each required tree must resolve to the owner,
    and every tracked file under each data tree to no owner.
  - Every rooted rule that targets a descendant is evaluated too, so a later
    rule on one file is caught even before the file exists.
  - Negative tests:
    - `/scripts/check_architecture.py` with no owner fails;
    - `/data/master/contacts.json @someone` fails;
    - bare directory rules are judged through the files they actually match.

## Not done, and not to be done without the owner

- Merging.
- Any Notion page or Architecture Registry edit (prepared, pending approval).
- Changing repository settings or branch protection.
- Changing any routine's model, schedule, connectors or prompt.
- Buying anything or spending credits.
- Sending outreach.
- Enabling autonomous writes.
- Changing system-of-record ownership.
- Editing accepted ADR text.
- Changing the Architecture Registry schema.
- Setting an Architecture Status.
