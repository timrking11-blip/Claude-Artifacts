# Account Research agent

A multi-agent workflow, built on [Google ADK](https://google.github.io/adk-docs/)
and modelled on the
[`fomc-research` sample](https://github.com/google/adk-samples/tree/main/python/agents/fomc-research),
that produces an **account brief** for any company in the CRM master ledger:
who we know there, how reachable they are, where the record is thin or stale,
what the company does, and whom to approach first.

| Feature | |
|---|---|
| Interaction | Workflow — one question (which account), then it runs |
| Agents | `root_agent` → `research_agent` → `analysis_agent`, plus `summarize_page_agent` as a tool |
| Data | `data/master/contacts.json` (the committed ledger), the company's website, optionally BigQuery and Agent Registry via MCP |
| Model | **Claude on Vertex AI** by default (`claude-fable-5-1`; ADK's `Claude` wrapper over `AnthropicVertex`), or Gemini with `ACCOUNT_RESEARCH_MODEL_PROVIDER=gemini` |

**Composition diagram:** https://claude.ai/artifact/54uStUBsF87tb9uyrhLCav
(source: [`artifact/agent-composition.html`](../../../artifact/agent-composition.html))

## How it maps to the template

| fomc-research | account_research | Change |
|---|---|---|
| `root_agent` asks for a meeting date, `store_state` | asks for a company, `find_account` resolves it against the ledger | ledger lookup with AMBIGUOUS / NOT_FOUND handling |
| `research_agent` → statements, transcript, futures | `list_account_contacts`, `assess_ledger_quality`, `fetch_page` + `summarize_page_agent`, MCP | same coordinator pattern, different sources |
| `analysis_agent` prompt templated on state | same, keys `account`, `account_contacts`, `ledger_quality`, `website_summary`, `warehouse_findings` | |
| `fetch_page_tool` stores raw HTML | strips to text, caps at 20k chars | fits the summarizer's context |
| `rate_limit_callback` | unchanged | |
| `deployment/bigquery_setup.py` loads a CSV | loads the ledger JSON into `<dataset>.contacts` | |
| `deployment/deploy.py`, `test_deployment.py` | unchanged apart from names | |

## Setup

```bash
cd python/agents/account-research
cp .env-example .env          # fill in project, location, bucket
set -o allexport; . .env; set +o allexport

curl -LsSf https://astral.sh/uv/install.sh | sh    # once
uv sync --dev
```

The ledger tools read `../../../data/master/contacts.json` by default; set
`ACCOUNT_RESEARCH_LEDGER` to point elsewhere.

**BigQuery (optional, for the warehouse step and the `gcp-bigquery` MCP server):**

```bash
cd deployment
python bigquery_setup.py --project_id=$GOOGLE_CLOUD_PROJECT \
    --dataset_id=$GOOGLE_CLOUD_BQ_DATASET --location=$GOOGLE_CLOUD_LOCATION
```

**MCP tools (optional):** set `ACCOUNT_RESEARCH_ENABLE_MCP=1` and have
Application Default Credentials available (`gcloud auth application-default login`).
The agent then attaches the BigQuery and Agent Registry MCP servers for the
project in `GOOGLE_CLOUD_PROJECT` as tools. With it off, the warehouse step is skipped
and everything else works.

## Claude on Vertex AI

The provider is chosen in `account_research/model.py` (the tools never import
it, so they stay ADK-free). The agent runs on Claude by default, through ADK's `Claude` model wrapper --
the same `AnthropicVertex(project_id, region)` client the Anthropic SDK
documents, authenticated with Application Default Credentials.

```bash
gcloud auth application-default login          # once
python scripts/claude_vertex_smoke.py          # one request; proves project, region, model and ADC
```

Google's ADC helper is an alternative to the first line and does a little
more -- it installs the SDK if missing, sets the ADC *quota project* (which
is also what the `x-goog-user-project` header on the repo's Google MCP
servers needs), and sends a test request:

```bash
bash <(curl -sSL https://storage.googleapis.com/cloud-samples-data/adc/setup_adc.sh)
```

Note what it does **not** prove: its test request goes to a *Gemini* model
(`publishers/google/models/<gemini>:generateContent`). Claude on Vertex is
licensed separately, so a green run there says nothing about Claude access.
`scripts/claude_vertex_smoke.py` is the Claude gate -- run it second. The
Project **ID** the helper asks for is the same value `.env` needs for
`GOOGLE_CLOUD_PROJECT`.

Before the first run, enable the Claude model in **Vertex AI → Model Garden**
for the project. The smoke script's `NotFound` message is what you see when
it isn't. Variables:

| Variable | Default | Meaning |
|---|---|---|
| `ACCOUNT_RESEARCH_MODEL_PROVIDER` | `claude` | `claude` or `gemini` |
| `ACCOUNT_RESEARCH_CLAUDE_MODEL` | `claude-fable-5-1` | Bare first-party id; `claude-opus-5` is the drop-in alternative |
| `ACCOUNT_RESEARCH_CLAUDE_EFFORT` | unset (`high`) | `low` … `max`; ADK's `AnthropicGenerateContentConfig` |
| `ACCOUNT_RESEARCH_MAX_TOKENS` | `16000` | Output cap per model call |
| `GOOGLE_CLOUD_LOCATION` | `global` | Claude accepts `global`; Gemini wants a region |

Two things to know on Claude Fable 5.1: thinking is always on (ADK sends no
`thinking` parameter, which is the correct configuration for it), and a safety
decline comes back as `stop_reason: "refusal"`, which ADK maps to a `SAFETY`
finish -- the run stops there, because Vertex has no server-side fallback
model. Fable 5.1 also requires 30-day data retention on the org.

## Run

```bash
adk run account_research      # CLI
adk web .                     # dev UI; pick account_research in the dropdown
```

Example: *"Research Northwind Analytics"* or *"northwind-analytics.com"*.
If several ledger accounts match, it lists them and asks which.

## Serve it as an API (Cloud Run)

`main.py` wraps the agent with ADK's `get_fast_api_app` -- the same FastAPI +
uvicorn shape as a plain web service, listening on `$PORT` (8080):

```bash
python main.py                 # http://0.0.0.0:8080 ; /healthz, /list-apps, /dev-ui/
adk deploy cloud_run --project=$GOOGLE_CLOUD_PROJECT --region=$GOOGLE_CLOUD_LOCATION .
```

Set `SESSION_SERVICE_URI` to a Postgres or Agent Engine URI in production;
the default is a local SQLite file.

## Observability

Agent tracing is off by default. Turn it on and ADK sends spans for the whole
run -- each sub-agent transfer, tool call and model call -- to Cloud Trace:

```bash
uv sync --extra trace                                # the Cloud Trace exporter
ACCOUNT_RESEARCH_TRACE_TO_CLOUD=1 python main.py     # or adk web .
ACCOUNT_RESEARCH_ENABLE_TRACING=1 python deployment/deploy.py --create
```

The exporter is an optional extra, so the flags without it stop with the
install command rather than a `ModuleNotFoundError` from inside ADK. The
running identity needs `roles/cloudtrace.agent`, and Application Default
Credentials must be present — `ACCOUNT_RESEARCH_OTEL_TO_CLOUD` builds its
exporter eagerly and cannot start without them (`trace_to_cloud` alone only
warns and runs untraced).

### Request/response logging to BigQuery

Separately from tracing, Vertex can mirror the actual prompts and completions
into a BigQuery table. Claude **is** supported -- models served through
`rawPredict`/`streamRawPredict` under the `anthropic` publisher.

Vertex has three request/response logging surfaces, and Google's docs show
recipes for all of them. Only the third applies here:

| Surface | Configured with | Terraform | Works for Claude |
|---|---|---|---|
| Gemini publisher model | `GenerativeModel("gemini-2.5-flash").set_request_response_logging_config(...)` | no | **No** — a Gemini class; Claude never goes through it |
| Deployed endpoint (tuned / custom model) | `GenerativeModel(".../endpoints/ID")…`, or `google_vertex_ai_endpoint` → `predict_request_response_logging_config` | **yes** | **No** — Claude is a publisher model, not something you deploy to an endpoint |
| Anthropic publisher model | REST `setPublisherModelConfig` | no | **Yes** |

So the one surface Terraform can express is the one that does not cover Claude;
that gap is
[terraform-provider-google#24092](https://github.com/hashicorp/terraform-provider-google/issues/24092),
open and unimplemented. Hence a script:

The dataset can be created by hand, or managed in HCP Terraform — see
[`terraform/`](../../../terraform/) at the repo root, which also grants Vertex
write access to it and prints the enable command as an output.

```bash
bq mk --dataset --location=US "$GOOGLE_CLOUD_PROJECT:crm"   # if it doesn't exist

python scripts/claude_request_logging.py --show
python scripts/claude_request_logging.py --enable --dataset crm --table claude_logs
python scripts/claude_request_logging.py --enable --dataset crm --dry-run   # inspect first
python scripts/claude_request_logging.py --disable
```

It targets whatever `ACCOUNT_RESEARCH_CLAUDE_MODEL` names, at
`GOOGLE_CLOUD_LOCATION` (`global` uses `aiplatform.googleapis.com`, a region
uses `<region>-aiplatform.googleapis.com`). `--sampling-rate` takes a fraction
in (0,1]; `--otel` adds OpenTelemetry logs.

The rows contain prompts and completions — the contact data the agent reads
and the briefs it writes. Choose the dataset's region, access and retention
deliberately before turning this on.

**Tracing and logging are different things.** Tracing gives you spans -- what
ran, in what order, how long. Logging gives you payloads. Note also that the
Gemini recipe for logging (`GenerativeModel.set_request_response_logging_config`)
configures a *Gemini* class the agent never touches; use the script above for
Claude.

## Tests

```bash
python -m pytest tests -q
```

The ledger tools are pure Python and are tested without ADK or credentials;
the same tests run in the repo's Python CI.

## Deploy to Agent Runtime

Identical to the template: grant the Reasoning Engine service agent BigQuery
User and Data Viewer, then

```bash
uv build --wheel --out-dir=deployment
cd deployment && python3 deploy.py --create
python test_deployment.py --resource_id=$RESOURCE_ID --user_id=me
```
