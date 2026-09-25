# CLAUDE.md

Facts the owner of this repo has corrected in past Claude Code sessions. Each
was gotten wrong at least once. Follow them as written, and when the owner
corrects something new, add it here in the same change.

## The firm's name

- The firm is **Strategic Market Insights** (SMI), as on its website and the
  Apollo account list. Never "Strategic Marketing Insights". CRM notes are
  append-only, so a wrong name in a filed proposal can't be taken back.
- The name lives in `BRAND` in `crm/note_to_founder.py`. Use that rather than
  retyping it.

## The owner works on Windows

- Commands the owner will run on their own machine must work in PowerShell:
  a backtick for line continuation (not `\`), `$env:APPDATA\terraform.d`
  (not `~/.terraform.d`), and `Invoke-RestMethod` with `ConvertFrom-Json`
  instead of `curl | jq`.
- Claude's own commands in a cloud session still run on Linux; this is about
  what you ask the owner to run.

## This repo is public

- Never commit infrastructure identifiers: GCP project IDs or numbers, HCP
  organization or workspace names. Use placeholders or read them from the
  environment. `.env` and `terraform/terraform.tfvars` are gitignored, the
  Terraform `cloud {}` block reads `TF_CLOUD_ORGANIZATION` and `TF_WORKSPACE`,
  and CI reads repository variables.

## Prospect research and proposals: the intake form is the specification

`crm/guardrails.py` and `scripts/compose_account.py finalize` enforce these.
Don't work around them.

- **Domain lock.** Research only the company at the exact domain on the intake
  form. A similarly named company at another domain is a different company,
  even if a search result says they're the same: clarid.ai is not claridi.ai.
  List lookalikes under Gaps and use nothing from them.
- **Empty means empty.** When the intake domain yields nothing, the proposal
  says "not found". Never fill the gap from a lookalike or a guess.
- **Credit spend.** Apollo enrich and Vibe Prospecting enrichment cost
  credits. Run them only when the form ticks "Allow credit spend on this
  account", and only for the intake domain.
- **One proposal per run.** A changed proposal is a new run from the Intake
  page, never an edit or revision of one already filed.

## HOLDs and "unconfirmed" flags clear only after an independent check

- A HOLD, or anything Claude called unconfirmed, is never cleared by a verbal
  "confirmed" alone. On 24 Sep 2026 a verbal confirmation cleared the
  Claridi.ai flag, the run went ahead on the lookalike clarid.ai, and undoing
  it took 30 minutes.
- It clears after one independent check: open the actual domain (side by side
  with any lookalike), pull a second source, or ask Claude "what would
  confirm this is the same company?" and do that check.
- When the owner confirms without a check, reply with the one specific check
  (about 90 seconds; each HOLD line names it after "Confirm by:") and act only
  after they report what it showed. Record that result in the run doc or an
  appended CRM note.

## "Founder" means the prospect's founder

- The ICP is small startups, so the requester on the intake form is the
  prospect's founder. The proposal's next step and the note to the founder
  (`crm/note_to_founder.py`) are addressed to them.
- The internal check before a proposal goes out is "Review before sending"
  (`crm/review.py`). It's for SMI and is never shown to the prospect.

## Unified Architecture Blueprint (24 Sep 2026)

The route the stack follows from 24 Sep 2026. The full import (findings,
model, connectors, phases, sunset register, decisions) is in
`docs/unified-architecture-blueprint.md`; the source PDF stays out of this
public repo. The CRM Systems Atlas (`registry/main` in that artifact's
database) is the map; the blueprint is the route.

**Pages 1–2, as read.** Page 1 is the cover and the consolidation in six
numbers, today → target: places a contact record can live 6 → 2 (3 after
Phase 2); joins computed at read time instead of stored 2 → 0; surfaces
reporting stack status 3 → 1 (they disagreed on 5 facts); rulebooks for the
same governance rules 4 → 1; routines in the CRM data path 6 → 4; Explorium
billing paths 2 → 1. Claims carry the Engagement Operating System tags:
S supported, N needs stipulation, E estimate. Page 2 is the executive
summary. Five findings: the stack is built several times over; one
constraint causes most of it (the CRM's database can be written only from a
Claude session that loads ArtifactData, which pushed the weekly merge into a
git master, bound two routines to one session, and let a retired sync report
success while writing nothing); two links between records are guesses (email
match, company-name substring); the status surfaces disagree; enrichment is
limited by credits, not code. Six actions in order: stop the drift; one
status surface (the registry); store the keys; one Enrichment Broker;
capture activity automatically; thread the Service Taxonomy through every
record, then intake and closed-won as records, then one Engagements module.
The sequencing rule: Phases 0–1 are housekeeping sized not to compete with
Gate 0 (30 Sep); Phase 2 pays back before the 15 Nov kill check; Phases 3–5
start only if the kill thresholds did not fire. If they fire, the
architecture shrinks, not grows.

**Phases.** P0 Stop the drift (24–30 Sep) · P1 One surface, one vocabulary
(1–16 Oct) · P2 Keys, broker, activity (19 Oct – 15 Nov; gate: the scorecard
computes itself from ACTIVITY) · P3 Proposals + intake as records (16 Nov –
18 Dec, only if the kill thresholds did not fire) · P4 Engagements module
(Jan–Feb 2027, needs a signed or live engagement) · P5 One canonical SQL
store (trigger-gated). Each phase has a gate in the docs file; a phase whose
entry condition is unmet does not start.

**Rules that follow from it.**
- Whatever is wired or retired is written to `registry/main` in the same
  session, on primary evidence; bump `version` and `updated`.
- The three Monday routines run on `CRON_TZ=America/New_York`: Apollo sync
  07:00, enrichment push 07:30, Command Center refresh 08:00 ET. The
  no-compose window is 06:45–08:15 ET year-round. State Monday times in ET.
- BigQuery, Vertex and HCP Terraform are parked (registry status `parked`),
  not blockers, until Phase 5.
- The Intake artifact is titled "Account Composition Intake". The retired
  ledger page and the 26 Aug Workbench are unpinned; the 9 Sep Workbench is
  pinned. The CRM System is the system of record until the SWAT Engine ships.
- Decisions D1–D6 are the owner's; none is made for them. Decided 25 Sep
  2026: D1, enrichment is bought from the Vibe Prospecting balance (a
  one-time backfill of the 50 matched prospects, cost estimate first; the
  weekly REST step stays match-only); D6, the Gate 0 booking link is a Google
  Calendar booking page on the domain mailbox, so Carly is disconnected.

**Phase 0 status, 25 Sep 2026.** Done: steps 1–8 (the unpins and the
pin, the retitle, GTM Control item 7, CRON_TZ on the three routines, parked
nodes in registry v1.5 and on the Stack Status page, the orphan "Operations
Workbench Design System" card removed from the Command Center; D1 and D6
decided and written to registry v1.5). Open, in the owner's settings:
disconnect Carly and ZoomInfo, label the Drive mirror "not a source"; the atlas page's embedded fallback snapshot
and its clock caption refresh at the next atlas refresh. Gate check: the
Monday 28 Sep Command Center refresh.
