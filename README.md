# Claude Artifacts — CRM master ledger

A weekly, two-way contact data exchange between **Apollo** and **Explorium**,
reconciled into one master database that lives in a Claude artifact and is
mirrored in this repo.

**Master database (artifact):** https://claude.ai/artifact/VcbjegQv71QGNveHtt415f
**Committed mirror:** [`data/master/contacts.json`](data/master/contacts.json)
**Change history:** [`data/CHANGELOG.md`](data/CHANGELOG.md)

## What runs, and when

```
  Monday 06:00 UTC  ─┬─  pull_apollo.py      ──┐
  (GitHub Actions)   └─  pull_explorium.py   ──┼──▶  merge_master.py  ──▶  commit
                          (run in parallel)    │
                                               └──▶  push_apollo.py  (opt-in writeback)

  After the Action   ─── Claude routine:  import artifact edits ▶ re-merge ▶ push master into artifact db
```

| Step | Script | Reads | Writes |
|---|---|---|---|
| Pull Apollo contacts | `scripts/pull_apollo.py` | Apollo API | `data/staging/apollo.json` |
| Enrich via Explorium | `scripts/pull_explorium.py` | previous master + Explorium API | `data/staging/explorium.json` |
| Merge | `scripts/merge_master.py` | both staging files | `data/master/contacts.json`, `data/CHANGELOG.md` |
| Writeback (opt-in) | `scripts/push_apollo.py` | master | Apollo API |
| Artifact → repo | `scripts/import_artifact_edits.py` | a db dump | master |
| Repo → artifact | `scripts/export_artifact_batch.py` | master | `data/artifact/batch_*.json` (fed to the artifact db) |

The two pulls are independent jobs in
[`.github/workflows/weekly-crm-sync.yml`](.github/workflows/weekly-crm-sync.yml).
Explorium enriches the *previous* master rather than this week's Apollo pull,
which is what lets them run at the same time; a contact new to Apollo this
week is enriched next week. Dispatch the workflow with
`explorium_roster=apollo` to run them serially instead.

## How the merge decides

Every source normalizes into one canonical record (`crm/schema.py`). The merge
(`crm/master.py`) is **field-level**: each field is resolved on its own, and the
winning claim is recorded in `provenance` with its source and timestamp.

1. An empty incoming value never overwrites a populated one.
2. A higher-trust source wins (`FIELD_TRUST` in `crm/schema.py` — Explorium
   outranks Apollo on firmographics, Apollo outranks Explorium on email).
3. **Manual edits made in the artifact outrank both feeds.** A human
   correction is never silently undone by the next sync.
4. At equal trust, a materially fresher observation (>7 days) wins.
5. Otherwise the incumbent holds and the disagreement is logged as a
   **held conflict** — it shows in the artifact's review queue.

Records match on email, then LinkedIn URL, then name + company domain. An
incoming record that matches *two* master records is never fused; it is logged
as an **ambiguous match** for a human to resolve. Ids are derived from the
strongest identity key, so a rebuild from scratch yields the same ids and the
master file stays diffable.

`tests/test_merge.py` covers all of this. Run `python -m pytest tests -q`.

## Setup

Repository secrets (Settings → Secrets → Actions):

| Secret | Used by |
|---|---|
| `APOLLO_API_KEY` | `pull_apollo.py`, `push_apollo.py` |
| `EXPLORIUM_API_KEY` | `pull_explorium.py` |

Nothing else to install — the scripts use only the Python standard library.

