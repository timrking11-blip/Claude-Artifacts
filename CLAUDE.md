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

## "Founder" means the prospect's founder

- The ICP is small startups, so the requester on the intake form is the
  prospect's founder. The proposal's next step and the note to the founder
  (`crm/note_to_founder.py`) are addressed to them.
- The internal check before a proposal goes out is "Review before sending"
  (`crm/review.py`). It's for SMI and is never shown to the prospect.
