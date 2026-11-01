# Run evidence store (GAP-023)

Run evidence is the files a proposal was made from. Since #26 (9 Oct 2026),
`data/runs/` is untracked, so evidence lived only in the checkout that made it.
This store keeps it durably, outside the shared repository, and every path
that files a proposal checks it first.

It is the first piece of the AI-native intelligence layer's shared evidence
capability (ADR-012, Proposed). Its interface is `crm/evidence_store.py`
(contract `evidence-store/1`). It covers the contract only, not the
Intelligence Core.

## What it does

| Step | Where | What happens |
|---|---|---|
| Persist | `compose_account.py finalize`, before any CRM batch is written | The run folder (except `run_final.json`) and the proposal record go to the store under `runs/<run_id>/`. A hash manifest follows, then everything is read back and re-hashed, then a receipt is written. The record carries the pointer in `evidence`. |
| Gate (normal path) | same command | `gate_record` checks the pointer against the store. Any failure stops the run with `GATE: evidence store: …`; no batch, proposal file or `run_final.json` is written. |
| Gate (Monday catch-up) | `push_proposals_to_crm.py` | The same `gate_record` runs for every proposal file. A proposal without verified evidence is held and listed; it is never pushed. |
| Replay | `python3 -m crm.evidence_store verify RUN_ID [--record P.json]` | Verifies a stored run from a fresh process, reading only the store. |

A record is accepted only when all of these hold:
- the manifest's hash matches the record's pointer;
- every file re-hashes to its manifest entry;
- the inputs fingerprint recomputes (`crm.decision.fingerprint` over each file path and its hash);
- the record is unchanged since it was persisted;
- a receipt exists;
- the run's `ledger.json`, if it has one, passes `crm.ledger.validate`. That rejects claims citing unregistered sources, duplicate ids, and a FACT resting only on unreviewed sources.

The manifest gives each file a `kind`, which keeps raw observations apart from derived artifacts and decisions:
- `raw`: the intake manifest, web research, data sources;
- `derived`: state, the ledger;
- `decision`: the review, the proposal record.

## Limits

- **Immutability is enforced by the code, not by the bucket.** Uploads send `x-upsert: false` and refuse different bytes under an existing key. Whoever holds the service-role key can still delete objects in the Supabase dashboard.
- **Retention:** nothing deletes evidence. A retention period is the owner's decision (still open).
- **One persist per run id.** A changed proposal is a new run, as before. A run whose finalize crashed after persisting cannot be re-finalized under the same id.
- **Proposals filed before this change have no evidence.** The catch-up holds them, which matters only if they would still have found a new contact to write to.
- **Not yet tested against Supabase itself.** The Supabase backend has been run only against a fake of the Storage API. See "Closing GAP-023".

## Setup (the owner)

1. **Create the bucket.** In the Supabase dashboard, open the existing project, go to **Storage → New bucket**, name it `run-evidence`, and leave **Public bucket** off. Add no storage policies: only the service role reaches a private bucket that has none. Alternatively, Claude can create it with the Supabase connector once you say go.
2. **Give runs the key.** Edit the session's cloud environment: the environment menu in the session's title bar, then **Edit**. Add these variables:
   - `EVIDENCE_STORE` = `supabase`
   - `SUPABASE_URL` = the project URL
   - `SUPABASE_SERVICE_ROLE_KEY` = the service-role key, under Network secrets if that section is offered
   - `EVIDENCE_BUCKET` = `run-evidence` (optional)

   Never paste the key into a chat. A new session picks the variables up. Routine sessions that run the Monday catch-up need the same variables.
3. **Check access without filing anything.** From a new session, run `python3 -m crm.evidence_store verify run_does_not_exist`. A reachable store answers `runs/run_does_not_exist/manifest.json is not in the store`; anything else is a setup problem.

## Closing GAP-023

GAP-023 closes only after a real run:
1. A composition run finalizes with the store configured. Its proposal JSON carries `evidence`.
2. From a different, fresh session, `python3 -m crm.evidence_store verify <run_id> --record data/proposals/<file>.json` prints `"verified": true`.
3. The next Monday catch-up lists that proposal as kept, not held.

Then record the run id, date and result in GAP-023 and in the manifest's `CAP-evidence-store` evidence.

## Rollback

- **Code:** revert the merge commit of the pull request that added this file. Composition runs then file without the store, as before. Proposal files that already carry `evidence` stay valid, because the old code ignores the field.
- **Data:** nothing to undo. The bucket only ever receives copies of run files; it holds no CRM records, and no CRM write depends on it.
- **To pause filing without reverting:** leave `EVIDENCE_STORE` unset. Runs then refuse to file and the catch-up pushes nothing. This fails closed; there is no switch that bypasses the gate.
