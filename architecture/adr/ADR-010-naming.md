# ADR-010 — Naming: Atlas, CRM Systems Atlas, Custom CRM, Intelligence Core

Status: Proposed
Owner: Timothy King
Origin: 14 — Governance Amendment (PROPOSED), section 5. Revised 9 Oct 2026.

## Why it stays Proposed

Separating ADR-001's "Atlas" into the Custom CRM (commercial records, today)
and an AI-Native Intelligence Core (journey, evidence, interpretation,
proposed) changes the ontology ADR-001 set out. Under ADR-007, an ontology
change needs an accepted ADR. The owner has not accepted this one, so it
stays Proposed.

Until then, `architecture/README.md` (Names) records how each name is used
today, from evidence. Nothing is renamed and nothing in accepted text is
rewritten.

## Proposed decision

- **CRM Systems Atlas.** The stack inventory: the artifact whose database
  holds `registry/main`, plus its page and refresh routine. It is never the
  contact database.
- **Custom CRM.** The operational CRM role. Its current implementation is
  the CRM System artifact and database. The "SWAT Engine" is a proposed
  successor implementation, not a new authority.
- **AI-Native Intelligence Core.** The proposed intelligence domain
  (ADR-012). It replaces "Intelligence Layer" and "AI Intelligence Layer" in
  new text.
- **"Atlas" alone.** Historical. It means what ADR-001 meant. New text
  qualifies it.
- **GTM Command Center.** The Claude artifact that shows status. In 01's
  system-of-record table, "Notion GTM Command Center" means the Notion
  architecture space. The proposal adds a note on 01 and does not rewrite
  it.
- **Registry and ledger.** Always qualified:
  - Architecture Registry (Notion) and CRM Systems Atlas registry.
  - Master Contact Ledger (retired), git master, credit ledger (`meta/credits`).
  - LEDGER_ENTRY is reserved for the proposed record type.

## Consequences if accepted

- ADR-001 gains a "Clarified by ADR-010" link. Its decision text does not
  change.
- Historical pages get notices, not rewrites.
