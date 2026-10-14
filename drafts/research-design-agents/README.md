# research-design-agents

Evidence-governed market research design agents, packaged as a Claude Code
plugin. They work for any product, market or category, and are not tied to
one project, industry or news cycle.

| Component | What it does |
|---|---|
| `agents/primary-research-designer.md` | Designs studies that collect new data: surveys, interviews, concept and pricing tests, experiments |
| `agents/custom-research-designer.md` | Scopes bespoke client studies: build, buy or reuse check, phased plan, deliverables, gates |
| `skills/research-brief` | Versioned brief: question, decision, jurisdictions, data, scope, reviewers |
| `skills/evidence-ledger` | Source register, claim ledger, search log, change control |
| `skills/primary-research-design` | Method choice, sampling arithmetic, instruments, analysis plan, consent |
| `skills/custom-study-scoping` | Client problem to research problem, reuse check, study architecture |
| `schemas/ledger.schema.json` | Machine-readable ledger shape |
| `evals/` | Test cases scored by `claude plugin eval` |
| `docs/` | Hermes Agent as a candidate runtime; relation to the intelligence layer |

The skills follow the Agent Skills standard (agentskills.io), so they are
written to load in other runtimes that read it, such as Hermes Agent (see
`docs/hermes-runtime.md`; not yet tested).

## Limits

These agents help plan and document research. They do not replace
subject-matter experts, legal counsel, privacy officers, security reviewers,
clinicians or regulators, and nothing they produce makes a product compliant,
safe, validated or legally approved.

## Use

Load the plugin for one session from a checkout:

```powershell
claude --plugin-dir C:\path\to\research-design-agents
```

Then ask for the agent by name, for example "use the primary-research-designer
to plan a pricing study for ...".

## Test

```powershell
claude plugin validate .
claude plugin eval . --runs 1 --no-publish
```

`eval` runs every case in `evals/` with and without the plugin and reports the
score difference. Each run uses your Claude account; pass `--max-cost-usd` to
cap a run.
