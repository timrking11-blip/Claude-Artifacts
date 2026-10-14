# Hermes Agent as a second runtime (candidate, not adopted)

Status: candidate · checked 14 Oct 2026 · owner: Tim King

## Why it is here

The intelligence layer this plugin may later feed is described in the owner's
architecture (see `intelligence-layer.md`). The owner asked that Hermes be
referenced as a way to build that layer. This page records what Hermes Agent
is, what was verified, and what must be true before it runs these agents.
It does not adopt Hermes.

## What was verified

Source: https://github.com/NousResearch/hermes-agent (README, read 14 Oct 2026).

| Claim | Evidence | Status |
|---|---|---|
| Hermes Agent is an open-source agent runtime by Nous Research | README: "The self-improving AI agent built by Nous Research." | FACT |
| MIT licence | README: "MIT — see LICENSE." | FACT |
| Reads Agent Skills (SKILL.md) | README: "Compatible with the agentskills.io open standard." | FACT, not yet tested with these skills |
| Connects to MCP servers | README: "Connect any MCP server for extended capabilities" | FACT |
| Model providers | README: "Nous Portal, OpenRouter, OpenAI, your own endpoint, and many others." Anthropic is not named in that line | Anthropic support UNVERIFIED |
| Keeps memory and writes its own skills | README: "Agent-curated memory with periodic nudges"; secondary sources describe a loop that creates skills from experience | FACT for memory; skill-writing UNVERIFIED in primary docs |
| Release, version, adoption figures | No release listed on the repo page; star counts in secondary sources disagree | UNVERIFIED |

## What is portable

The four skills in `skills/` use only the Agent Skills fields (`name`,
`description`, a Markdown body) and name no Claude-only tools, so they are
written to load in any runtime that reads the standard. The two files in
`agents/` are Claude Code subagent definitions and do not carry over; in
Hermes their role would be a system prompt or profile.

## Adoption check (before Hermes runs these agents)

Taken from the rule that no new tool is adopted without a demonstrated gap,
an owner, a boundary, a cost and an acceptance test:

1. **Gap.** Name what Claude Code cannot do that Hermes would (for example a
   persistent daemon, or chat-platform delivery). Without one, do not add it.
2. **Owner.** Who runs, updates and pays for the Hermes host.
3. **Boundary.**
   - Its self-written skills and memory must not modify the skills in this
     repo. Changes come back as a pull request a person reviews.
   - It writes nothing to a CRM or system of record. It produces ledger JSON
     (`schemas/ledger.schema.json`) and nothing else.
   - MCP servers and API keys are listed per deployment, read-only first.
4. **Cost.** Model and hosting costs as dated list-price estimates.
5. **Acceptance test.** The eval suite in `evals/` scores the same or better
   when the skills run in Hermes as when they run in Claude Code.

## Open questions

- Does Hermes support Anthropic models directly, or only through OpenRouter
  or a custom endpoint? (Check its provider docs.)
- Can its skill-learning loop be turned off, or pointed at a separate folder?
- The install command pipes a remote script to a shell. Read the script
  before running it on any machine that holds keys.
