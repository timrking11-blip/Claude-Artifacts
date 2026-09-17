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

AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "0.0.0.0")

app = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    # Local SQLite session store next to the agent; swap for a
    # postgresql:// or agentengine:// URI in production.
    session_service_uri=os.getenv("SESSION_SERVICE_URI", "sqlite:///./sessions.db"),
    allow_origins=os.getenv("ALLOW_ORIGINS", "*").split(","),
    web=os.getenv("SERVE_WEB_UI", "1") == "1",
    host=HOST,
    port=PORT,
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "agent": "account_research"}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
