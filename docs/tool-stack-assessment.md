# Tool stack assessment (27 Sep 2026)

An assessment of the Unified Architecture Blueprint (24 Sep 2026) three days
after Phases 1 and 2 were started early, with a recommended GTM and
operational tool stack for Strategic Market Insights and a dated plan. Every
figure below was read live on Sat 27 Sep 2026: the CRM System database, the
CRM Systems Atlas registry (v1.12), the Command Center database, the Launch
Check's daily crawl (26 Sep), the routine list, Apollo credit usage and
sequence stats, the connector list, and this repo (143 tests passing).

Published as a page: https://claude.ai/artifact/X1AmTcpR9ZYBZuzeJ74bQP
(pinned 27 Sep 2026; the page and this file carry the same content).

Claims carry the blueprint's tags: **S** supported (primary source read) ·
**N** needs stipulation (the owner confirms) · **E** estimate or judgment.

## 1 · Verdict

The blueprint's diagnosis is right and the build is sound. What is wrong is
the order of attention. The architecture is now two phases ahead of the
business it serves: 64 contacts, one account, zero replies, zero calls, and a
Gate 0 that closes on Wed 30 Sep with its contact page still returning 404.
The single most valuable hour this week is not in the repo. It is a domain
mailbox, a contact page and a booking link.

Three findings change what to do next:

1. **The one metric the 15 Nov kill check depends on is measured three ways
   and none is authoritative.** The Command Center scorecard says 1 first
   touch sent. Apollo says the First Touch Sequence has delivered 25. The
   activity capture on 25 Sep recorded 29 Gmail sends on 26 contacts. This is
   redundancy finding R4 (status surfaces disagree) reappearing on the most
   important number in the plan. S
2. **Outreach is sent from a personal Gmail address.** Apollo's only linked
   mailbox is tim.r.king11@gmail.com (`is_free_domain: true`). The domain
   address shown on the site on 17 Sep is no longer displayed (the 26 Sep
   crawl marks it regressed), and no message has ever been sent from or
   received at it in the connected Gmail account. S
3. **There is no back office.** Nothing in the stack signs a contract, sends
   an invoice, takes a payment or opens an engagement folder. The plan's
   target is one signed engagement by 15 Nov. E

## 2 · The blueprint, assessed

### What it gets right, and must not be re-litigated

- The root-cause finding (the CRM database can be written only from a session
  that loads ArtifactData) is correct, and D2 (one session-bound Monday Data
  Sync with a step-zero check and a heartbeat) is the right answer for one
  operator. Phase 5's trigger ("misses a Monday twice") is the right hedge.
- Field ownership, pinned writes, empty-never-overwrites, the intake-domain
  guardrail, the HOLD-clears-only-after-a-check rule and the runlog hold over
  five records are exactly the controls a one-person shop needs. They are
  built, tested and enforced in code (`crm/guardrails.py`, `crm/runlog.py`,
  `crm/broker.py`).
- Build over buy at under 200 active contacts is the right call, with one
  amendment below (Supabase as the named Phase 5 store).
- The sequencing rule (Phases 0–1 sized not to compete with Gate 0; shrink if
  the kill thresholds fire) is the most important sentence in the document.

