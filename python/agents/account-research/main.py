"""Serve the Account Research agent as a FastAPI app.

The ADK equivalent of a bare FastAPI + uvicorn script: `get_fast_api_app`
mounts the agent's API (and, with web=True, the dev UI) on one app. This is
the entry point Cloud Run runs -- it listens on $PORT, default 8080.

    python main.py                       # local, http://0.0.0.0:8080
    adk deploy cloud_run --project=... --region=... .   # or let ADK build it

`adk web .` remains the quicker option for local development.
"""

import os

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app
from google.auth.exceptions import DefaultCredentialsError

AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "0.0.0.0")

# Observability. Off by default; tracing sends agent spans (sub-agent
# transfers, tool calls, model calls) to Cloud Trace. This is the ADK-native
# path and is provider-agnostic -- it covers Claude on Vertex, which Gemini's
# GenerativeModel.set_request_response_logging_config does not.
TRACE_TO_CLOUD = os.getenv("ACCOUNT_RESEARCH_TRACE_TO_CLOUD", "0").strip().lower() in ("1", "true", "yes")
OTEL_TO_CLOUD = os.getenv("ACCOUNT_RESEARCH_OTEL_TO_CLOUD", "0").strip().lower() in ("1", "true", "yes")

if TRACE_TO_CLOUD or OTEL_TO_CLOUD:
    try:  # ADK imports this lazily, deep in get_fast_api_app
        import opentelemetry.exporter.cloud_trace  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Tracing is enabled but the Cloud Trace exporter is not installed.\n"
            "  uv sync --extra trace      (or: pip install opentelemetry-exporter-gcp-trace)\n"
            "Or unset ACCOUNT_RESEARCH_TRACE_TO_CLOUD / ACCOUNT_RESEARCH_OTEL_TO_CLOUD."
        ) from None

try:
    app = get_fast_api_app(
        agents_dir=AGENTS_DIR,
        trace_to_cloud=TRACE_TO_CLOUD,
        otel_to_cloud=OTEL_TO_CLOUD,
        # Local SQLite session store next to the agent; swap for a
        # postgresql:// or agentengine:// URI in production.
        session_service_uri=os.getenv("SESSION_SERVICE_URI", "sqlite:///./sessions.db"),
        allow_origins=os.getenv("ALLOW_ORIGINS", "*").split(","),
        web=os.getenv("SERVE_WEB_UI", "1") == "1",
        host=HOST,
        port=PORT,
    )
except DefaultCredentialsError:
    # otel_to_cloud builds its exporter eagerly and needs credentials;
    # trace_to_cloud only warns. Either way, say so plainly.
    raise SystemExit(
        "Tracing is enabled but there are no Application Default Credentials.\n"
        "  gcloud auth application-default login\n"
        "Or unset ACCOUNT_RESEARCH_TRACE_TO_CLOUD / ACCOUNT_RESEARCH_OTEL_TO_CLOUD."
    ) from None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "agent": "account_research"}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
