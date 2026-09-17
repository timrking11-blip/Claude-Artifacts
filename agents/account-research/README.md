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
| Model | Gemini on Vertex AI (`GOOGLE_GENAI_MODEL`, default `gemini-2.5-flash`) |

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
cd agents/account-research
cp .env-example .env          # fill in project, location, bucket
set -o allexport; . .env; set +o allexport

curl -LsSf https://astral.sh/uv/install.sh | sh    # once
uv sync --dev
```

The ledger tools read `../../data/master/contacts.json` by default; set
`ACCOUNT_RESEARCH_LEDGER` to point elsewhere.

**BigQuery (optional, for the warehouse step and the `gcp-bigquery` MCP server):**

```bash
cd deployment
python bigquery_setup.py --project_id=$GOOGLE_CLOUD_PROJECT \
    --dataset_id=$GOOGLE_CLOUD_BQ_DATASET --location=$GOOGLE_CLOUD_LOCATION
```

**MCP tools (optional):** set `ACCOUNT_RESEARCH_ENABLE_MCP=1` and have
Application Default Credentials available (`gcloud auth application-default login`).
The agent then attaches the BigQuery and Agent Registry MCP servers for
project `922106495655` as tools. With it off, the warehouse step is skipped
and everything else works.

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
