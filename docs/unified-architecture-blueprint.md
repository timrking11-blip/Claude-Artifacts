# Unified Architecture Blueprint (24 Sep 2026)

Imported from the 24-page PDF *SMI Unified Architecture Blueprint*, prepared
for Timothy King on Thursday 24 September 2026: thirteen pinned artifacts
cross-referenced against the CRM Systems Atlas (registry v1.4), with every
artifact read live, the atlas PDF, Apollo credit usage read via the API, and
the project docs. The PDF itself stays out of this public repo (it names
artifact ids); this file carries the architecture. `CLAUDE.md` holds the
working summary and the phase status.

Claims are tagged as the source tags them: **S** supported (primary source
named) · **N** needs stipulation (the owner confirms) · **E** estimate or
judgment, labelled.

## The consolidation in six numbers (today → target)

| Today → target | What |
|---|---|
| 6 → 2 | places one contact record can live (3 after Phase 2) |
| 2 → 0 | joins between records computed at read time instead of stored |
| 3 → 1 | surfaces reporting stack status (they disagree on 5 facts today) |
| 4 → 1 | rulebooks for the same governance rules |
| 6 → 4 | routines in the CRM data path |
| 2 → 1 | Explorium billing paths (one has no credits) |

## 01 · Executive summary: every part works, too many parts do the same job

**What was found**

1. The stack is built several times over. The atlas maps 25 systems, 24 flows
   and 23 entities around a CRM holding 64 contacts and 1 account. Across the
   13 pinned artifacts there are 6 places a contact can live, 3 surfaces
   reporting stack status, 3 intake doors (a fourth planned), and the same
   governance rules written in 4 vocabularies. S
2. One constraint causes most of it. The CRM's database can be written only
   from a Claude session that loads ArtifactData. That pushed the weekly merge
   into a separate git master, bound two routines to one live session, and let
   the retired ledger sync report success for a month while writing nothing. S
3. Two links between records are guesses. Git-master contacts reach CRM
   contacts by email match at push time; contacts reach accounts by domain or
   company-name substring at render time. Neither link is stored. S
4. The status surfaces already disagree. On 24 Sep, GTM Stack Status, the
   Command Center snapshot and the atlas give different answers on five facts,
   including whether the daily site check is running. S
5. Enrichment is limited by credits, not code. Apollo has 9 of 280 lead credits
   and 0 of 160 direct-dial credits left until 11 Oct. Explorium's REST key
   matched 50 of 52 prospects but had no credits to enrich them, while the Vibe
   Prospecting account held 746 credits on 17 Sep. S · N Vibe balance not re-read

**What to do, in order**

1. Stop the drift this week: unpin 2 stale artifacts, rename 1, correct 2
   stale statements, pick one Explorium billing path, fix the clock before
   1 Nov. E ~1–2 h
2. One status surface: the atlas registry becomes the only source of stack
   status; GTM Stack Status becomes a panel in the Command Center.
3. Store the keys: person → organization and CRM ↔ git-master ids are written,
   never inferred.
4. One Enrichment Broker: free matching first, a credit ledger with floors,
   Apollo for identity, email and sequences, Vibe for firmographics and
   trigger events.
5. Capture activity automatically: Apollo sequence events and Gmail sent mail
   become activity rows, so first touches, replies and calls count themselves.
6. Thread the Service Taxonomy through every record, then turn client intake
   and closed-won into records, and fold Operations Workbench, the SWAT
   cockpit and P3/P4 into one Engagements module.

**The sequencing rule.** GTM Stack Status, 24 Sep: "The build is ahead of the
plan; the outreach is 8 days behind a 60-day clock." So Phases 0–1 are
housekeeping sized not to compete with Gate 0 (Wed 30 Sep). Phase 2 is sized
to pay back before the 15 Nov kill check. Phases 3–5 start only if the kill
thresholds have not fired. If they fire, this architecture should shrink, not
grow.

## 02 · The 13 pinned artifacts, as they actually are

Three were pinned under names that differ from what the page says it is.

| # | Pinned as | What it is (read live, 24 Sep) | Where its data lives | Atlas node | Disposition |
|---|---|---|---|---|---|
| 1 | CRM System | Page titled Leads Pipeline: contact board and table, account cards, proposal fields, LinkedIn-reply logging. Sync never touches stage, notes, next step, value or activity. | ArtifactData: contacts/, accounts/, meta/sync, meta/config | CRM System · live · canonical | KEEP Pipeline module; stored keys, archetype codes |
| 2 | GTM Stack Status | Hand-written status report for 24 Sep: two data planes, pace meters, 5 routines, 5 blockers. Figures fixed in the HTML. | None — static | not a node | SUNSET into a Command Center panel |
| 3 | CRM Enriched Data Layer | Page titled Master Contact Ledger: per-field provenance, source filters, held-conflict and ambiguous-match queue. | ArtifactData: contacts/, meta/sync | Master Contact Ledger · retired | UNPIN now; harvest its provenance UI |
| 4 | GTM Command Center | Weekly scorecard vs 60-day targets, ranked to-dos, Gate 0 countdown, kill thresholds, six-lane board of every artifact. | ArtifactData: dashboard/main, dashboard/lanes, layout/main, todos/state | GTM Command Center · live | KEEP Command module; lanes from registry |
| 5 | SMI Engagement Intake | Client-facing pre-engagement form: 13 core and 9 optional questions. | Browser storage; sends by mailto: | not a node | FIX submit to a record (Phase 3) |
| 6 | Operations Workbench | The 26 Aug build: multi-engagement time, expenses, credits, workstreams with hand-offs, approvals; sample data. The Command Center calls the 9 Sep build current. | Published file data/state.json | not a node | REPIN 9 Sep build; fold into Engagements |
| 7 | Engagement Operating System | Governing standard v1.1: 7 stages, one human acceptance gate, invariants G1–G6, roles EL/ER/AA, evidence tags. | None — document | not a node | PROMOTE spec for the governance contract |
| 8 | SMI Go-to-Market Control | GTM plan v1.0: Gate 0 checklist, four segments, first-touch copy, 42-prompt AI-visibility bank, targets, kill thresholds, open items. | Browser storage (checkboxes) | not a node | KEEP Library; Gate 0 ticks move out |
| 9 | SMI Service Taxonomy | Six service lines (MKT · VAL · GTM · CAP · GOV · SYS), nine archetypes, deliverable objects; the SWAT controlled vocabulary. | None — document | not a node | PROMOTE shared reference codes |
| 10 | SWAT Engine | Build cockpit (3 Sep): phases P0–P8 with gates, AI spec, a placeholder taxonomy of 5 types, 3 open items. | Browser storage | SWAT Engine · draft | MERGE into Command build lane |
| 11 | P4 Contextualization Spec | Synthesis phase: hashed context bundle, validator plus database trigger, four guarantees incl. threshold blinding. | None — spec (engine is SQL) | not a node | PROMOTE its gates into the shared library |
| 12 | P3 Scan Runbook | Collector runbook ST1–ST8 feeding decision criteria DC1–DC6 for the siting work. | None — runbook | not a node | KEEP template for Expansion Siting |
| 13 | Linkedin RFP Request and Proposal Generation with Agentic AI | Page titled Account Composition Intake v2: paste a request, press Run, watch the composition routine; review, founder note, PDF proposal. | ArtifactData: runs/; fires the Composition run routine | Account Composition Intake · live | KEEP Research module; rename |

