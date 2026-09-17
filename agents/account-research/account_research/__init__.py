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

# --- Model provider ---------------------------------------------------------
# "claude": Claude served from Vertex AI through ADK's `Claude` wrapper, which
#           builds an AsyncAnthropicVertex client from GOOGLE_CLOUD_PROJECT and
#           GOOGLE_CLOUD_LOCATION (Claude accepts "global") and authenticates
#           with Application Default Credentials. Needs `anthropic[vertex]`.
# "gemini": the template's behaviour -- a Gemini model name on Vertex.
# Every agent imports MODEL (and GENERATE_CONFIG) from here, so this is the
# only place the provider is chosen.
PROVIDER = os.getenv("ACCOUNT_RESEARCH_MODEL_PROVIDER", "claude").strip().lower()
GENERATE_CONFIG = None

if PROVIDER == "claude":
    try:
        from google.adk.models.anthropic_llm import (
            AnthropicGenerateContentConfig,
            Claude,
        )
    except ImportError as exc:  # the wrapper imports the Anthropic SDK
        raise ImportError(
            "ACCOUNT_RESEARCH_MODEL_PROVIDER=claude needs the Anthropic SDK with "
            "Vertex support: pip install 'anthropic[vertex]' (or uv sync). "
            "Set ACCOUNT_RESEARCH_MODEL_PROVIDER=gemini to run without it."
        ) from exc

    MODEL = Claude(
        model=os.getenv("ACCOUNT_RESEARCH_CLAUDE_MODEL", "claude-fable-5-1"),
        # Non-streaming default from the Claude API guidance; the wrapper's
        # own default is 8192, which is tight for a two-page brief.
        max_tokens=int(os.getenv("ACCOUNT_RESEARCH_MAX_TOKENS", "16000")),
    )
    # Claude's five effort levels are set through this config, not the
    # standard thinking_level. Unset means the API default ("high").
    _effort = os.getenv("ACCOUNT_RESEARCH_CLAUDE_EFFORT", "").strip().lower()
    if _effort:
        GENERATE_CONFIG = AnthropicGenerateContentConfig(effort=_effort)
elif PROVIDER == "gemini":
    MODEL = os.getenv("GOOGLE_GENAI_MODEL") or "gemini-2.5-flash"
else:
    raise ValueError(
        f"ACCOUNT_RESEARCH_MODEL_PROVIDER={PROVIDER!r}; expected 'claude' or 'gemini'"
    )


def model_name() -> str:
    """The model id in use, whichever provider is active."""
    return getattr(MODEL, "model", MODEL)
