# Composition run: from the Intake page to the CRM, one button

The Account Composition Intake page
(https://claude.ai/artifact/BtU87XpWsN9VDNTFwidnA3) is the preferred way to
engage the account-research agents and to file a prequalification proposal
that came in through LinkedIn. Nothing is copied into a terminal.

```
Intake page                                   Session that owns this repo
───────────                                   ──────────────────────────
paste request · name account · disposition
press Run ──► db  runs/<run_id> = {manifest, status: queued}
          ──► Claude Code Remote · fire_trigger(trig_01W9A9anRnfQxBWhb2FxEoPF, text={run_id, manifest})
                                              ▼
                                   git pull · dump CRM (contacts + accounts, with versions)
                                   scripts/compose_account.py prepare      ──► runs/<id> status running, steps
                                   summarise page · draft proposal (LLM legs)
                                   scripts/compose_account.py finalize     ──► data/proposals/<slug>-<date>.{json,md}
                                   ArtifactData batch (CRM contact notes, account record)
                                   ArtifactData update runs/<id> ◄── run_final.json (founder note, proposal, ids)
                                   git commit data/runs/<id> + data/proposals · push
page renders live: sequence lamps · note to the founder · proposal · CRM ids
```

The CRM refresh is unchanged: the Monday chain (06:00 UTC Action merge →
11:00 Apollo ⇄ CRM sync → 11:30 enrichment push → 12:00 GTM refresh) still
carries enrichment, `proposal_ready` flags, and any proposal file a run left
unapplied. A button run writes only its own proposal note and account record.

## Why the run lands in this session

Fresh-session routines never get `ArtifactData` (proven twice on 24 Sep
2026), so the routine **Composition run (Intake page button)** is bound to
the session that built the pipeline, the same way the Monday 11:30 routine
is. That session has the repo, `ArtifactData`, `WebFetch` and the Apollo
connector. It is woken by `fire_trigger`, which the page calls through the
viewer's own `Claude Code Remote` connector (consent asked once per page).

Cost: the routine runs on that session's model. Switch it to
`/model claude-opus-5` before the first run; the only language-model work is
the page summary and the proposal draft. Everything else is scripts.

## What the page does

| Step | On the page | In the run |
|---|---|---|
| 00 LinkedIn request | request text (required), post URL, requester | `request_text` for the composer; the founder note reads it for pricing asks |
| 01 Precondition | account name / domain / existing CRM id, LinkedIn-source tick (`state.account.source`, `crm.pre_qual`) | `find_account` against `data/master/contacts.json`; an unknown account still runs, with a Note |
| 02 Optional state | include/skip + settings, as before | opt-outs are recorded in the manifest and the founder note |
| 03 Disposition | apollo / manual | `manual` mints `crm_<date>_<rand>` with `pending_apollo`; `apollo` gets a HOLD only if `meta/config.account_lists` is empty at run time |
| 04 Run | **Run composition** | writes `runs/<id>` in the page's database, fires the routine; the sequence lamps follow `steps` live |
| 05 Result | note to the founder, proposal, CRM ids, run history | rendered from `runs/<id>` via `onSnapshot` |
| 06 By hand | the old copy-manifest path | only when the connector is not available in that view |

Per-viewer drafts stay in the browser (`localStorage`). Run records are
shared (`db` capability); Claude reads and updates them with `ArtifactData`
against the intake artifact URL.

## The note to the founder

Computed by `crm/founder_note.py` from the manifest, the run state and the
CRM dump; tested criterion by criterion in `tests/test_founder_note.py`.

**HOLD** — the proposal is drafted and filed, the run ends `needs_founder`,
`proposal_status` stays `drafted`, nothing goes out:

1. The request talks about money, rates, budget, retainer, hourly, pricing or
   a quote. No market rates are set; the founder decides what to say.
2. A matched CRM contact already carries a `proposal_ref` (a repeat).
3. A matched contact is flagged `disqualified` or `removed_from_list`.
4. A matched contact is at stage `meeting`, `proposal` or `won` (open deal).
5. Disposition `apollo` while `meta/config.account_lists` is empty (the routine reads
   that setting live and passes `--account-lists-present` when it is not).
6. The run started inside Mon 06:45–08:15 ET (the sync window).
7. Any judgement call the composer made (`--composer-flag`): request outside
   the advisory practice, unrealistic deadline, conflict of interest, a
   person named who is not in the research.

**Note** — for information; the run ends `done`:

8. No CRM contact matched (proposal filed on the account record only).
9. No matched contact is `proposal_ready` (cold outreach).
10. Account not in the enriched data layer, ledger quality below the floor,
    or every ledger contact older than 90 days.
11. Website fetch failed; warehouse findings are the sentinel.
12. Keys opted out at intake.

The note is stored in the proposal record (`founder_note`), printed under the
proposal in the contact's CRM notes (`Founder note:` block), shown on the
page, and written to `data/runs/<id>/founder.json`.

## Files a run leaves behind

```
data/runs/<run_id>/
  manifest.json        exactly what the page sent
  state.json           account, account_contacts, ledger_quality, website_summary, warehouse_findings
  founder.json         holds, notes, text, matched_doc_ids
  prompts.md           the two prompts the session answered
  website_summary.txt  (when a page was fetched)
  proposal.md          the draft as composed
  run_update.json      first page update (steps after the deterministic legs)
  run_final.json       last page update (status, founder note, proposal, CRM ids)
data/proposals/<slug>-<date>.json|md   the filed proposal (push_proposals_to_crm.py reads the JSON)
data/artifact/crm/compose_<run_id>/    the ArtifactData batch (gitignored)
```

## Running it by hand

From the repo root, with a CRM dump made by `ArtifactData list` (contacts and
accounts, each with its versions file):

```
python3 scripts/compose_account.py prepare data/runs/<id>/manifest.json --run-id <id> --crm-dump <dump>
# answer data/runs/<id>/prompts.md → website_summary.txt, proposal.md
python3 scripts/compose_account.py finalize <id> --proposal data/runs/<id>/proposal.md \
    --website-summary data/runs/<id>/website_summary.txt --crm-dump <dump> [--composer-flag "…"]
# then ArtifactData batch with data/artifact/crm/compose_<id>/writes.json
```

`prepare` exits 2 on a gate failure (no account name or domain, null
disposition, ambiguous account) or a halt (`on_fetch_error: halt`).
`finalize` exits 2 when the draft is missing one of the five headings or
mentions money — the same checks as the agent's `write_proposal` tool.

## Rules the run keeps (from the account-composition-run skill)

Never write `stage`. Notes are append-only. Never let an empty value
overwrite a populated one (every CRM write is a field merge of what changed,
pinned with `if_version`). Search `accounts` before creating one. Write the
sentinel rather than leaving `warehouse_findings` unset. Never invent a fact
about the company. The run never calls `pull_apollo.py`, `push_apollo.py` or
`merge_master.py`, and never writes to the CRM except through the
`writes.json` it emitted.