Also referenced but not pinned: CRM Systems Atlas, Account Research
Composition (17 Sep; Intake v2 now calls itself "the only way proposals are
made"), Strategic Market Insights Launch Check, Operations Workbench 9 Sep
build. The Command Center links an "Operations Workbench Design System" that
does not appear in the artifact list. N

## 03 · Cross-reference

### The overlap matrix, read the short way

- The Command Center and GTM Stack Status duplicate each other on 6 of 13
  jobs; neither owns any of them. The SWAT cockpit restates 6 jobs it was
  meant to own later.
- Governance rules have one owner and five restatements. Client intake has one
  owner and four other places that define or collect it. The offer catalogue
  has one owner and three other lists, one of them in conflict: the CRM's
  product presets are still ad products from a previous role, while the
  Taxonomy defines nine archetypes. S
- Consolidated owners per job: contact and account records → Pipeline
  (canonical store); field provenance → Pipeline "Sources" tab; proposal
  drafting → Research module; proposal status → PROPOSAL record; client intake
  → INTAKE_SUBMISSION → profile; delivery ops → Engagements module; evidence
  → ASSERTION (one model); governance rules → governance contract (library);
  stack status → registry → Command panel; targets and kill thresholds → GTM
  Control (plan) · Command (live); Gate 0 → Launch Check (one record); offer
  catalogue → ARCHETYPE reference table; build tracking → Command build lane
  (db-backed).

### Redundancy register

| # | Finding | Evidence | Consequence | Fix |
|---|---|---|---|---|
| R1 | Six places a contact can live | Apollo, the git master, the CRM, the retired ledger (still pinned), BigQuery crm.contacts, Carly's empty table. S Atlas L0 + L3 | Every store needs its own sync; four counts (82 · 67 · 64 · 62) circulate | Phase 2: three stores with stored keys; Phase 5: two |
| R2 | Two links are guesses | Master ↔ CRM matched by email at the Monday push, no stored key; accounts ↔ contacts matched at render time by domain, then company-name substring, no stored FK. S | "Acme" attaches to "Acme Mechanical" and "Acme Roofing"; a changed email breaks enrichment silently | Phase 2 writes org_id and master_id onto every contact |
| R3 | The canonical store needs a live session | A routine that writes to the CRM must run in the session that can load ArtifactData; push and composition are bound to one session. S | A single point of failure, and the reason the git master exists | Phase 2 heartbeat; Phase 5 a store CI can write |
| R4 | Three status surfaces disagree on five facts | Git-master count (82 vs — vs 67), daily site check (paused vs paused vs live), CRM ledger sync (retired vs live vs retired), ledger page (retired vs live vs retired), accounts (0 vs 0 vs 1), enrichment push (not listed vs not listed vs live). S | Static copies of live facts drift within hours | Phase 1: the registry is the only store of stack facts |
| R5 | Three intake doors and a fourth planned; none produces a client profile | SMI Engagement Intake ends in a mailto to a personal inbox; Account Composition Intake lands in runs/ → CRM; SWAT Intake & Context is planned; Operations Workbench takes "new engagement" by hand. S | Intake answers that arrive as email never become a record | Phase 3: the form writes an INTAKE_SUBMISSION |
| R6 | One rulebook in four dialects | EOS G1–G6, the SWAT cockpit AI spec, the P3/P4 specs and the atlas guardrails state the same eight rules. S | A rule change means editing up to four places; drift here is how a draft becomes final by accident | Contract C1–C8 (below) |
| R7 | Two Explorium billing paths, one empty | REST pull matched 50 of 52 and wrote no fields (no credits); Vibe Prospecting MCP spent 129 credits on 17 Sep, 746 left. S | The weekly job runs and adds nothing while a funded path sits outside the schedule | Phase 0 decision D1 · Phase 2 broker |
| R8 | Offer catalogue not threaded | CRM product presets are old ad products; SWAT cockpit taxonomy is a 5-type placeholder; the Taxonomy defines 9 archetypes. S | Nothing can report by archetype | Phase 1 |
| R9 | Progress trapped in one browser | SWAT cockpit gates, GTM Control Gate 0 ticks and intake answers live in browser storage. S | Invisible to the refresh agent, the atlas, and the owner on another device | Phase 1 (gates) · Phase 3 (intake) |
| R10 | Stale pins and names | Pinned Workbench is the 26 Aug build; "Linkedin RFP…" is Account Composition Intake; "CRM Enriched Data Layer" is the retired ledger; "SWAT Engine" means both a single-tenant cockpit and a 27-table multi-tenant engine. S | The wrong page gets edited | Phase 0 |
| R11 | A proposal has no single record | data/proposals, a merged pre-qual note, proposal_* contact fields, Intake runs, standalone pages. S | "Proposals issued", a kill-threshold input, needs a human to answer it | Phase 3 |
| R12 | The clock moves on Sun 1 Nov | Cowork crons were UTC (0 11, 30 11, 0 12 on Mondays); each run would land an hour earlier in ET and the no-compose window become 05:45–07:15 ET. S | The collision window in the atlas and the Intake contingencies becomes wrong | Phase 0: CRON_TZ |
| R13 | Infrastructure ahead of volume | BigQuery plan unapplied since 17 Sep; Vertex smoke test never run; IAM binding unverified — three of five Stack Status blockers — for 64 contacts and 1 account. S · E | Attention goes to a warehouse with nothing to warehouse | Phase 0: mark "parked" |

### What is already right and must be kept

Version-pinned writes that fail closed; empty never overwrites populated (it
saved 18 mobile numbers on the 17 Sep import); field ownership that stops the
sync touching stage, notes and value; void proposals kept, never deleted; the
intake-domain guardrail (two lookalike-domain proposals were voided, not
deleted); and P4's threshold blinding. The architecture is built around them.

## 04 · Future state

### One model, five routines, one console

Keeps the names in use: the SWAT Engine becomes the console; the CRM System
becomes its Pipeline module.

- **Reference vocabulary.** Service Taxonomy (6 lines, 9 archetypes,
  deliverable objects) and segments A–D, used as codes on every record, owned
  by the Library.
- **Sources.** Apollo.io (identity, lists, sequences, email events, visitors);
  Gmail and Calendar (sent mail, meetings booked — new path); Vibe Prospecting
  (firmographics, tech, business events, sizing); the LinkedIn request pasted
  into Research; web and public data (site, Census, CSLB, Bright Data
  collectors); the client intake form (13 core, 9 optional; public,
  pre-engagement — new path).
- **Routines (five).**
  1. *Monday Data Sync* (merged): Apollo pull and upload → Enrichment Broker
     (free match → budget → enrich) → activity capture → validate with pinned
     writes → heartbeat (rows written). One session-bound routine that fails
     closed.
  2. *Composition run*: fired from Research (fire_trigger); brief → draft →
     finalize (guardrails).
  3. *Collectors + synthesis*: P3 collectors → assertions (raw); P4 bundle →
     validate → write.
  4. *Intake handler* (new): submission → org · person · opportunity.
  5. *Ops refresh* (weekly, merged): registry → scorecard → to-dos.
- **Stores, one logical model.** Canonical store = the CRM db (GTM, research)
  plus the SWAT SQL model (engagements), sharing keys until Phase 5 puts them
  in one store. Git keeps the evidence ledger (runs, proposals, bundles, log).
  The atlas keeps the registry (systems, flows, status). BigQuery and Vertex
  are parked and rejoin only at Phase 5 as an analytics mirror.
- **Console modules.** Pipeline (CRM System) · Research (Composition Intake) ·
  Engagements (Workbench + cockpit) · Command (Command Center + atlas) ·
  Library, read-only (EOS · GTM plan · Taxonomy). Public door: the client
  intake form.
- **Edges removed:** git master → CRM by email match (becomes a stored key);
  the separate 10-day atlas task; GTM Stack Status; intake → personal inbox;
  REST enrichment with no credits. **Edges added:** Gmail/Calendar → activity;
  intake form → record; registry → stack-health panel; broker → credit
  ledger; won → engagement. **Kept as-is:** Apollo ⇄ CRM by stored Apollo id;
  Composition run via fire_trigger; P3 → P4 with bundle hash; GitHub Actions
  weekly merge until Phase 5.

### ER diagram A: GTM and research domain

New record types are marked *new*; reference lists come from the Library.

- **ORGANIZATION** (← CRM accounts + Apollo): org_id PK; domain UK;
  apollo_account_id, explorium_business_id; org_type prospect | referrer;
  segment_code FK; stage cold → customer.
- **PERSON** (← CRM contacts + git master): person_id PK; org_id FK (stored
  key); email, linkedin_url, apollo_contact_id, explorium_prospect_id UK;
  title, flags[].
- **OPPORTUNITY** *new* (← stage/value fields on the contact): opp_id PK;
  org_id, primary_person_id, archetype_code, signal_id (trigger) FK; stage
  new → won | lost; value, next_step, date.
- **ACTIVITY** (← contacts.activity[]): activity_id PK; person_id, opp_id FK;
  type email | call | meeting; channel_ref apollo | gmail; ts, direction.
- **SIGNAL** *new* (Vibe events, Apollo visitors): signal_id PK; org_id FK;
  provider vibe | apollo; type funding | site | exec; observed_at, hint.
- **LIST_MEMBERSHIP** (← apollo_lists[], meta/config): list_id (Apollo label),
  member_ref person | org; status on | removed.
- **FIELD_PROVENANCE** *new* (← git-master provenance{}): entity_ref, field,
  value, source apollo | vibe | manual, job_id, observed_at.
- **ENRICHMENT_JOB** *new* (credit ledger): job_id PK; provider, operation,
  est_credits, spent; run_id, approved_by FK.
- **PROPOSAL** *new* (← data/proposals + proposal_*): proposal_id prq_… PK;
  opp_id, run_id, archetype_code FK; status drafted → sent; amount, sent,
  expires.
- **COMPOSITION_RUN** (← Intake runs/ + data/runs): run_id PK; org_id, opp_id,
  requester_person_id FK; allow_credit_spend; status done | needs_founder.
- **SEGMENT** (reference, ← GTM Control ladder A–D): code, rank,
  qualify_in/out. **ARCHETYPE** (reference, ← Service Taxonomy): code,
  service_lines[].

The two changes that matter most: PERSON carries a stored org_id (no more
render-time name matching) and OPPORTUNITY is its own record, so stage, value
and next step stop living on a contact and a contact can sit in two deals.
Every enriched field writes a FIELD_PROVENANCE row under an ENRICHMENT_JOB
that recorded its cost. Identity keys, in order (unchanged): email → LinkedIn
URL → name + domain; Apollo and Explorium ids are keys; a record matching two
masters is logged as ambiguous, never fused. Field owners (unchanged):
Apollo-owned fields are overwritten by sync; CRM-owned fields are never touched
by sync, import or composition, and now live on OPPORTUNITY and ACTIVITY.

### ER diagram B: engagement delivery domain

- **INTAKE_SUBMISSION** *new* (today a mailto email): submission_id PK;
  person_id, org_id FK; answers 13 core + 9 optional; submitted_at, channel.
- **CLIENT_PROFILE** (← SWAT Intake & Context spine): engagement_id PK (1:1);
  submission_id FK; objectives, constraints, stakeholders, rights.
- **ENGAGEMENT** (← Workbench engagements[] + SWAT): engagement_id PK; opp_id
  (UK, the won deal), org_id, archetype_code FK; decision, decision_date;
  eos_stage 1–7; kill_threshold (G6).
- **WORKSTREAM** (← Workbench projects): workstream_id PK; engagement_id FK;
  budget_hours, tasks[].
- **LEDGER_ENTRY** (← Workbench time + expense + credit): entry_id PK;
  workstream_id, person FK; kind time | expense | credit; qty; pending →
  approved.
- **DECISION_CRITERION** (← SWAT decision_criterion): dc_id DC1… PK;
  engagement_id FK; threshold, weight; signed_off_at (pre-data). No path into
  a synthesis bundle: thresholds stay hidden from the model.
- **SYNTHESIS_ENTRY** (← P4 swot_entry + blueprint): entry_id PK;
  engagement_id FK; kind swot | blueprint | brief; bundle_hash sha256.
  **SYNTHESIS_EVIDENCE** (← P4 swot_evidence): entry_id, assertion_id FK.
- **ASSERTION** (← SWAT assertion + run findings): assertion_id PK; scope
  run_id | engagement; text, source_ref; authorship ai | human; status raw →
  substantiated; tag S | U | N. **ASSERTION_REVIEW**: review_id PK;
  assertion_id FK; reviewer, decision, ts.
- **DECISION_LOG** *new* (EOS G5): log_id PK; engagement_id FK; artifact;
  draft → accepted; accepted_by, ts, changed.

One won OPPORTUNITY becomes at most one ENGAGEMENT; the client's intake answers
become its CLIENT_PROFILE without retyping. Workbench time, expenses and
credits share one approval pattern, so they become one LEDGER_ENTRY. ASSERTION
is shared: a composition run and a P3 collector write the same shape and pass
the same review.

### Entity dictionary: one owner, one writer path

| Entity | Home (now → Phase 5) | Written by | Fed from | Replaces today |
|---|---|---|---|---|
| ORGANIZATION | CRM db → SQL | Monday Data Sync · Composition run · Intake handler | Apollo account · Vibe business | accounts/, git-master company fields |
| PERSON | CRM db → SQL | Monday Data Sync · Intake handler | Apollo contact · Vibe prospect · LinkedIn | contacts/, git-master contact, ledger contact, BigQuery copy, Carly table |
| OPPORTUNITY | CRM db (new) → SQL | Pipeline module (the owner) · Intake handler | human · intake | stage / value / next step / proposal_* on the contact |
| ACTIVITY | CRM db → SQL | Activity capture · Pipeline module | Apollo sequences · Gmail · Calendar · LinkedIn paste | contacts.activity[] |
| SIGNAL | CRM db (new) → SQL | Enrichment Broker | Vibe business events · Apollo website visitors | — (new) |
| LIST_MEMBERSHIP | CRM db → SQL | Monday Data Sync | Apollo labels | apollo_lists[], meta/config.lists |
| FIELD_PROVENANCE | CRM db → SQL | Enrichment Broker · manual edit | every source | git-master provenance{}, the retired ledger's provenance view |
| ENRICHMENT_JOB | CRM meta/credits → SQL | Enrichment Broker · Composition run | Apollo usage stats · Vibe estimate-cost | — (new credit ledger) |
| COMPOSITION_RUN | Intake db + git → SQL + git | Research module · Composition run | run manifest | runs/ page db and data/runs/ (git keeps the evidence copy) |
| PROPOSAL | CRM db (new) → SQL | Composition run · the owner | — | data/proposals, merged pre-qual note, contact proposal_*, standalone proposal pages |
| INTAKE_SUBMISSION | CRM db (new) → SQL | Intake handler | public intake form | mailto email |
| ENGAGEMENT · CLIENT_PROFILE | Workbench file + SWAT SQL → SQL | Won → Engagement handoff | opportunity · proposal · intake | Workbench engagements[]; SWAT profile spine |
| WORKSTREAM · LEDGER_ENTRY | Workbench file → SQL | Engagements module | people on the engagement | Workbench projects, time, expenses, credits |
| ASSERTION · REVIEW | SWAT SQL | Composition run · P3 collectors · P4 · reviewer | web · providers · public data | SWAT assertion tables; run sources and coverage files |
| DECISION_CRITERION | SWAT SQL | the owner, signed off before collection | — | DC1–DC6 (unchanged) |
| SYNTHESIS_ENTRY · EVIDENCE | SWAT SQL | P4 synthesis only | hashed bundle | swot_entry, swot_evidence (unchanged) |
| DECISION_LOG | SWAT SQL (new) | acceptance at EOS Stage 5 | — | EOS "decision log" (not a record today) |
| ARCHETYPE · SEGMENT | reference list in the Library | the owner | Service Taxonomy · GTM Control | product presets; SWAT placeholder taxonomy |

Where the SWAT Engine's SQL model is hosted is not stated in any pinned
artifact. N The plan assumes it is reachable from the machine that runs P3/P4
today and does not move until Phase 5.

### The end-to-end workflow, as records

Signal → Lead → Enriched → Touched → Composed → Proposal → Won → Engagement.
Signal and Engagement have no record today. The two diamonds, the accept
(G1) and the EOS Stage 5 gate, are the only places a draft can become final.
Proof loop: hour actuals by archetype → base rates → fee floor on the next
proposal.

| Transition | Who moves it | What gets written | Rule that guards it |
|---|---|---|---|
| Signal → Lead | Enrichment Broker (Monday) | SIGNAL; ORGANIZATION if new (Apollo search before create) | C2 scope · Apollo does not dedupe accounts |
| Lead → Enriched | Enrichment Broker | fields + FIELD_PROVENANCE + ENRICHMENT_JOB | C7 empty never overwrites · credit floor |
| Enriched → Touched | The owner sends; Activity capture records | ACTIVITY (channel_ref = Apollo or Gmail message id) | No manual logging required |
| Touched → Composed | The owner presses Run in Research | COMPOSITION_RUN, ASSERTIONs (raw), draft PROPOSAL | C2 intake-domain guardrail · no compose 06:45–08:15 ET Mon |
| Composed → Proposal | The owner accepts (separate sitting) | PROPOSAL status accepted → sent; DECISION_LOG row | C1 · EOS single-operator control: never generate and accept in one session |
| Proposal → Won | The owner marks the opportunity | OPPORTUNITY stage won | Stage is human-owned; sync never writes it |
| Won → Engagement | Handoff routine | ENGAGEMENT + CLIENT_PROFILE + archetype workstreams | C5 kill threshold written at EOS Stage 2, before evidence |

## 05 · Connectors

### Apollo.io and Vibe Prospecting: give each one job

Apollo answers *who* and *was it sent*. Vibe answers *what is this company*
and *what just changed*. Neither should do the other's job.

Credit state on 24 Sep 2026 (cycle 11 Sep – 11 Oct): Apollo lead (email
reveal) 271 of 280 used, 9 left; direct dial 160 of 160, 0 left; AI credits
0 of 5,000; conversation credits 0 of 150; website-visitor credits 0 of 20.
Vibe Prospecting (MCP) 129 used, 746 left as of 17 Sep, not re-read N;
packages are one-time, valid 365 days. Explorium REST key (CI): 0 credits;
matched 50 of 52, wrote no fields.

Is 280 reveals a month enough? The 60-day plan calls for 120 first touches by
15 Nov, about 60 email reveals per cycle across the two remaining cycles, well
inside 280 if reveals are spent only on contacts entering the week's send
block. The binding constraint is this cycle: 9 left until 11 Oct. E

**Apollo.io: identity, lists, outreach**

1. Reveal on send, not on import. Spend lead credits only when a contact
   enters the week's send block or a composition run allows spend. Keep a
   floor of ~10 per cycle for replies and referrals. E
2. Send through sequences, or ingest what you send. Pull sequence and email
   events weekly into ACTIVITY.
3. Turn on the website-visitor tracker the day Gate 0 publishes the site:
   visiting domains become SIGNAL rows timed after a first touch.
4. Keep Apollo as email owner in the trust order; stop expecting phones from
   it (0 direct dials).
5. Keep search-before-create for accounts; Apollo does not dedupe them.
6. Leave AI and conversation credits alone until activity capture exists.

**Vibe Prospecting (Explorium): firmographics, events, sizing**

- V1 · One billing path (decision D1). Recommended: backfill the 50
  already-matched prospects once from the Vibe balance, with a cost estimate
  first; keep the CI job for free matching only (it still writes identity
  keys); buy REST credits only when weekly new records make a session-free
  path worth paying for.
- V2 · Size before you spend: entity statistics are free and give the
  denominator behind the 120-account target.
- V3 · Always sample and estimate first, and log each export's dataset id to
  ENRICHMENT_JOB.
- V4 · Events are the product: business events become SIGNAL rows mapped to
  archetypes.
- V5 · Explorium owns firmographics in the merge trust order; the broker
  enforces it at write time.

### The Enrichment Broker (T1)

Replaces the REST enrichment step, ad-hoc Vibe exports and the separate
enrichment push. Runs as step 2 of the Monday Data Sync, and on demand inside
a composition run when the intake form allows spend.

1. Identity match — free: Apollo people search, org lookup, Vibe match; writes
   vendor ids.
2. Budget check — credit ledger per cycle, Vibe estimate-cost, floor per
   provider. Over floor → queue to next cycle, field = "pending_budget"
   (sentinel).
3. Enrich by field owner — email → Apollo; firmographics, tech → Vibe; title,
   seniority → LinkedIn.
4. Merge by trust order — empty never overwrites; manual outranks feeds; >7
   days fresher wins at equal trust. Disagreement → conflict held, incumbent
   stays, review queue in the CRM drawer.
5. Pinned write — if_version from the dump, plus a provenance row and an
   ENRICHMENT_JOB row.

Steps 1, 4 and 5 are today's merge_master.py, validate_sync and pinned-write
rules moved into one place. Step 2 is new: nothing is bought without a ledger
entry, and running out queues work instead of failing silently.

**Trigger events → segment → archetype → opening line**

| Signal | Source | Segment (GTM Control) | Archetype (Taxonomy) | First touch already written |
|---|---|---|---|---|
| New location, expansion, new service area | Vibe events | B · multi-location operators | Expansion Siting Study | B1 "before the lease" |
| Ownership change or acquisition | Vibe events | C · dealer network | Expansion Siting · Diligence Red-Flag Review | C1 "what changed on my end" |
| Leadership change (new CEO / President) | Vibe events · Apollo | C · dealer network | GTM Blueprint · Fractional CSO | C1, then C2 at +10 days |
| Funding round, grant or award | Vibe events | A · regulated-software founders | Funding Route Lock · Viability Test | A1 "the channel question" |
| Hiring surge in sales or partnerships | Vibe workforce trends | A or B | GTM Blueprint | A1 / B1 variant |
| Site visit after a first touch | Apollo visitors | any | — (timing, not fit) | Move the follow-up forward |

Exact event-type names come from the Vibe tool's filter list; confirm them
before hard-coding the mapping. N Segment D (referral sources) is deliberately
absent: referrers are recruited, not triggered.

### Everything else

| Connector | State today | Recommendation | Call |
|---|---|---|---|
| Gmail · Google Calendar | Connected; used for drafts | Activity capture: sent messages to CRM addresses become ACTIVITY; calendar events with CRM attendees become meetings. Point it at the domain mailbox once GTM Control open item 1 is closed. | EXPAND |
| Claude Code Remote | Live; the Intake's trigger path | Keep: it is how the Research module fires the composition run. | KEEP |
| Google Drive | Holds a stale mirror of the repo | Stop mirroring or label the folder "not a source". | FIX |
| Carly | Connected; 0 contacts, 0 workflows | Do not use its contacts table (a seventh store). Either use a booking page from it for Gate 0 item 0.7, or disconnect. Pick one booking tool. | DECIDE |
| ZoomInfo | Installed; needs reconnect | Reconnect only with a licence of your own; a third enrichment vendor adds merge conflicts without new coverage at this volume. | REMOVE |
| Bright Data (plugin) | Available; used by P3 ST4–6 | Keep for engagement collectors. Not a CRM enrichment source. | KEEP |
| Clay | Not installed | Not now: the broker does the same for two providers without a third bill. | NOT NOW |
| Lusha | Not installed | Only if phone coverage becomes the bottleneck for Segment C calls. Trial on 20 contacts or fewer; TCPA rules apply. | IF NEEDED |
| HubSpot | Not installed | The buy-versus-build alternative to the whole Pipeline module. Revisit at the Phase 5 decision. | PHASE 5 |

Buy-versus-build: build (this plan) keeps field ownership, pinned writes,
guardrails and the evidence model, costs maintenance and depends on a live
session until Phase 5; buy (a hosted CRM) gives native email logging,
sequences and reliability, loses the custom rules, and the SWAT Engine would
still need its own store. Lean: build, while one operator runs under ~200
active contacts and the SWAT Engine is itself a proof asset for the SYS
service line. E

Connector rules that go into the contract: every paid call writes an
ENRICHMENT_JOB row before it runs; one owner per field, a second vendor can
fill a blank but never overwrite; no connector gets its own contact table; a
connector that has carried no data for 30 days is marked "unused" in the
registry and reviewed.

## 06 · Growth and tools

Growth items (need records that do not exist today): G1 trigger-led account
ranking (SIGNAL × segment rank × archetype fit); G2 post-touch intent (Apollo
visitor tracking after Gate 0); G3 referral partners as records (org_type =
referrer plus a reciprocal-referral log); G4 proof loop into pricing (hour
actuals by archetype → base rates → fee floor); G5 AI visibility as data (log
each monthly run of the 42-prompt bank); G6 the architecture as a case study
(de-identified, for the Decision Systems & Automation line).

| # | Tool | What it does | Removes | Built from | Phase | Effort E |
|---|---|---|---|---|---|---|
| T1 | Enrichment Broker | Free match → budget → enrich by field owner → trust-order merge → pinned write + provenance | REST enrichment step; ad-hoc Vibe exports; separate push task | merge_master.py, validate_sync, composition credit gate | 2 | 4–6 h |
| T2 | Activity Capture | Apollo sequence and email events, Gmail sent, Calendar meetings → ACTIVITY | Manual send logging; hand-entered scorecard inputs | CRM "Log reply" pattern; Apollo and Gmail connectors | 2 | 2–4 h |
| T3 | Registry-driven Command | Weekly Ops refresh: re-inventory → registry → scorecard → stack-health panel | GTM Stack Status; hand-kept lane cards; the 10-day atlas task | Atlas registry contract; Command Center refresh | 1 | 2–3 h |
| T4 | Intake-to-Record | Public form writes a submission; links org, person, opportunity; email becomes confirmation | mailto output; retyping into CRM and SWAT | SMI Engagement Intake fields | 3 | 3–5 h |
| T5 | Governance library | Clauses C1–C8 in code | Four restatements of one rulebook | crm/guardrails.py; P4 validator and trigger | 4 | 6–10 h |
| T6 | Won → Engagement handoff | Won creates ENGAGEMENT, CLIENT_PROFILE and archetype workstreams | Manual lane 05 "Closed-Won Intake" | Proposal + intake + P3 runbook | 3–4 | 3–5 h |

## 07 · Build and sunset plan

Dates that constrain the plan: Gate 0 (Wed 30 Sep) and the 60-day kill check
(15 Nov) from GTM Control; the Apollo credit reset (11 Oct); clocks fall back
(Sun 1 Nov). Phases 0–2 total roughly 13–20 hours over seven weeks,
deliberately less than one outreach day a week. E

| Phase | Window | Outcome | Starts only if | Effort E |
|---|---|---|---|---|
| 0 · Stop the drift | Thu 24 – Wed 30 Sep | Pins, names and stale statements match the atlas; one Explorium path chosen; clock fixed | — | 1–2 h |
| 1 · One surface, one vocabulary | Thu 1 – Fri 16 Oct | Stack status lives only in the registry; archetype codes on every record; gates out of browser storage | Phase 0 gate passed | 4–6 h |
| 2 · Keys, broker, activity | Mon 19 Oct – Sun 15 Nov | Stored keys; Enrichment Broker with credit ledger; activity captured automatically; signals on accounts | Phase 1 gate passed | 8–12 h |
| 3 · Proposals + intake as records | Mon 16 Nov – Fri 18 Dec | PROPOSAL and OPPORTUNITY records; intake form writes records; won → engagement handoff | 15 Nov kill thresholds did not fire | 10–14 h |
| 4 · Engagements module | Jan – Feb 2027 | Workbench, SWAT cockpit and P3/P4 under one ENGAGEMENT; governance library in code | At least one signed or live engagement | 15–25 h |
| 5 · One canonical store | Trigger-gated | One SQL store that CI and routines can write; pages become projections; git master retired as a store | A second person joins, or the session binding misses a Monday twice, or volume outgrows the page db | TBD |

Standing rule from the atlas applies to every step: whatever is wired or
retired is written to the registry in the same session, on primary evidence.

### Phase 0 · Stop the drift (Thu 24 – Wed 30 Sep)

1. Unpin "CRM Enriched Data Layer". The atlas already records it retired;
   keep the page, its history is evidence.
2. Pin the 9 Sep Operations Workbench and unpin the 26 Aug build, after
   confirming the 9 Sep build has the multi-engagement model.
3. Retitle "Linkedin RFP Request and Proposal Generation with Agentic AI" to
   "Account Composition Intake": its heading, the Command Center card and the
   atlas node already use that name.
4. Correct GTM Control open item 7 ("the prospect workbook is the system of
   record") to "the CRM System is the system of record until the SWAT Engine
   ships".
5. Choose the Explorium billing path (decision D1) and write it into the
   registry.
6. Before Sun 1 Nov: add CRON_TZ=America/New_York to the Apollo sync,
   enrichment push and Command Center refresh tasks, or rewrite the collision
   window as 05:45–07:15 ET wherever it appears.
7. Mark BigQuery, Vertex and HCP Terraform "parked" in the registry; stop
   carrying them as open blockers (GTM Stack Status lists three).
8. Resolve the orphan link: find or remove the "Operations Workbench Design
   System" card.

**Gate.** At the next Monday refresh after these steps: no Command Center card
contradicts the atlas registry, and every pinned artifact's title matches its
heading.

### Phase 1 · One surface, one vocabulary (Thu 1 – Fri 16 Oct)

1. Stack-health panel (T3): the Command Center refresh reads atlas
   registry/main and renders systems, status and last run; lane cards read
   status from the registry instead of carrying their own.
2. Retire GTM Stack Status: replace its body with a one-line pointer to the
   Command Center (keep the URL), then unpin.
3. One Ops refresh: fold the 10-day atlas refresh into the weekly Command
   Center refresh (re-inventory → registry → scorecard); disable the 10-day
   task after two clean weekly runs.
4. Load the reference lists: Service Taxonomy codes (6 lines, 9 archetypes)
   and segments A–D into CRM meta/config; replace the old product presets with
   archetypes; add optional archetype_code and segment_code.
5. Gate 0 lives in one place: Launch Check holds the 9 items; GTM Control links
   to it; the Command Center gate card reads it.
6. SWAT cockpit into the Command build lane: re-enter P0–P8 gate states in
   the Command Center database; replace the placeholder taxonomy with the 9
   archetypes.
7. Publish contract C1–C8 as a Library page; EOS, P4 and the Intake
   contingencies link to it.

**Gate.** Any stack fact (status, count, last run) is stored in exactly one
place; every open CRM record can take an archetype code from a fixed list.

### Phase 2 · Keys, broker, activity (Mon 19 Oct – Sun 15 Nov)

Records and keys (weeks 1–2): store the master key (the Monday push writes
master_id onto each CRM contact and crm_id onto each master row; email
matching becomes a one-time, logged backfill); store the organization key
(org_id on contacts only on an exact domain match, anything else flagged for
review, never matched by substring); promote accounts (ORGANIZATION records
for the companies behind the 35 qualified contacts, Apollo account search
first); harvest the retired ledger (its per-field provenance and conflict
queue become a "Sources" tab in the CRM contact drawer, then archive the
ledger page).

Monday Data Sync (weeks 2–4): merge Apollo sync and enrichment push into one
ordered routine, bound to the session that owns the repo, with a step zero
that verifies ArtifactData loads and fails loudly if not; Enrichment Broker
(T1) as step 2 with a credit ledger in meta/credits and per-provider floors;
activity capture (T2) as step 3; signals (Vibe business events for qualified
and new accounts become SIGNAL rows, an account with none gets the sentinel
"none found"); heartbeat (each run writes rows-written and versions-pinned;
the Ops refresh turns a routine red after two zero-write weeks).

**Gate · 15 Nov kill check.** First touches, replies and calls booked on the
scorecard are computed from ACTIVITY with no hand entry; zero
person→organization or CRM↔master links computed at read time; the credit
ledger shows spend against floor for both providers; two consecutive clean
Monday runs.

**If the kill thresholds fire on 15 Nov.** Fewer than 6 calls from 80+ sends
means the message is wrong, not the list. Stop at the end of Phase 2: keep the
broker and activity capture (they measure the next attempt), skip Phases 3–5,
and put the saved hours into the three Segment C diagnostics the kill
threshold prescribes.

### Phases 3, 4 and 5 (gated)

- **Phase 3 · Records for deals (16 Nov – 18 Dec)**, if the kill thresholds
  did not fire: decide D5 (stage, value and next step move to OPPORTUNITY);
  PROPOSAL records backfilled from data/proposals, Intake runs, contact
  proposal_* fields and the standalone proposal pages, with composition
  writing a PROPOSAL row, not only a note; Intake-to-Record (T4), after
  confirming the page can accept a signed-out submission N; Won → Engagement
  (T6). Gate: "proposals issued" and "engagements signed" compute from
  records; an intake reaches a profile with zero retyping.
- **Phase 4 · Engagements module (Jan – Feb 2027)**, with at least one signed
  or live engagement: fold Operations Workbench under ENGAGEMENT (workstreams,
  one LEDGER_ENTRY for time, expense and credit; sample data removed);
  governance library (T5) called by the composition run, P3 collectors and P4
  synthesis; one ASSERTION model and one review queue; archetype playbooks
  (the P3 runbook becomes the Expansion Siting template); the proof loop.
  Gate: one engagement runs intake → P4 → accepted blueprint with every id
  traceable to its CRM organization and proposal.
- **Phase 5 · One canonical store (trigger-gated)**, on any trigger (a second
  person joins; the session binding misses a Monday twice; volume outgrows the
  page database): decide D4; migrate canonical tables so GitHub Actions and
  routines write SQL directly and page databases become projections refreshed
  by the sync; retire the git master as a store (git keeps runs, proposals,
  bundles, CHANGELOG and code); unpark BigQuery only as an analytics mirror.
  Gate: one write path per entity; no routine needs a live session to write;
  parity check across projections shows zero difference.

## 08 · Sunset register

Retire on primary evidence only. Harvest first; keep history: a retired page
is evidence, not clutter.

| System | Disposition | Phase | Replaced by | Harvest first | Evidence required before retiring |
|---|---|---|---|---|---|
| CRM Enriched Data Layer (pinned) | UNPIN → ARCHIVE | 0 / 2 | CRM "Sources" tab | Provenance display, conflict and ambiguous-match queue | Atlas v1.4 records it retired ✓; archive after the tab ships |
| Operations Workbench, 26 Aug (pinned) | UNPIN | 0 | 9 Sep build | — | 9 Sep build shows the multi-engagement model |
| GTM Stack Status (pinned) | POINTER | 1 | Command Center stack-health panel | Blocker format; "every figure read live" footer rule | Panel shows the same facts two Mondays running |
| SWAT Engine cockpit (pinned) | MERGE | 1 | Command build lane (database-backed) | P0–P8 gates, AI spec, open items | Gate states re-entered and visible to the refresh |
| GTM Control · Gate 0 checklist | MERGE | 1 | Launch Check | 9 items with designer and licence dependencies | Launch Check lists all 9 items |
| Atlas refresh, 10-day task | MERGE | 1 | Weekly Ops refresh | Registry contract; fail-safe pending file | Two clean weekly registry writes |
| Account Research Composition (17 Sep) | ARCHIVE | 1 | Account Composition Intake v2 | — | Confirm it holds nothing Intake v2 lacks N |
| Apollo sync + enrichment push (two tasks) | MERGE | 2 | Monday Data Sync | Task ids, auto-approve settings, run history | Two clean Monday runs of the merged routine |
| Explorium REST enrichment step | MATCH-ONLY | 0 / 2 | Enrichment Broker via Vibe | Matched prospect ids | Broker writes firmographics for the 50 matched |
| CRM ledger sync task (disabled) | DELETE | 1 | — | Export its run history (the evidence) | Disabled since 24 Sep ✓ |
| Carly · ZoomInfo connectors | REMOVE | 0 | — (Carly booking only, if chosen) | — | No CRM data path (atlas) ✓ · no licence |
| BigQuery · Vertex · HCP Terraform | PARK | 0 | — until Phase 5 | Terraform root, WIF setup, request-logging plan | — (parked, not retired) |
| Drive mirror of the repo | LABEL / STOP | 0 | GitHub | — | Atlas: stale since 17 Sep ✓ |
| Git master contacts.json as a store | RETIRE | 5 | Canonical SQL | Merge engine, provenance, the merge tests | Phase 5 parity check |
| SMI Engagement Intake mailto: output | REPLACE | 3 | INTAKE_SUBMISSION record | All 22 questions and wording | First real submission lands as a record |

After Phase 1 the pinned set drops from 13 to 10: Enriched Data Layer, GTM
Stack Status and the SWAT cockpit come off; the 9 Sep Workbench replaces the
26 Aug build.

## 09 · Decisions and open items

Each decision names a recommendation; none is made for the owner.

| # | Decision | Recommendation | By |
|---|---|---|---|
| D1 | Explorium: fund the REST key (session-free, CI) or enrich from the Vibe MCP balance (funded, session-bound)? | Vibe balance for a one-time backfill of the 50 matched; REST stays match-only until volume justifies credits | P0 |
| D2 | Accept one session-bound Monday routine in exchange for ordered, single-writer syncs? | Yes, with the step-zero check and the heartbeat | P2 |
| D3 | If the 15 Nov kill thresholds fire, stop after Phase 2? | Yes: shrink the build, fix the message | 15 Nov |
| D4 | Phase 5 store: managed SQL, BigQuery, or hosted CRM + SWAT SQL? | Managed SQL with triggers, if the SWAT Engine is heading toward a client-facing SYS offer | P5 |
| D5 | Pipeline by deal (OPPORTUNITY) instead of by contact? | Yes once proposals are records; one contact can sit in two deals | P3 |
| D6 | One booking tool for Gate 0 item 0.7 | Whichever sends invites from the domain mailbox | P0 |

Decided 25 Sep 2026 (recorded in registry v1.5): D1, the Vibe balance funds a
one-time backfill of the 50 matched prospects and the REST step stays
match-only; D6, a Google Calendar booking page on the domain mailbox, so Carly
is disconnected. D1 amended the same day (registry v1.11): no enrichment
backfill; alternatives are explored later, and the REST step stays match-only.
D2 decided 25 Sep 2026 (registry v1.10): yes.

Needs stipulation: (1) the Vibe Prospecting balance today (last known 746 on
17 Sep); (2) where the SWAT Engine's SQL model is hosted, and which artifact
"SWAT Engine" should mean; (3) "Operations Workbench Design System" is linked
from the Command Center but absent from the artifact list; (4) HCP Terraform
apply state and whether the BigQuery logging dataset exists (unverified since
17 Sep); (5) whether a published page can accept a write from a visitor who is
not signed in to claude.ai (decides how T4 is built); (6) the Apollo plan tier
(observed limits 280 lead and 160 direct-dial credits per cycle; the plan name
was not read); (7) Vibe event-type names for the trigger mapping.

What changes in the atlas when this is adopted: the registry gains three node
statuses already in its contract (parked, retired, proposed) for
BigQuery/Vertex/HCP, the Stack Status page and the new routines; the Monday
clock collapses from four runs to three (Actions merge, Monday Data Sync, Ops
refresh); L3 gains the new entities as they ship. The atlas stays the map;
this document is the route.

## The governance contract C1–C8

One library, enforced at every write. Each clause cites its EOS invariant.

| Clause | Rule | Today's dialects |
|---|---|---|
| C1 | Generated records start as draft; state changes only by a recorded acceptance | EOS G1 "draft, not final", Stage 5 "no acceptance, no advance"; SWAT "nothing silently finalizes"; P4 writes authorship='ai', status='raw'; composition review HOLD lines, needs_founder, agents never write stage |
| C2 | A run reads only the scope it was given, recorded in its manifest | EOS G2 input-bounded; P4 bundle holds only listed assertions, "no invention" trigger; the intake-domain guardrail |
| C3 | No claim without a source row or an evidence tag | EOS G4 traceable with tags S/U/N; SWAT "source pointer or auto-flag"; P4 v_ungrounded_swot fails the build; data/runs sources + coverage |
| C4 | One call site per provider | EOS G3 model-agnostic; ADK provider switch anthropic · claude on Vertex · gemini |
| C5 | Criteria are signed off before collection and never enter a synthesis bundle | EOS G6 kill/pivot pre-agreed; P3 "decide the DC1 threshold before ST7 runs", threshold blinding; GTM Control kill thresholds "not renegotiable after" |
| C6 | Missing data is a sentinel value, never a blank or a default | EOS "needs stipulation" tag; P3 "absent from a website is unknown, never false"; atlas "sentinel vs unset", write "not available" |
| C7 | Empty never overwrites; every write is version-pinned; owners are fixed per field | SWAT P6 gate "without wiping accepted human edits"; P4 hash check refuses a stale bundle; atlas empty-value rule, pinned writes (if_version), field ownership |
| C8 | Nothing is deleted; every state change is logged with who and when | EOS G5 auditable, decision log; P4 bundle manifest + sha256; CHANGELOG, meta/sync changelog, void proposals kept |