Writeback to Apollo is off unless **both** `APOLLO_WRITEBACK_ENABLED=true`
and `--apply` are set (the workflow's `writeback` input does both). Without
them `push_apollo.py` prints what it *would* send. It never writes email back
to Apollo.

## The artifact as master

The artifact holds one document per contact in its `contacts` collection and
sync metadata in `meta/sync`. Any signed-in viewer can search and filter;
anyone at *interact* level or above can edit a record in place. An edit is
stored with `source: "manual"` and the editor's id, and the next sync respects
it.

To move data between the repo and the artifact from a Claude session:

```bash
# repo -> artifact (after a merge)
python scripts/export_artifact_batch.py          # writes data/artifact/batch_*.json + meta_sync.json
# then, per batch file:  ArtifactData(action="batch", url=<artifact>, writes=<file contents>)
# and:                   ArtifactData(action="set", collection="meta", doc_id="sync", file_path="data/artifact/meta_sync.json")

# artifact -> repo (before a merge, to capture edits)
# ArtifactData(action="list", url=<artifact>, collection="contacts", out_dir="dump")
python scripts/import_artifact_edits.py dump
```

The artifact database holds at most 5,000 documents. Past that, split the
ledger by list or region.

## Agents

[`agents/account-research/`](agents/account-research/) — a Google ADK
multi-agent workflow, modelled on Google's `fomc-research` sample, that writes
an account brief for any company in the master ledger. See its README for
setup, running with `adk run` / `adk web`, and deployment to Agent Runtime.

[`python/agents/`](python/agents/) — samples vendored verbatim from
`google/adk-samples`, pinned to a commit; currently
`brand-aligned-presentations` (brand-adherent `.pptx` decks from research,
RAG and a corporate template). See that directory's README for provenance.

## MCP servers

[`.mcp.json`](.mcp.json) registers two Explorium servers for Claude Code.
They are different servers on different hosts:

- **`explorium-docs`** — the Mintlify-hosted documentation MCP
  (`search_explorium_docs`, `query_docs_filesystem_explorium_docs`,
  `submit_feedback`). Read-only, no credentials.
- **`explorium-agentsource`** — the B2B data API MCP (`enrich-business`,
  `match-prospects`, `fetch-businesses-events`, …). Spends credits; needs
  `EXPLORIUM_API_KEY`.

Both servers use **OAuth**. `.mcp.json` deliberately carries no
`Authorization` header: setting one disables the OAuth flow, and the REST
API key in `crm/config.py` is not a token for the MCP endpoint anyway.

### Authorizing the MCP servers

`/mcp enable`, `disable` and `reconnect` never authenticate — they only
toggle a server's config. Authorization needs a browser, so it happens in
one of two places:

- **Local Claude Code (terminal or desktop app).** Open this repo; approve
  the project's `.mcp.json` when prompted. Run `/mcp` with no arguments,
  pick the server, choose **Authenticate**, and log in in the browser tab
  it opens. This applies to that machine only.
- **claude.ai and remote Claude Code sessions.** These cannot run OAuth
  themselves. Instead add the server as a connector: claude.ai → Settings →
  Connectors → *Add custom connector*, with the same URL from `.mcp.json`.
  OAuth runs in the browser there, and the tools then appear in every web
  session as `mcp__<Connector name>__*`.

The docs server URL follows Mintlify's `<docs-host>/mcp` convention and has
been observed answering with an OAuth challenge, which confirms it is a live
MCP endpoint. If it ever moves, it is defined in `.mcp.json` and
`crm/config.py` only.

### Google Cloud MCP servers

`.mcp.json` also registers two of Google Cloud's remote MCP servers for
project `922106495655`. The registry names them by URN; the client connects
by URL:

| URN (`urn:mcp:googleapis.com:projects:922106495655:locations:global:…`) | Entry | URL | What it does |
|---|---|---|---|
| `…:agentregistry` | `gcp-agent-registry` | `https://agentregistry.googleapis.com/mcp` | Discover agents, MCP servers and model endpoints catalogued in the project |
| `…:aiplatform` | `gcp-agent-platform` | `https://aiplatform.googleapis.com/mcp/generate` | Agent Platform (Vertex AI) — the `generate` toolset; other toolsets live at their own `/mcp/<toolset>` path |
| `…:bigquery` | `gcp-bigquery` | `https://bigquery.googleapis.com/mcp` | List datasets and tables, read metadata, run SQL against the project's BigQuery data |

Google's servers do **not** use the in-client OAuth flow the Explorium
servers use. They take a Google bearer token and a quota-project header,
which `.mcp.json` reads from the environment:

```bash
# once per machine
gcloud auth application-default login

# before each Claude Code session (token lives ~1 h)
eval "$(scripts/gcp_mcp_env.sh)" && claude
```

`scripts/gcp_mcp_env.sh` exports `GCP_MCP_ACCESS_TOKEN` from
`gcloud auth application-default print-access-token` and `GCP_PROJECT`
(override it to point the same entries at another project). The token never
lands in the repo. In the project, enable the APIs — the BigQuery MCP server
is switched on by enabling the BigQuery API itself:

```bash
gcloud services enable agentregistry.googleapis.com cloudapiregistry.googleapis.com apihub.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable bigquery.googleapis.com
```

and give your identity the Agent Registry viewer, Vertex AI user, and
BigQuery job user / data viewer roles as needed.

These two entries work from a **local** Claude Code session with `gcloud`
installed. Remote and web sessions have no `gcloud` and cannot mint the
token, so there they will show as failed to connect — that is expected.

## Layout

```
.mcp.json                     MCP server registration
crm/config.py                 every endpoint, credential and tunable, once
crm/schema.py                 canonical record, identity keys, trust table
crm/master.py                 field-level merge, load/save
crm/http.py                   retrying stdlib JSON client
scripts/                      the six entrypoints above
tests/test_merge.py           merge behaviour
data/master/contacts.json     committed mirror of the artifact database
data/CHANGELOG.md             per-run record of what changed
artifact/crm.html             the published ledger page
.github/workflows/            weekly schedule
```
