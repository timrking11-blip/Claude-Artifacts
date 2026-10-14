# 14 Oct 2026: backlog remediation and the research ledger

Reviewer: Claude (Claude Code), at the owner's direction in the session of
14 Oct 2026. Baseline: default branch at `6bee998`.

## Owner directions this change carries out

| Direction (14 Oct 2026) | Recorded as |
|---|---|
| "Go with … PR twenty-two. So far as the ADR's live in Notion are concerned" | ADR-014, Accepted. ADR texts move to Notion 02; this repository indexes them |
| "For the decision protocol, create an accepted contract and a decision record" | ADR-006, Accepted. SPEC-003 and `crm/decision.py` |
| "Fix the labeling so that the signal code … under SPEC-002 [is] tested and consistent with what populates in Notion"; "Create the CRM/signal.py … relabelling Notion as proposed or in progress" | SPEC-002 written. `crm/signal.py` and its tests. Registry relabels (GAP-003) |
| "Correct for all the remaining amendment backlog … If there are strict owner decisions, omit" | GAP-001 and GAP-007 closed. Naming fixes in README.md and `scripts/merge_master.py`. Notion corrections (GAP-017) |
| "Adopt the Hermes research prompt using the two profiles … one schema … a small validator … For the composition run, include that as well" | `docs/research-profiles.md`, the evidence-ledger schema and validator, the composition-run gate. Profile files for the Macroeconomic Research Annex and Liminal Psychiatry folders (outside this repository) |
| "Run all the proposed ADR changes …" (confirmation) | The rows above |

## Found while doing it

- ADR-007's condition was met on 9 Oct 2026, when PR #24 merged, but the
  follow-up its Transition section requires was not made. It is made here,
  dated to the merge (2026-10-09), not to today.
- No Signal code existed. The Notion registry said SPEC-002 was
  "Current / Implemented" over a blank page.
- The rulesets API now answers 403 for this private repository on GitHub
  Free (GAP-014).

## Left for the owner (not done here)

GAP-002 (ADR-010), GAP-004 (WP-IC-1), GAP-005, GAP-008, GAP-009, GAP-010,
GAP-011, GAP-013, GAP-014, GAP-015, GAP-016, GAP-018, GAP-019, and acceptance
of ADR-009 to ADR-012.
