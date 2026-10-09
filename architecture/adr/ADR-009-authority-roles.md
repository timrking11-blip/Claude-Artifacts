# ADR-009 — Authority roles under ADR-007

Status: Proposed
Owner: Timothy King
Origin: 14 — Governance Amendment (PROPOSED), 1–2 Oct 2026,
https://app.notion.com/p/3ec7ecee36a9814aa01ffdf64313dfc6. Revised 9 Oct 2026.

## Revision note

Page 14 drafted ADR-009 to supersede ADR-007 and keep governance in Notion
permanently. On 9 Oct 2026 the owner kept ADR-007 and directed that ADR-009
not be accepted as drafted.

Changes from the draft:
- **Removed:** the supersession of ADR-007, and the permanent Notion
  authority.
- **Kept:** the role of each store, which page 14 got right.

This ADR assigns no architecture authority. ADR-007 does that.

## Proposed decision

| Store | Role | Holds | Does not hold |
|---|---|---|---|
| Repository `architecture/` | Architecture authority from ADR-007's effective commit; until then, the reviewable draft | ADRs, manifest, system-of-record matrix, current and target state, audits, gaps | Operational records |
| Notion INTEGRATED GTM ARCHITECTURE | Effective authority until ADR-007's merge; the readable view after it | Reading pages, diagrams, history, the Architecture Registry (a catalog) | Authority once ADR-007 is effective |
| CRM Systems Atlas (`registry/main`) | Runtime inventory and observed status of the stack | Systems, flows, routines, connectors, observed status | Contacts and commercial records; architecture decisions |
| Custom CRM (the CRM System artifact's database) | Operational GTM system of record | Accounts, contacts, activity, runlog, jobs, credit state | Architecture; intelligence objects not yet accepted |
| AI-Native Intelligence Core | Proposed intelligence domain (ADR-012) | Nothing today | Any authority until ADR-012 is accepted and verified |
| Claude, ChatGPT and other agents | Act against the stores above | Nothing of record | Any authority. A handoff carries source and version, objective, decisions, pending work, permitted writes and verification result |

## Consequences if accepted

- An agent reads `architecture/README.md` and the manifest first, then the
  Notion pages for context, then runtime evidence.
- A disagreement between a Notion page and this folder is logged as a gap.
  It is never resolved silently in either direction.
