"""Initialization for the Account Research agent.

Modelled on google/adk-samples `fomc-research`: resolve the Google Cloud
project from Application Default Credentials, set the Vertex backend, pick the
model, then import the agent graph.
"""

import logging
import os

# The ledger tools and their tests run without any Google credentials, so a
# missing ADC must not make the package unimportable. The agent itself needs
# ADC at run time; ADK reports that clearly on the first model call.
try:
    import google.auth

    _, _project_id = google.auth.default()
    if _project_id:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _project_id)
except Exception:  # noqa: BLE001 - any auth failure means "not configured"
    pass

os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

loglevel = os.getenv("ACCOUNT_RESEARCH_LOG_LEVEL", "INFO")
numeric_level = getattr(logging, loglevel.upper(), None)
if not isinstance(numeric_level, int):
    raise ValueError(f"Invalid log level: {loglevel}")
logger = logging.getLogger(__package__)
logger.setLevel(numeric_level)

MODEL = os.getenv("GOOGLE_GENAI_MODEL") or "gemini-2.5-flash"
