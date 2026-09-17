"""Which model the agents run on. Imported by the agents, never by the tools.

Selecting the provider here rather than in the package __init__ keeps
`account_research.tools.*` importable with nothing but the standard library,
which is what lets the ledger tools test without ADK, credentials or network.
"""

import os

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
