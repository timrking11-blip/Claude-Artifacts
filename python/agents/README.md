# python/agents — vendored ADK samples

Samples copied verbatim from [google/adk-samples](https://github.com/google/adk-samples),
laid out under the same `python/agents/<name>` path they have upstream. Each
directory is an exact `git archive` of the upstream tree at the commit below;
nothing inside is modified, so an upstream diff applies cleanly.

| Sample | Upstream commit | Date | Upstream path |
|---|---|---|---|
| [`brand-aligned-presentations/`](brand-aligned-presentations/) | [`4fddcec8b2e632a74d404334e4be3134213c044a`](https://github.com/google/adk-samples/commit/4fddcec8b2e632a74d404334e4be3134213c044a) | 2026-08-14 | `python/agents/brand-aligned-presentations` |

License: each sample carries its own `LICENSE` (Apache-2.0, Google LLC).

Our own agents, modelled on these samples rather than copied, live in
[`../../agents/`](../../agents/) (e.g. `account-research`, derived from
`fomc-research`).

To bring a sample up to a newer upstream commit:

```bash
git -C /path/to/adk-samples fetch origin <sha>
rm -rf python/agents/<name>
git -C /path/to/adk-samples archive <sha> python/agents/<name> | tar -x -C .
# then update the table above
```