### Where it is weak or already off-plan

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| A1 | Phases 1 and 2 started on 25 Sep before the Phase 0 gate (28 Sep), Gate 0 (30 Sep) and the Phase 1 gate (12 Oct). S | CLAUDE.md, registry changelog | The blueprint's own rule ("a phase whose entry condition is unmet does not start") has been broken once already. Not fatal, but the 28 Sep and 12 Oct gate checks now audit work already done rather than gate work not yet started. Hold the line from here. |
| A2 | The scorecard is still hand-fed. S | Scorecard: 1 first touch. Apollo: 25 delivered + 1 on a second sequence. Activity rows: 29 Gmail sends. | Until the refresh computes from ACTIVITY (held to the 1 Oct routine) the 60-day pace, reply rate and kill check are unmeasured. |
| A3 | Enrichment is dead for the next two weeks. S | Apollo lead credits 285 of 285 used, direct dial 160 of 160, cycle ends 11 Oct. Vibe balance "not read"; D1 backfill declined. CRM: industry on 29 of 64 contacts, employees 29, revenue 6. | No firmographics arrive before 11 Oct; the trigger-event mapping (Vibe events → segment → archetype) has no data path at all. |
| A4 | The vocabulary is loaded but unused. S | `archetype_code` and `segment_code` on 0 of 64 contacts; `org_id` on 0 of 64 (the 34 confirmed accounts are held until the 1 Oct routine creates them). | The Phase 1 gate ("every open record can take an archetype code") is met structurally and empty in practice. Nothing can report by archetype yet. |
| A5 | Routine reliability is unproven. S | "Weekly enrichment → CRM push" has never recorded a run (last_run none; the stack panel says "no run recorded"). The eight phase kickoffs are one-shot routines bound to a single session; none has fired yet. | The same pattern that let the retired ledger sync report success while writing nothing. The 28 Sep 07:30 ET run is the first real test. |
| A6 | Connector sprawl contradicts the contract. S | 12 connectors installed but `connect_incomplete` (Supabase, Microsoft 365, Miro, Figma, Brand24, Profound, Windsor.ai, FactSet, S&P, Oxford Economics, Monte Carlo, Hugging Face); Explorium_Connector `needs_reconnect` beside Vibe Prospecting; SlidesGPT `not_connected`. | The blueprint's rule "a connector that has carried no data for 30 days is marked unused and reviewed" has 14 candidates on day one. Two Explorium connectors after D1 chose one billing path. |
| A7 | Sequence sprawl has started. S | A second Apollo sequence ("SaaS CEO GTM Advisory Outreach") was created on 25 Sep by the AI assistant, 5 steps, 1 delivered. The First Touch Sequence has 10 overdue manual tasks. Open tracking is off on both (0 delivered-open-tracked). | Two sequences, four segments and no segment naming. Overdue manual tasks mean the LinkedIn steps are the owner's unlogged labour. |
| A8 | Gate 0 is three days out and open. S | 26 Sep crawl: `/contact` 404; domain email no longer on the page; robots.txt blocks 30 AI crawlers (contradicts the AI-visibility plan); marquee, cart icon, three H1s, Services meta description still open. Fixed since 17 Sep: About is text (2,710 chars), mailto mismatch, sitemap, social links, favicon, share image. | Segments A, B and D do not start. The kill card for this is already on the Command Center. |
| A9 | The back office does not exist. E | No contract or e-sign tool, no invoicing or accounting, no engagement folder template, no fee floor (open GTM item 4). The Operations Workbench (9 Sep) holds sample data. | The first "yes" on a call has nowhere to land. Phase 4 (Jan–Feb 2027) is the first place the blueprint mentions any of it. |
| A10 | The pinned set mixes personal and business. S | Resume Match Desk (a personal tool) is pinned beside the business artifacts; "Design" (24 Sep) and the Personal Budget Modeling Tool sit in the same gallery. | Minor, but the Command Center's lanes and the atlas describe a business system; the pinned list should match. |

## 3 · Recommended tool stack

Principle: three hubs and nothing else with its own contact table. **Google
Workspace** on the domain is the office. **Apollo** is identity and outreach.
**The Claude stack** (the CRM System page, the Command Center, the Intake
page, Claude Code Remote routines and this repo) is the system of record, the
research desk and the automation layer. Every other tool is either an input
to one of the three or removed.

### GTM stack

