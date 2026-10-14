# drafts/

Work written before its own repository existed. It was staged on a side
branch so another session could read it, and the owner merged it into the
default branch on 14 Oct 2026 (PR #28, merge commit 037b6a8). It is not part
of the SMI stack: nothing in `crm/`, `scripts/`, `architecture/` or the
workflows reads it. It moves to its own repository once that repository is
created and its PROBLEM.md is confirmed, and is removed from here in the same
change.

One link runs the other way. Since 14 Oct 2026 the plugin's
`schemas/ledger.schema.json` is a byte-identical copy of the SMI evidence
ledger schema, `architecture/schemas/evidence-ledger.schema.json`, so that
there is one schema. `tests/test_ledger.py` checks the two are identical. When
the plugin moves out, that test goes with it, and the new repository takes the
schema from Claude-Artifacts.

- `research-design-agents/`: draft Claude Code plugin (two research design
  agents, four Agent Skills, a ledger schema, eval cases, docs), 14 Oct 2026.
  First eval run (one run per case, with and without the plugin): no net
  gain. pricing-study-design failed with the plugin and passed without it;
  unverified-market-size failed in both arms; vague-request-brief passed only
  with the plugin; health-app-custom-study passed in both.
