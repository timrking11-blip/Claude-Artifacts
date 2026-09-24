# Composition run: from the Intake page to the CRM, one button

The Account Composition Intake page
(https://claude.ai/artifact/BtU87XpWsN9VDNTFwidnA3) is **the one process** for
engaging the account-research agents and filing a prequalification proposal,
LinkedIn or otherwise. Nothing is copied into a terminal, and there is no
second path: the GitHub Actions request queue that briefly existed
(`data/prequal/requests/`, `prequal-proposal.yml`) was retired on 24 Sep 2026
and its one request (Claridi.ai) moved to `data/runs/run_20260924_claridi/`.

```
Intake page                                   Session that owns this repo
───────────                                   ──────────────────────────
paste request · name account · disposition
press Run ──► db  runs/<run_id> = {manifest, status: queued}
          ──► Claude Code Remote · fire_trigger(trig_01W9A9anRnfQxBWhb2FxEoPF, text={run_id, manifest})
                                              ▼
                                   git pull · dump CRM (contacts + accounts, with versions)
                                   scripts/compose_account.py prepare      ──► runs/<id> status running, steps
                                   0 data sources: Apollo (org enrich, people), Vibe Prospecting
                                     (match, firmographics, events)          ──► data_sources.md, coverage.json
                                   1 web research: site → company → market → competitors → adjacent
                                     → macroeconomics (the session's own web tools, briefed by
                                     account_research/tools/web_research.py SYSTEM)
                                   2 summarise page (when our fetch got it)
                                   scripts/compose_account.py brief        ──► proposal_prompt.md, research filled in
                                   3 draft the SMI proposal (ValueFirst "Why now" section required)
                                   scripts/compose_account.py finalize     ──► data/proposals/<slug>-<date>-<run_id>.{json,md}
                                   ArtifactData batch: ONE merged note into the CRM record's pre-qual
                                     phase — proposal · note to the founder · review · research coverage · sync schedule
                                   ArtifactData update runs/<id> ◄── run_final.json (review, note to the founder, proposal, ids)
                                   git commit data/runs/<id> + data/proposals · push
page renders live: sequence lamps · review · note to the founder · proposal (Download PDF) · CRM ids
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

Cost: the routine runs on that session's model. The language-model work is
the web research, the page summary and the proposal draft; everything else is
scripts. The research runs on the session's own web tools, so no Anthropic API
key is needed (the agent package's `web_research` tool, which calls the API
directly, is the same brief for `adk web` development only).

## Guardrails (the intake form is the specification)

Enforced in code by `crm/guardrails.py` at `finalize`; a breach refuses the
run before anything is written, and the routine may not loosen a rule to get
past it.

- **Domain lock.** The prospect is the company at the intake form's domain.
  A similarly named company at another domain (edit distance of two or less,
  or one label containing the other, e.g. clarid.ai for claridi.ai) is never
  used: if one appears in the research, the data-source findings or the
  proposal's citations, the run is refused.
- **No credit spend off-form.** Apollo organization enrich and Vibe
  Prospecting enrichment run only when the intake form's "Allow credit spend"
  box is ticked, and only for the intake domain. A source that reports data
  without the tick refuses the run.
- **Empty means empty.** When no source finds anything on the intake domain,
  the proposal is a not-found note: it must say "not found", may cite only
  that domain and primary macro sources (.gov, Federal Reserve banks,
  BIS/IMF/OECD), and the review carries a HOLD to confirm the domain.
- **One proposal per run.** A filed run cannot be re-finalized; a changed
  proposal is a new run started on the intake page, so every CRM note traces
  to one form submission.
- **Void, never delete.** A proposal found to be wrong is voided with an
  appended note and `"void": true` on its file; the Monday catch-up never
  re-applies a void proposal.

## Order of operations

1. **Intake** — request, account, options, disposition; press Run.
2. **Gate and ledger** — `prepare`: find_account, contacts, ledger quality,
   our own fetch of the site, warehouse sentinel, review criteria.
3. **Data sources** — the session pulls Apollo (organization enrich, people at
   the domain) and Vibe Prospecting (business match, firmographics, events),
   surfacing any credit cost first, and records each source's outcome in
   `coverage.json`.
4. **Web research** — company, market and buyer, competitors, adjacent items
   (parent, partners, customers, investors, hiring, leadership backgrounds),
   and the macroeconomic context with dated primary sources.
5. **Brief and draft** — `brief` fills the SMI proposal prompt; the session
   drafts it, including the ValueFirst **Why now** section.
6. **File and note** — `finalize` validates, files the proposal, and plans one
   merged note for the CRM record: the proposal, the note to the founder, the
   review, research coverage per source, and the Apollo / CRM sync schedule for the record.
   `pre_qual` is set on the record; `stage` is never touched.
7. **Sync** — the Monday chain carries the record on: 06:00 UTC merge into the
   data layer, 11:00 Apollo ⇄ CRM (uploads `pending_apollo` accounts and
   re-keys them), 11:30 enrichment push + proposal catch-up, 12:00 GTM refresh.

## The research leg ("agent crawlers")

`prepare` writes the research desk brief into `prompts.md`: fetch the
company's own site first (home, about, product, customers, team, careers,
news), then search the company by name and domain, then its market, buyer and
competitors. The memo comes back under fixed headings (Company, Evidence of
stage, Market and buyer, Competitors, Signals worth a conversation, Gaps) with
a source link and an evidence tag -- `[supported]`, `[needs stipulation]`,
`[unsupported]` -- on every factual sentence. The session saves it as
`web_research.md` plus `web_sources.txt`; `brief` stores both in the run state.
It runs even when our own page fetch failed: a site that blocks plain HTTP
fetchers is often still readable from the search side. A run whose research
found nothing gets a Note in the review. Any data source that came back
empty or errored (no credits, plan refusal, host blocked by the environment's
network policy) also becomes a Note, so the sender sees what the proposal
was and was not built on.

## The proposal

The SMI short form, from `prequal_agent_prompt.py`: a title line, "Prepared by
Strategic Marketing Insights", then **Engagement summary** (the one decision it
closes), **What we heard** (signals table), **Why now: the market and the
economy** (the ValueFirst lens: demand and cost drivers, rates and credit,
policy calendar, cycle position, every figure dated), **The problem in front of
<account>** (sourced, evidence-tagged constraints), **Approach** (phases with
gates, no fees), **What we'd need to qualify this**, **Next step** (a 30-minute
scoping call), **Sources**. `finalize` refuses a draft that misses a section,
mentions money, runs past 1,000 words, or cites nothing when the research found
sources -- the same checks as the agent's `write_proposal` tool.

## What the page does

| Step | On the page | In the run |
|---|---|---|
| 00 LinkedIn request | request text (required), post URL, founder (the requester) and their LinkedIn | `request_text` for the composer; `request.founder` (also written as `request.requester`) is who the proposal's next step and the note to the founder address; the review reads the request for pricing asks |
| 01 Precondition | account name / domain / existing CRM id, LinkedIn-source tick (`state.account.source`, `crm.pre_qual`); an account not in the ledger is researched as a prospect | `find_account` against `data/master/contacts.json`; an unknown account still runs, with a Note |
| 02 Optional state | include/skip + settings, as before | opt-outs are recorded in the manifest and the review |
| 03 Disposition | apollo / manual | `manual` mints `crm_<date>_<rand>` with `pending_apollo`; `apollo` gets a HOLD only if `meta/config.account_lists` is empty at run time |
| 04 Run | **Run composition** | writes `runs/<id>` in the page's database, fires the routine; the sequence lamps follow `steps` live |
| 05 Result | review before sending, note to the founder (Copy note), proposal with **Download PDF** and Copy proposal, CRM ids, run history | rendered from `runs/<id>` via `onSnapshot` |
| 06 By hand | the old copy-manifest path | only when the connector is not available in that view |

Per-viewer drafts stay in the browser (`localStorage`). Run records are
shared (`db` capability); Claude reads and updates them with `ArtifactData`
against the intake artifact URL.

## Founder = requester

Small startups are the ICP, so the person who sends the request is the
founder. The intake form's founder field is the requester: the manifest
carries it as `request.founder` and, for older readers, `request.requester`
(`crm/note_to_founder.py founder_of` reads either). Two things are addressed
to them:

- the proposal's **Next step**, by first name (the prompt's `FOUNDER` slot);
- the **note to the founder** (`crm/note_to_founder.py`, tested in
  `tests/test_note_to_founder.py`): a cover note of at most 170 words that
  goes with the proposal. It says plainly when nothing public was found about
  the company and asks for what would sharpen the draft, answers a pricing
  ask with "we scope before we quote", and carries any `--founder-line` the
  composer adds at finalize (a scope limit, what to send us). It never
  mentions money and never carries internal review items.

Neither is ever invented: no founder on the form, no name in either.

## Download PDF

Under **Proposal as drafted**, the Intake page's **Download PDF** button lays
the proposal out on US Letter pages in the browser (jsPDF 2.5.1 from cdnjs,
jsDelivr as fallback; Helvetica): the brand eyebrow, the account as the title,
"Prepared for <founder>, <account>", the date and the proposal id, section
rules, the "What we heard" table with its header repeated across pages, live
source links, muted evidence tags, and page numbers. The page offers the file
through the `downloads` capability, so the viewer confirms the save. The
button is hidden where downloads are unavailable and disabled for voided
runs. The review and the note to the founder are not in the PDF.

## Review before sending

Computed by `crm/review.py` from the manifest, the run state and the CRM
dump; tested criterion by criterion in `tests/test_review.py`. It is for the
sender, never the founder.

**HOLD** — the proposal is drafted and filed, the run ends `needs_review`,
`proposal_status` stays `drafted`, nothing goes out:

1. The request talks about money, rates, budget, retainer, hourly, pricing or
   a quote. No market rates are set; decide what to say before sending.
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

8. No CRM contact matched: a prospect. The full proposal goes on the account
   record's notes instead, and a LinkedIn lead's account gets `source:
   linkedin` and `pre_qual: true` when unset.
9. No matched contact is `proposal_ready` (cold outreach).
10. Account not in the enriched data layer, ledger quality below the floor,
    or every ledger contact older than 90 days.
11. Website fetch failed; web research found no sources; warehouse findings
    are the sentinel.
12. Keys opted out at intake; no founder named on the intake form.

The review is stored in the proposal record (`review`), printed in the
merged CRM note after the note to the founder (`Review before sending:`
block), shown on the page, and written to `data/runs/<id>/review.json`.
Records and runs filed before the rename carry `founder_note` /
`founder_status` / `needs_founder` and `founder.json`; the page, finalize and
`push_proposals_to_crm.py` still read those.

## Files a run leaves behind

```
data/runs/<run_id>/
  manifest.json        exactly what the page sent
  state.json           account, account_contacts, ledger_quality, website_summary, warehouse_findings
  review.json          holds, notes, text, matched_doc_ids (the review before sending)
  prompts.md           the research brief and the page-summary prompt
  data_sources.md      Apollo and Vibe Prospecting findings; coverage.json per-source outcome
  web_research.md      the research memo; web_sources.txt its URLs
  website_summary.txt  (when a page was fetched)
  proposal_prompt.md   the SMI proposal prompt with the research filled in (from `brief`)
  proposal.md          the draft as composed
  run_update.json      first page update (steps after the deterministic legs)
  run_final.json       last page update (status, review, note to the founder, founder, proposal, CRM ids)
data/proposals/<slug>-<date>-<run_id>.json|md   the filed proposal (push_proposals_to_crm.py reads the JSON)
data/artifact/crm/compose_<run_id>/    the ArtifactData batch (gitignored)
```

## Running it by hand

From the repo root, with a CRM dump made by `ArtifactData list` (contacts and
accounts, each with its versions file):

```
python3 scripts/compose_account.py prepare data/runs/<id>/manifest.json --run-id <id> --crm-dump <dump>
# answer data/runs/<id>/prompts.md → web_research.md, web_sources.txt, website_summary.txt
python3 scripts/compose_account.py brief <id> --web-research data/runs/<id>/web_research.md \
    --web-sources data/runs/<id>/web_sources.txt --data-sources data/runs/<id>/data_sources.md \
    --coverage data/runs/<id>/coverage.json [--website-summary data/runs/<id>/website_summary.txt]
# answer data/runs/<id>/proposal_prompt.md → proposal.md
python3 scripts/compose_account.py finalize <id> --proposal data/runs/<id>/proposal.md \
    --website-summary data/runs/<id>/website_summary.txt --crm-dump <dump> [--composer-flag "…"] [--founder-line "…"]
# then ArtifactData batch with data/artifact/crm/compose_<id>/writes.json
```

`prepare` exits 2 on a gate failure (no account name or domain, null
disposition, ambiguous account) or a halt (`on_fetch_error: halt`).
`finalize` exits 2 when the draft misses a section, mentions money, runs past
1,000 words, or cites nothing when the research found sources.

## Monday

The 11:30 UTC routine dumps contacts **and accounts** (with `versions.json`
and `versions_accounts.json`) so `push_proposals_to_crm.py` can re-apply any
proposal a run left unapplied, on a contact or on a prospect's account. It is
idempotent by `proposal_ref`, which every run sets on what it wrote.

## Rules the run keeps (from the account-composition-run skill)

Never write `stage`. Notes are append-only. Never let an empty value
overwrite a populated one (every CRM write is a field merge of what changed,
pinned with `if_version`). Search `accounts` before creating one. Write the
sentinel rather than leaving `warehouse_findings` unset. Never invent a fact
about the company. The run never calls `pull_apollo.py`, `push_apollo.py` or
`merge_master.py`, and never writes to the CRM except through the
`writes.json` it emitted.
