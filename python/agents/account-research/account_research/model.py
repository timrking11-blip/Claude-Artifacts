"""Which model the agents run on. Imported by the agents, never by the tools.

Selecting the provider here rather than in the package __init__ keeps
`account_research.tools.*` importable with nothing but the standard library,
which is what lets the ledger tools test without ADK, credentials or network.
"""

import os

# --- Model provider ---------------------------------------------------------
# "anthropic" (default): Claude through the Anthropic API, via ADK's
#           `AnthropicLlm`. The SDK resolves the credential itself --
#           ANTHROPIC_API_KEY, or a profile from `ant auth login`. No Google
#           Cloud project, no ADC, no Vertex enablement. This is the path to
#           use while GCP is parked.
# "claude": the same model served from Vertex AI through ADK's `Claude`
#           subclass, which builds an AsyncAnthropicVertex client from
#           GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION and authenticates
#           with Application Default Credentials. Needs `anthropic[vertex]`.
# "gemini": the template's behaviour -- a Gemini model name on Vertex.
# Every agent imports MODEL (and GENERATE_CONFIG) from here, so this is the
# only place the provider is chosen.
PROVIDER = os.getenv("ACCOUNT_RESEARCH_MODEL_PROVIDER", "anthropic").strip().lower()
GENERATE_CONFIG = None

# Opus 5 is the default: a prequalification proposal from structured research
# does not need the Fable tier, and Opus is half the price per token. Set
# ACCOUNT_RESEARCH_CLAUDE_MODEL=claude-fable-5-1 to opt back in.
DEFAULT_CLAUDE_MODEL = "claude-opus-5"

if PROVIDER in ("anthropic", "claude"):
    try:
        from google.adk.models.anthropic_llm import (
            AnthropicGenerateContentConfig,
            AnthropicLlm,
            Claude,
        )
    except ImportError as exc:  # the wrapper imports the Anthropic SDK
        raise ImportError(
            f"ACCOUNT_RESEARCH_MODEL_PROVIDER={PROVIDER} needs the Anthropic SDK: "
            "pip install anthropic (or 'anthropic[vertex]' for the claude provider; "
            "or uv sync). Set ACCOUNT_RESEARCH_MODEL_PROVIDER=gemini to run without it."
        ) from exc

    # AnthropicLlm -> Anthropic API. Claude -> Vertex. Same request shape,
    # same model ids; only the client and its credential differ.
    _cls = AnthropicLlm if PROVIDER == "anthropic" else Claude
    MODEL = _cls(
        model=os.getenv("ACCOUNT_RESEARCH_CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL),
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
        f"ACCOUNT_RESEARCH_MODEL_PROVIDER={PROVIDER!r}; expected 'anthropic', 'claude' or 'gemini'"
    )


def model_name() -> str:
    """The model id in use, whichever provider is active."""
    return getattr(MODEL, "model", MODEL)
