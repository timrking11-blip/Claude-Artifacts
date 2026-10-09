# ADR-007 — Architecture authority moves to the repository

Status: Accepted; transition pending merge
Decided: 2026-10-01
Owner: Timothy King
Effective commit: pending
Effective date: pending

## Where this text comes from

The owner accepted this decision in the 1 Oct 2026 Cowork session, answering
"Repo governs: accept ADR-007". The ADR file from that session (commit
5613bc9 on a branch that was never pushed) did not reach GitHub, and no copy
of the commit or its patch was available on 9 Oct 2026. The Decision section
below is therefore the decision as recorded on 1 Oct, verbatim, in Notion
10 — Architecture Change Log (entry "2026-10-01 — Architecture authority
moves to the repository"), and in 00 — Architecture Hub.

Acceptance evidence, checked 9 Oct 2026:
- Change Log 10, 1 Oct 2026: "Owner: Timothy King (accepted ADR-007 in the
  1 Oct Cowork session, after being shown that Notion was the authority on
  record and that page 12 had recommended keeping it here)." Claude wrote
  this entry.
- 00 Hub, Current governance state: "ADR-007 … — Accepted (1 Oct 2026)".
- 14 — Governance Amendment (PROPOSED), section 0, quotes the owner's answer
  "Repo governs: accept ADR-007".
- 9 Oct 2026: the owner reaffirmed "Repo governs: accept ADR-007". They
  directed that the decision stays accepted, that the transition takes
  effect when the authority changes reach the verified default branch, and
  that a blocked push does not rescind it.

## Decision

As recorded on 1 Oct 2026:

> The repository's `architecture/` folder becomes the architecture authority:
> `README.md`, `current-state.md`, `target-state.md`,
> `architecture-manifest.yaml` and `adr/`. Notion becomes the readable view.
> Rule: no change to system-of-record ownership, authority boundaries or
> canonical ontology without an accepted ADR, enforced in CI by a digest of
> the manifest's protected sections.

> The authority takes effect when the folder lands on the default branch.

## Transition

- **Condition.** The pull request carrying this folder merges into the
  default branch `claude/explorium-docs-mcp-brregp`. A local commit, a pushed
  branch or an open pull request does not meet it.
- **Until then.** Notion (INTEGRATED GTM ARCHITECTURE: 00 Hub, 01, 02 and the
  Architecture Registry) remains the effective architecture authority. This
  file says only that the decision is accepted, not that authority has moved.
- **On merge.** A follow-up commit records the merge commit and its date in
  the two header lines above and in `architecture-manifest.yaml`
  (`authority.effective_commit`, `authority.effective_date`). It changes the
  status to "Accepted; effective". The dates are never backdated: the
  effective date is the merge date, not 1 Oct.
  `scripts/validate_architecture.py` fails if the status and those fields
  disagree.
- **After merge.** This folder governs. Notion is the readable view. Where
  the two disagree, the disagreement is a gap (`architecture/gaps/`),
  resolved by fixing Notion or by an accepted ADR here.

## Alternatives considered

- Keep Notion as the authority. This was recommended by 12 — Architecture
  Reconciliation Audit (1 Oct) and by 14 — Governance Amendment's draft
  ADR-009 (1–2 Oct). The owner chose the repository on 1 Oct and again on
  9 Oct. ADR-009 is not accepted as drafted; see its file.

## Consequences

- The digest in `architecture-manifest.yaml` detects a protected section
  (authority, decisions, the system-of-record matrix) that changed without
  the digest being updated. It does not authenticate the owner.
- Claude opens pull requests under the owner's account, so the owner cannot
  approve them on GitHub. Until the owner chooses another arrangement (see
  `architecture/README.md`, Approval and identity), the owner's merge is the
  acceptance.
- ADR-001 to ADR-006 were imported with their statuses unchanged. Nothing was
  promoted.

## Annotations

- **2026-10-02.** 14 — Governance Amendment (PROPOSED) proposed ADR-009 to
  supersede this ADR and restore Notion as the authority. That proposal was
  not accepted.
- **2026-10-09.** The owner retained this decision and directed the
  transition above. Page 14's useful parts were carried into ADR-009
  (revised: roles, not authority), ADR-010, ADR-011 and ADR-012, all
  Proposed. The disposition is in
  `audits/2026-10-09-authority-baseline.md`.