| Job | Tool | Status today | Decision |
|---|---|---|---|
| Identity, lists, sequences, email events | Apollo.io | Connected; credits exhausted until 11 Oct; sending from personal Gmail | **KEEP.** Link the domain mailbox as the default sender. Turn on open and click tracking. One sequence per segment, named by segment code. Reveal on send only, floor 10. Website-visitor tracker (20 credits, unused) the day Gate 0 closes. |
| Firmographics, technographics, trigger events | Vibe Prospecting (Explorium MCP) | Connected; balance unread; no spend planned | **KEEP as the one enrichment vendor.** Disconnect Explorium_Connector (duplicate path). The REST key stays match-only in CI. Owner reads the Vibe balance in the Vibe UI once and it is written to `meta/credits`; a small per-cycle floor follows. N |
| System of record (contacts, accounts, activity, proposals) | CRM System artifact | Live, 64 contacts, 1 account, 7 runlog lines | **KEEP until Phase 5.** Do not buy HubSpot or Pipedrive now: they would be a seventh contact store and would lose field ownership and pinned writes. Revisit at the first hire or the Phase 5 trigger. |
| Account research and proposals | Account Composition Intake + `compose_account.py` | Live; 5 runs (1 needs_founder, 1 void, 3 superseded) | **KEEP.** It is the only proposal path. Phase 3 makes PROPOSAL a record. |
| Outreach copy and drafts | GTM Control first-touch bank; First-Touch Emails page | Drafts in CRM notes | **KEEP.** Sends go through Apollo so they are captured; a Gmail send is the fallback and is captured too. |
| Activity capture | `crm/activity.py` + Gmail, Calendar, Apollo connectors | Built; one run (29 rows) | **RUN WEEKLY** as step 3 of the Monday Data Sync. Add Apollo emailer events (delivered, replied, bounced) so the 25 sequence sends are counted. |
| Web presence and inbound | Squarespace site; Google Search Console; Contact form | Live; contact page 404; Search Console unverified N | **FIX (Gate 0).** Contact page, domain email restored, AI crawlers allowed (the AI-visibility plan needs them), Search Console verified. |
| Booking | Google Calendar booking page on the domain mailbox (D6) | Decided 25 Sep; not verified live | **BUILD (Gate 0).** One link behind "Book a 20-minute call". Booked events become ACTIVITY meetings. |
| AI visibility | The 42-prompt bank in GTM Control | Manual | **AUTOMATE LATER** as a monthly routine that logs results (growth item G5). Do not finish the Profound connector; remove it. |
| Command and status | GTM Command Center + Atlas registry + morning brief | Live | **KEEP.** The registry is the only status store (Phase 1). |
| Collateral and decks | Gamma (connected), Canva (connected) | Both connected | **KEEP BOTH with one job each:** Canva for brand assets and the site; Gamma for client-facing decks. Remove SlidesGPT. |
| Signals | Vibe business events; Apollo visitors; Apollo job postings | Not wired (registry `proposed`) | **PHASE 2**, only after a `jobs/` row, estimate and go. Segment D (referrers) stays un-triggered. |

### Operational stack

| Job | Tool | Status today | Decision |
|---|---|---|---|
| Mail, calendar, docs, files, video | Google Workspace, one seat, on strategicmarketinsights.services | Domain address exists on paper; never used; no SPF/DKIM/DMARC evidence N | **THE MISSING FOUNDATION.** One Business Starter seat (about 7–8 USD a month E). SPF, DKIM and DMARC (p=none, then quarantine). Every outbound system (Apollo, booking page, contact form, invoices) sends from it. Remove the Microsoft 365 connector. |
| Contracts and signature | Google Docs SOW and MSA templates from the EOS stages; e-sign | None | **ADD BEFORE THE FIRST CALL CONVERTS.** Any e-sign tool that returns a PDF and needs no contact database: PandaDoc's free e-sign tier or Dropbox Sign (Drive-native) fit. E. The signed PDF is filed to the engagement folder; ENGAGEMENT holds the link. |
| Invoicing, payments, books | QuickBooks Online (first-party connector); see section 4, which revised an earlier Wave pick | None | **ADD** at the first signed engagement. Open the account on the domain mailbox. One invoice template that names the archetype code. |
| Time, expenses, credits | Operations Workbench (9 Sep) | Sample data | **KEEP.** Do not buy Harvest or Toggl. Replace the sample data at the first engagement; it becomes LEDGER_ENTRY in Phase 4. |
| Engagement workspace | Drive folder template per engagement (intake, contract, evidence, deliverables) + P3/P4 runbooks | None | **ADD** as a template now; wire "won → engagement" to create it in Phase 3 (T6). |
| Client intake | SMI Engagement Intake page (mailto today) | 22 questions; ends in an email to a personal inbox | **REROUTE.** Point the mailto at the domain mailbox and label it. The Phase 3 Intake handler reads that Gmail label and writes INTAKE_SUBMISSION. This settles stipulation N5: no public write to a page is needed. |
| Governance and knowledge | This repo, the Claude Project, the Governance Contract page, CLAUDE.md | Live | **KEEP.** |
| Automation | Claude Code Remote routines + GitHub Actions | Live; heartbeat not yet in force | **KEEP.** The Monday Data Sync heartbeat (5 Oct shadow) is the reliability fix. |
| Canonical store (Phase 5) | Supabase (managed Postgres, triggers, CI-writable, connector already installed) | Connector `connect_incomplete`; parked | **NAME IT AS THE D4 DEFAULT**, leave it parked. It answers "a store CI can write" without BigQuery. BigQuery stays parked as an analytics mirror. |
| Design tooling | Canva | Connected | **KEEP.** Remove Figma and Miro. |
| Engagement-scoped connectors | PubMed, NPI Registry, ICD-10, CMS Coverage, protocols.io | Connected (the Liminal validation work) | **KEEP while that engagement is live**, tagged `engagement-scoped` in the registry so they are not mistaken for stack. |
| Everything else | Brand24, Windsor.ai, FactSet, S&P, Oxford Economics, Monte Carlo, Hugging Face, api.agi.tech, Caffeine | Half-connected or unused | **REMOVE**, or write the one job each does into the registry. A connector with no registry node is not part of the stack. |

