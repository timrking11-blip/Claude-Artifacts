# CRM master database changelog

Appended by `scripts/merge_master.py` on every weekly run. Each entry lists
what changed, which conflicts were held for a human, and any ambiguous
matches that were left unfused.

## 2026-09-17T14:06:10+00:00

Master now holds **67** contacts.

- **apollo**: 67 created, 0 updated, 0 unchanged, 0 field changes, 0 conflicts held, 0 ambiguous matches

## 2026-09-21T06:05:45+00:00

Master now holds **82** contacts.

- **apollo**: 15 created, 0 updated, 52 unchanged, 0 field changes, 0 conflicts held, 0 ambiguous matches
- **explorium**: 0 created, 50 updated, 0 unchanged, 0 field changes, 0 conflicts held, 0 ambiguous matches

## 2026-09-24T18:43:32+00:00

Master now holds **67** contacts.

- **dedupe**: 15 duplicate records folded by Apollo contact id. The 2026-09-21 run reported
  "15 created"; every one was an Apollo contact with no email that master already held,
  re-created because vendor ids were not identity keys. They are now (crm/schema.py), the
  merge self-heals weekly (crm/master.py:dedupe_by_vendor_id), and validate_sync.py fails
  CI on any recurrence. No field values were lost: each duplicate was folded through the
  field-level merge with its own provenance.

## 2026-09-25T19:47:56+00:00

- **key backfill** (scripts/backfill_keys.py): 64 CRM contact(s) given master_id (64 by Apollo id, 0 by email), 64 master row(s) given crm_id, 0 already keyed, 0 left unkeyed.

## 2026-09-28T06:06:42+00:00 -- HELD

Weekly sync · apollo 10 created, 0 updated, 67 unchanged; explorium 0 created, 0 updated, 49 unchanged · HELD (10 created, over 5). Master was not written.

- **apollo**: 10 created, 0 updated, 67 unchanged, 0 field changes, 1 conflicts held, 0 ambiguous matches
  - CONFLICT HELD `c_260b5a86fbab14a0` `company_name`: kept 'Culture Of Fit', rejected 'Culture Of Fit Health'
- **explorium**: 0 created, 0 updated, 49 unchanged, 0 field changes, 0 conflicts held, 0 ambiguous matches
