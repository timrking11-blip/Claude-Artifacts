# Run evidence store (GAP-023)

Run evidence is the files a proposal was made from. Since #26 (9 Oct 2026),
`data/runs/` is untracked, so evidence lived only in the checkout that made it.
This store keeps it durably, outside the shared repository, and every path
that files a proposal checks it first.

It is the first piece of the AI-native intelligence layer's shared evidence
capability (ADR-012, Proposed). Its interface is `crm/evidence_store.py`
(contract `evidence-store/1`). It covers the contract only, not the
Intelligence Core.

## Owner's decisions (1 Nov 2026)

| Decision | Choice |
|---|---|
| Backend | Option A: private Supabase Storage |
| Bucket | `run-evidence`, private |
| Retention | 365 days to start, subject to contractual and regulatory requirements |
| Overwriting | Prohibited; evidence keys are immutable |
| Deletion | Only through a controlled, auditable lifecycle process (not yet defined; nothing deletes automatically) |
| Missing evidence | Blocks the CRM submission |
| Legacy proposals | Quarantined until verified or re-run with authorization |
| PR #32 | Stays a draft until a live run passes acceptance |
| GAP-023 | Open until then; GAP-024 and the research-agents G0 are separate |

## What it does

| Step | Where | What happens |
|---|---|---|
| Persist | `compose_account.py finalize`, before any CRM batch is written | The run folder (except `run_final.json`) and the proposal record go to `runs/<run_id>/`, then the hash manifest, then a read-back with every file re-hashed, then a receipt, then one row in the registry. The record carries the pointer in `evidence`. |
| Gate (normal path) | same command | `gate_record` checks the pointer against the bucket and the registry. Any failure stops the run with `GATE: evidence store: …`; no batch, proposal file or `run_final.json` is written. |
| Gate (Monday catch-up) | `push_proposals_to_crm.py` | The same `gate_record` runs for every proposal file. A proposal without verified evidence is quarantined (listed as held) and never pushed. |
| Replay | `python3 -m crm.evidence_store verify RUN_ID [--record P.json]` | Verifies a stored run from a fresh process, reading only the store. |

A record is accepted only when all of these hold:
- the manifest's hash matches the record's pointer and the registry row;
- every file re-hashes to its manifest entry;
- the inputs fingerprint recomputes (`crm.decision.fingerprint` over each file path and its hash);
- the record is unchanged since it was persisted;
- a receipt exists;
- the run's `ledger.json`, if it has one, passes `crm.ledger.validate`. That rejects claims citing unregistered sources, duplicate ids, and a FACT resting only on unreviewed sources.

Each manifest file has a `kind`: `raw` (the intake manifest, web research, data sources), `derived` (state, the ledger) or `decision` (the review, the proposal record). Each manifest also carries `retain_until`, its creation date plus 365 days.

## Security boundary

- **Filing runs use a least-privilege writer, not the service role.** The writer is a dedicated Supabase Auth user, signed in with the publishable key (or the legacy anon key) plus its email and password. `supabase/migrations/20261101000000_evidence_store.sql` grants it two things on the bucket, INSERT and SELECT, and nothing else:
  - no UPDATE policy, so no overwrite (an upsert needs SELECT and UPDATE);
  - no DELETE policy, so no delete.

  `store_from_env` never accepts the service-role key.
- **Audit record.** `public.evidence_registry` holds one row per run: manifest hash, fingerprint, file count, dates, and who registered it. The writer can insert and read rows but never update or delete them. The gate cross-checks the bucket against this row, so changing a stored run also means changing a table the writer cannot touch.
- **What still bypasses this.** The service-role key, and the owner's dashboard access, bypass every policy. Keep that key out of every run environment.
  - The registry gives detection, not prevention, against that key: a change to the bucket that leaves the registry untouched still fails the gate.
  - A fully independent audit trail would need storage outside this project. That is a later decision.

## Setup (the owner)

