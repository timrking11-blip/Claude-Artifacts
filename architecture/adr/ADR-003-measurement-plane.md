# ADR-003 — Measurement Plane

Status: Proposed
Owner: Timothy King
Notion: https://app.notion.com/p/dd5cfa9c7a8b488ab04522c938482219

Imported 9 Oct 2026 from Notion 02 (page last edited 29 Sep 2026), verbatim.
Proposed: editable, not in force.

## Decision

Use GA4, Google Search Console, Google Tag Manager, consent-aware events, UTMs, and Atlas conversion identifiers as the initial measurement plane. Atlas remains the commercial authority; BigQuery stays behind the analytics gate.

## Guardrails

- Shared event taxonomy
- Consent and retention controls
- Event-time and processing-time fields
- Metric reconciliation and exception handling

## Annotations

- **2026-10-09, naming.** "Atlas" here means the Custom CRM, which holds the
  commercial records today. It is not the CRM Systems Atlas. See ADR-001's
  annotation and `architecture/README.md`, Names.
