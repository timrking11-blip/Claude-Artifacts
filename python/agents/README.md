# python/agents

All ADK agents live here, in the `python/agents/<name>` layout that
`google/adk-samples` uses. Two kinds:

## Ours

| Agent | Modelled on | Notes |
|---|---|---|
| [`account-research/`](account-research/) | `fomc-research` | Account briefs from the CRM master ledger; Claude on Vertex by default. Tests run in this repo's CI without credentials. |

## Vendored samples

Samples copied verbatim from [google/adk-samples](https://github.com/google/adk-samples),
laid out under the same `python/agents/<name>` path they have upstream. Each
directory is an exact `git archive` of the upstream tree at the commit below;
nothing inside is modified, so an upstream diff applies cleanly.

| Sample | Upstream commit | Date | Upstream path |
|---|---|---|---|
| [`brand-aligned-presentations/`](brand-aligned-presentations/) | [`4fddcec8b2e632a74d404334e4be3134213c044a`](https://github.com/google/adk-samples/commit/4fddcec8b2e632a74d404334e4be3134213c044a) | 2026-08-14 | `python/agents/brand-aligned-presentations` |

License: each sample carries its own `LICENSE` (Apache-2.0, Google LLC).

**Tests.** Vendored samples are not part of this repo's CI. Their suites
need Google Application Default Credentials at import time (every module in
`brand-aligned-presentations/tests` fails collection with
`DefaultCredentialsError` without them), so run them locally after
`gcloud auth application-default login`:

```bash
cd python/agents/brand-aligned-presentations && uv sync --dev && make test
```

To bring a sample up to a newer upstream commit:

```bash
git -C /path/to/adk-samples fetch origin <sha>
rm -rf python/agents/<name>
git -C /path/to/adk-samples archive <sha> python/agents/<name> | tar -x -C .
# then update the table above
```