Monthly cost of the recommended stack at today's volume: Google Workspace
one seat, Apollo (plan tier unread N), Squarespace (existing), e-sign free
tier, QuickBooks only once an engagement is signed, Vibe one-time packages
as approved. Nothing new above about
10 USD a month until the first engagement is signed. E

## 4 · Connectors by GTM function

The seven functions are the Command Center's own (`dashboard/main`
`functions`), with the number of artifact cards each holds today. Registry
states were read on 27 Sep 2026 (SearchMcpRegistry, ListConnectors). Value is
a judgment (E) of what each connector adds to a record the plan already
needs. The test for any connector: it feeds a record that exists or is
scheduled (ACTIVITY, SIGNAL, PROPOSAL, ASSERTION, LEDGER_ENTRY,
INTAKE_SUBMISSION), it brings no contact table of its own, and it gets a
registry node the day it is wired.

### Pipeline Generation (2 cards · Apollo, Vibe Prospecting connected)

| Connector | State | Job | Feeds | Value | Call |
|---|---|---|---|---|---|
| Apollo.io | connected | Identity, lists, sequences, events, visitors | PERSON · ACTIVITY · SIGNAL | In use | Use more of it: visitor tracker, open tracking, one sequence per segment |
| Vibe Prospecting | connected | Firmographics, technographics, events | ORGANIZATION · FIELD_PROVENANCE · SIGNAL | In use | The one enrichment vendor; needs a funded balance and a floor |
| Lusha · Crustdata · ZoomInfo | not installed | Third data vendor | PERSON (duplicate) | None | Not now; Lusha only if phone coverage blocks Segment C calls (trial ≤ 20, TCPA) |
| HubSpot · Pipedrive · Close · Attio | not installed | Hosted CRM | a seventh contact store | None | Not before Phase 5 |

### Market Intelligence (3 cards · Vibe; Bright Data plugin; five healthcare connectors engagement-scoped)

| Connector | State | Job | Feeds | Value | Call |
|---|---|---|---|---|---|
| Parallel Search | not installed · free · no sign-in | Web search and fetch for the composition run's research leg | ASSERTION (raw) · run coverage | Medium | Add: one call site for web research (C4), citable in coverage files |
| Crunchbase MCP | not installed · paid | Funding rounds, company signals | SIGNAL (funding → Segment A → FRL, first touch A1) | Medium | Only when Segment A starts, only through the broker; never overwrites Vibe |
| Similarweb · Semrush · Ahrefs | not installed · paid | Traffic, audience, competitor maps | ASSERTION for the MKT line | Low now | Engagement-funded only |
| FactSet · S&P · Oxford Economics · Monte Carlo | connect_incomplete | Institutional data | none | None | Remove; reconnect one when a client scope names it |
| Firecrawl | not installed | Scraping for P3 | ASSERTION | None | Bright Data already does this |

### Messaging & Content (7 cards · Gmail, Canva, Gamma connected; Brand24, Profound incomplete)

| Connector | State | Job | Feeds | Value | Call |
|---|---|---|---|---|---|
| Gmail | connected | Sends and replies | ACTIVITY | In use | Repoint to the domain mailbox |
| Typefully | not installed · paid | Scheduled LinkedIn posts | ACTIVITY (subject-only) | Medium | Add after Gate 0; LinkedIn is where intake requests come from and two of seven sequence steps happen |
| Ahrefs Brand Radar · OpenRush | not installed · paid | AI-answer citations | the 42-prompt log (G5) | Low now | Run the prompt bank by routine first; buy at three months if it moves |
| Brand24 · Profound | connect_incomplete | Listening; AI visibility | none | None | Remove |
| Canva · Gamma | connected | Brand assets; client decks | files | In use | Keep, one job each; remove SlidesGPT |