1. **Apply the migration** to the store's own Supabase project (the owner's choice, 3 Nov 2026), not one another app shares, so the writer is the only Auth user that matters to the store. Paste `supabase/migrations/20261101000000_evidence_store.sql` into the project's SQL editor and run it. Or tell Claude to apply it with the Supabase connector. It creates the bucket, the writer allow-list, the storage policies and the registry.
2. **Create the writer user.** Go to Authentication → Users → Add user, give it an email and a long random password, and auto-confirm it. Then run this in the SQL editor, with the new user's id:
   `insert into public.evidence_writers (user_id) values ('<the user id>');`
3. **Give runs the writer, never the service key.** Edit the session's cloud environment: the environment menu in the session's title bar, then **Edit**, then the **Environment variables** row. Add these five, one `NAME=value` per line, then press **Save changes**. They must be environment variables, not network secrets. A network secret is attached as a request header by the proxy and never reaches the session, while the writer's sign-in sends the password in the request body:
   - `EVIDENCE_STORE` = `supabase`
   - `SUPABASE_URL` = the project URL
   - `SUPABASE_PUBLISHABLE_KEY` = the publishable key
   - `EVIDENCE_WRITER_EMAIL` = the writer's email
   - `EVIDENCE_WRITER_PASSWORD` = the writer's password

   Anyone who uses the environment can read its variables. That is acceptable only because the writer can do no more than add and read evidence: no overwrite, no delete. Never paste these into a chat. Routine sessions that run the Monday catch-up need the same variables.

   Under **Network access** in the same dialog, add the project's host (the host in `SUPABASE_URL`) to **Allowed domains**, keeping the package-manager default ticked, or use a broader level. Otherwise the proxy refuses the connection and `verify` reports `store unreachable: Tunnel connection failed: 403 Forbidden`.
4. **Check access without filing anything.** From a new session, run `python3 -m crm.evidence_store verify run_does_not_exist`. A working setup answers `runs/run_does_not_exist/manifest.json is not in the store`. A sign-in or HTTP error is a setup problem.

## Live acceptance (closes GAP-023; PR #32 stays a draft until then)

1. **Persist and gate.** A composition run finalizes with the store configured. Its proposal JSON carries `evidence`, and the registry has its row.
2. **Replay from a fresh session.** In a different session, `python3 -m crm.evidence_store verify <run_id> --record data/proposals/<file>.json` prints `"verified": true`.
3. **Negative checks against the live bucket.** As the writer, these must fail:
   - an upload to an existing key, with and without `x-upsert: true`;
   - a delete;
   - an update to a registry row.

   Then a hand-altered copy of the run's record must fail `verify`.
4. **A controlled CRM filing.** The run's batch is applied, and the next Monday catch-up lists that proposal as kept, not quarantined.

Record the run id, date and each result in GAP-023, and in the manifest's `CAP-evidence-store` evidence.

## Limits

- **Deletion has no lifecycle process yet.** Nothing deletes evidence. `retain_until` records when a run may be considered for deletion; the controlled, auditable process that would do it is still to be designed.
- **One persist per run id.** A changed proposal is a new run, as before. A run whose finalize crashed after persisting cannot be re-finalized under the same id.
- **Legacy proposals are quarantined.** Those filed before this change have no evidence. They stay held until verified or re-run from the intake page with authorization.
- **Not yet tested against Supabase itself.** The Supabase backend and the migration have been tested only against a fake of the Storage and REST APIs. Live acceptance is still to come.

## Rollback

- **Code:** revert the merge commit of the pull request that added this file. Composition runs then file without the store, as before. Proposal files that already carry `evidence` stay valid, because the old code ignores the field.
- **Database:** the migration only adds things: a bucket, two tables, a function, four policies. They can stay in place harmlessly. To remove them, drop them in reverse order, after copying anything the bucket holds.
- **To pause filing without reverting:** leave `EVIDENCE_STORE` unset. Runs then refuse to file and the catch-up pushes nothing. This fails closed; there is no switch that bypasses the gate.
