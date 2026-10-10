# ADR-001 — Atlas as GTM System of Record

Status: Accepted
Decided: 2026-09-29
Owner: Timothy King
Notion: https://app.notion.com/p/1b180e2e00d4473f97bb754b5b9b45c4

Imported 9 Oct 2026 from Notion 02 — Architecture Decision Records (page last
edited 29 Sep 2026). The sections from Context to Guardrails are the accepted
text, copied verbatim, and are not edited here. Changes go in dated
annotations or in a new ADR.

Acceptance evidence, checked 9 Oct 2026:
- the Notion page's Status reads "Accepted", dated 29 Sep 2026;
- Change Log 10 entry "2026-09-29 — Atlas accepted as GTM intelligence
  system of record", owner Timothy King;
- the Architecture Registry row ADR-001 has Architecture Status "Accepted".

## Context

Traditional CRM architecture does not adequately represent signals, behavioral journey, intelligence, content influence, or AI interpretation.

## Decision

Atlas will function as the GTM intelligence system of record. It will own canonical commercial entities and the journey connecting them.

Source tools enrich, activate, measure, or execute; they do not become competing commercial authorities.

## Consequences

Atlas does **not** replace:

- GA4
- Apollo
- Clay
- LinkedIn
- Squarespace
- GitHub

Instead, Atlas integrates and interprets them.

This decision governs the system-of-record matrix, Atlas logical data model, journey and evidence graph, inbound capture, enrichment, and integration trust boundaries.

## Guardrails

- Field-level ownership and reviewed merges
- Canonical IDs and deduplication
- Auditable state changes
- No silent overwrite of verified data

## Annotations

- **2026-10-09, naming (no change to the decision).** "Atlas" in this ADR is
  the logical commercial and intelligence system. Today its commercial part
  is implemented by the Custom CRM (the CRM System artifact and its
  database). Its journey and evidence part is not implemented. It is not the
  CRM Systems Atlas, which is the stack inventory (`registry/main`). ADR-010
  (Proposed) would record this. Until ADR-010 is accepted, read "Atlas" here
  by this note; nothing is renamed. See `architecture/README.md`, Names.
- **2026-10-09, implementation metadata.** The Architecture Registry row says
  Implementation Status "Implemented". The evidence supports the commercial
  part only (EXECUTED); the journey and evidence graph is DESIGNED. The
  registry correction is proposed in GAP-003 and not applied.