### Strategy & Positioning (5 cards · the owner's own documents)

| Connector | State | Job | Feeds | Value | Call |
|---|---|---|---|---|---|
| Anthropic Economic Index | not installed · free | Public data on AI use by occupation | evidence for the SYS line and the case study (G6) | Low | Optional, when the SYS positioning page is written |
| Consensus | not installed | Scientific literature | none | None | PubMed already serves the Liminal work |
| Nothing else | | This function is thinking, not tooling | | None | No connector improves a positioning decision |

### Revenue Operations (5 cards · Google Calendar, Gmail connected; the CRM System page is the store)

| Connector | State | Job | Feeds | Value | Call |
|---|---|---|---|---|---|
| PandaDoc | not installed · free e-sign tier | Create from markdown, send, sign, read status | PROPOSAL (drafted → sent → signed) · ENGAGEMENT (signed PDF) | **High** | Add at the first accepted proposal or Phase 3. The run already writes the proposal as markdown. Docusign heavier; Jotform Sign, Signeasy fallbacks |
| Intuit QuickBooks | not installed · first-party connector | Invoices, payments, P&L | LEDGER_ENTRY · proof loop (G4) | **High** at first engagement | **Revises the Wave pick above:** Wave has no connector, so its invoices never reach a record. QuickBooks Online does (Meridian connector writes). FreshBooks is the alternative with a connector |
| Calendly | not installed | Booking | ACTIVITY | None | D6 chose a Google Calendar booking page; no second booking tool |
| Stripe | not installed | Card payments | LEDGER_ENTRY | Low | Only if a fixed-fee Viability Test is sold from the site |
| Google Calendar | connected | Meetings | ACTIVITY (gcal:) | In use | Capture runs weekly from 19 Oct |

### Engagement Delivery (4 cards · Google Drive connected; Workbench holds sample data)

| Connector | State | Job | Feeds | Value | Call |
|---|---|---|---|---|---|
| Tally | not installed · free tier | Forms with logic; fetch submissions | ASSERTION (VSP screeners, surveys) · INTAKE_SUBMISSION | **High** | Add at the first Validation Sprint or Phase 3. The Tally survey skill writes the specs; the connector builds and pulls. Gives client intake a direct submissions path |
| tldv · Fireflies · Read AI | not installed · free tiers | Transcripts from Meet, Zoom, Teams | ASSERTION with source pointer (C3) for 30–40 VSP interviews; ACTIVITY | **High** for VSP and DRF | One, chosen by the client's meeting tool, at the first interview-based engagement; consent per interview; transcripts in the engagement's Drive folder |
| Slack · Notion · Asana | not installed | Client workspace | none | Low | Not until a client asks |
| Productive | not installed | Projects, time, invoicing in one | replaces Workbench + QuickBooks | None | Phase 4 buy-versus-build question; the Workbench is a proof asset |
| Google Drive | connected | Engagement folders | ENGAGEMENT files | In use | Folder template per engagement; created by the won → engagement handoff |

### Governance (4 cards · GitHub, Claude Code Remote, Google Drive connected; Supabase incomplete)

| Connector | State | Job | Feeds | Value | Call |
|---|---|---|---|---|---|
| GitHub · Claude Code Remote | connected | Evidence ledger, routines | runs, proposals, CHANGELOG, runlog | In use | The heartbeat is the one addition needed |
| Supabase | connect_incomplete | Managed Postgres, triggers, CI-writable | Phase 5 store (D4) | Medium, Phase 5 | Keep parked as the D4 default; connect only when a trigger fires |
| Make | not installed | Scenario automation | none | None | Routines and Actions already run every job; a second scheduler is a second clock |
| Microsoft 365 · Miro · Figma · Hugging Face · Windsor.ai · api.agi.tech · Caffeine | incomplete or unused | Duplicates or no job | none | None | Remove, or write the one job each does into the registry |

### Value to add, ranked

1. **PandaDoc** (High): closes Composed → Proposal → Won as records with
   signature evidence. First accepted proposal or Phase 3.
2. **Intuit QuickBooks** (High at first engagement): invoices become
   LEDGER_ENTRY rows; the proof loop gets real actuals. Replaces the Wave pick.
3. **Tally** (High): VSP screeners and surveys; a direct submissions path for
   client intake. Free tier; the spec-writing skill exists.
4. **tldv or Fireflies** (High for VSP and DRF): interview transcripts become
   sourced ASSERTION rows. One connector, at the first interview engagement.
5. **Parallel Search** (Medium): free, no sign-in, no contact table; one named
   web-research call site for the composition run. Can be added this week.
6. **Crunchbase** (Medium): funding SIGNAL rows for Segment A, through the
   broker, after Gate 0 opens Segment A.
7. **Typefully** (Medium): a LinkedIn cadence from copy already written, after
   Gate 0, logged as ACTIVITY.
8. **Similarweb, Semrush, Ahrefs** (Low now): engagement-funded, not stack.

Sixteen connectors are named as none. Removing the fourteen installed and
incomplete is step 9 of the plan. Adding any of the eight above follows the
same rule as every tool: a registry node, a field-owner line, no contact
table, and a review if it carries no data for 30 days.

## 5 · The largest gaps now, ranked

1. **Gate 0 is open with three days left.** Contact page, domain mailbox in
   use, booking link. Business gap; blocks three of four segments.
2. **First touches are counted three ways (1 · 25 · 29).** The kill check's
   denominator is unmeasured. Architecture gap; the fix is built (T2) and
   needs one reconciliation and one weekly run.
3. **Outreach comes from a personal Gmail on a free domain.** Deliverability
   and positioning. Fixed by the Workspace seat plus DNS records.
4. **Enrichment has no live path until 11 Oct and no funded firmographics
   path at all.** Accounts uncreated (34 held), codes on 0 of 64.
5. **No back office.** Contract, invoice, payment, engagement folder, fee
   floor. Needed before the first call converts.
6. **Routine reliability is unproven.** The enrichment push has never
   recorded a run; the heartbeat is not yet in force.
7. **Connector and sequence sprawl.** 14 connector candidates for removal;
   two Apollo sequences with no segment naming and 10 overdue tasks.
8. **Personal artifacts in the business pinned set.**

## 6 · Plan of action

Owner tasks are UI work on the owner's machine (no commands to run). Session
tasks run from the Claude Code session that owns this repo. Scheduled tasks
already exist as routines; do not start them from another session.

### Sat 27 – Wed 30 Sep · Close Gate 0 (owner, about 3 hours) E

1. **Google Workspace seat on the domain** (owner). Create the mailbox; add
   SPF, DKIM and DMARC (p=none) at the DNS host. Confirm by: send one message
   to a Gmail address, open "Show original", and read SPF, DKIM and DMARC all
   as PASS.
2. **Squarespace** (owner): create `/contact` with the form and add it to the
   navigation; restore the domain address in the footer; allow AI crawlers
   under Settings → Crawlers (the AI-visibility plan needs them); hide the
   cart; add the Services meta description. Confirm by: the 07:00 ET daily
   site check on Thu 1 Oct shows `f71_contactMissing` false and
   `f82_domainEmail` true.
3. **Booking page** (owner): a Google Calendar booking page on the new
   mailbox, behind "Book a 20-minute call" on the Contact page. Confirm by:
   open the link logged out, book a test slot, and receive the invite from
   the domain address.
4. **Apollo sender** (owner): link the domain mailbox in Apollo, make it the
   default, turn on open and click tracking on both sequences. Do not add
   contacts to a sequence from the personal Gmail again. Do not rename
   sequences through the API (CLAUDE.md).
5. **Mon 28 Sep, scheduled:** 07:00 ET Apollo sync, 07:30 ET enrichment push,
   08:00 ET Command Center refresh, 10:00 ET Phase 0 gate check. Owner reads
   the result. If the 07:30 push again records no run, that is finding R3
   live: the shadow Data Sync moves up from 5 Oct to the next available
   Monday and the push is not trusted in the meantime.
6. **Mon 28 Sep, session, after the refresh:** reconcile 1 · 25 · 29 once.
   Ingest Apollo emailer events for the First Touch Sequence into ACTIVITY
   (`channel_ref apollo:<message id>`, so no Gmail-captured send is counted
   twice), write one runlog line, and make the scorecard's "first touches"
   read the activity count. From then on the number has one source.

### Thu 1 – Fri 16 Oct · Phase 1 continuation and close

7. **Thu 1 Oct 11:00 and 13:00 ET, scheduled:** the Phase 1 continuation
   (Gate 0 into Launch Check) and the Phase 2 held pieces (the 34 accounts
   created with `org_id` set on exact domain match; Data Sync into shadow;
   Ops refresh scorecard on activity rows).
8. **Owner, after step 7 (about 30 minutes):** set `segment_code` and
   `archetype_code` on the 35 qualified contacts from the CRM page pickers.
   Confirm by: the 5 Oct refresh reports codes on 35 of 64.
9. **Owner (20 minutes):** disconnect the 12 `connect_incomplete` connectors,
   Explorium_Connector and SlidesGPT; keep the engagement-scoped healthcare
   set. **Session, same day:** write each removal to the registry as
   `retired` with "never carried data" as evidence, and tag the healthcare
   connectors `engagement-scoped`.
10. **Owner:** decide the second Apollo sequence. Recommended: archive it
    until Gate 0 closes, then re-create one sequence per segment named by
    code (A, B, C). Clear or skip the 10 overdue manual tasks so the
    sequence reflects what was actually done.
11. **Owner:** unpin Resume Match Desk from the business set (it stays
    published and private).
12. **Mon 5 and 12 Oct, scheduled:** Data Sync shadow runs. **Mon 12 Oct
    10:00 ET, scheduled:** Phase 1 close (Stack Status pointer, Phase 1 gate
    written). The gate is real only if the stack panel matched the registry
    two Mondays running.

### Sat 11 Oct – Sun 15 Nov · Credits, back office, cutover, kill check

13. **11 Oct, Apollo reset:** 285 lead credits for the cycle to 11 Nov.
    Reveal on send only; floor 10; the broker's `jobs/` row before any bulk
    reveal. Owner reads the Vibe balance in the Vibe UI once; session writes
    it to `meta/credits` with a floor. N
14. **Back office (owner, about 2 hours, before the first call converts):**
    SOW and MSA as Google Docs templates from the seven EOS stages; one
    e-sign account on the domain mailbox; a Wave account on the domain
    mailbox with one invoice template; a Drive folder template per
    engagement; the fee floor written into GTM Control open item 4 and the
    Command Center to-do closed. **Session:** each becomes a registry node
    (`live`, kind `tool`) so the atlas knows they exist.
15. **Mon 19 Oct 10:00 ET, scheduled:** Phase 2 cutover. The two old
    routines are paused, never deleted. Install the Apollo website-visitor
    tracker the same day (Gate 0 having closed).
16. **Signals, Phase 2, only with a funded Vibe balance:** a `jobs/` row for
    business events on the 34 accounts, a free estimate, the owner's go.
    Without funding, signals stay `proposed` and the trigger mapping waits.
17. **Client intake reroute (owner, 10 minutes):** point the SMI Engagement
    Intake mailto at the domain mailbox and add a Gmail filter that labels
    it. This is the Phase 3 Intake handler's input.
18. **Mon 16 Nov 10:00 ET, scheduled:** the 15 Nov kill check, computed from
    ACTIVITY. If fewer than 6 calls from 80+ sends: stop after Phase 2 (D3),
    keep the broker and activity capture, and put the hours into the three
    Segment C diagnostics. If the thresholds hold: Phase 3 starts, with
    PROPOSAL and OPPORTUNITY records and the Intake handler reading the
    labelled Gmail.

### Standing rules from this assessment

- No new SaaS with its own contact table. A connector with no registry node
  is not part of the stack.
- One number, one source: any figure on the Command Center is computed from
  a record or reads "not computed". Never hand-entered.
- Every outbound message (sequence, booking invite, invoice, form
  confirmation) leaves from the domain mailbox.
- A phase starts at its gate. Two phases have already started early; from
  here the scheduled routines decide.

## 7 · Stipulations this assessment adds

1. Whether a Google Workspace seat exists for the domain address today, or
   only a forwarding alias at the registrar.
2. Whether SPF, DKIM and DMARC records exist on the domain.
3. Whether the Google Calendar booking page (D6) has been created.
4. The Vibe Prospecting balance (last known 746 on 17 Sep; "240 could be
   exported" on 25 Sep).
5. The Apollo plan tier (observed limits: 285 lead credits, 160 direct dial,
   20 inbound website-visitor credits, 150 conversation credits per cycle).
6. Whether the second Apollo sequence was intended, and for which segment.
