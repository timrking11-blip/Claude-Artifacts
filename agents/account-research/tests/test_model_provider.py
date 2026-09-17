"""The provider switch in account_research/model.py."""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _reload(monkeypatch, provider, **env):
    monkeypatch.setenv("ACCOUNT_RESEARCH_MODEL_PROVIDER", provider)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("account_research.model", None)
    return importlib.import_module("account_research.model")


def test_gemini_provider_is_a_plain_model_name(monkeypatch):
    pkg = _reload(monkeypatch, "gemini", GOOGLE_GENAI_MODEL="gemini-2.5-flash")
    assert pkg.MODEL == "gemini-2.5-flash"
    assert pkg.GENERATE_CONFIG is None
    assert pkg.model_name() == "gemini-2.5-flash"


def test_claude_provider_builds_the_vertex_wrapper(monkeypatch):
    pytest.importorskip("anthropic")
    from google.adk.models.anthropic_llm import Claude
    pkg = _reload(monkeypatch, "claude", ACCOUNT_RESEARCH_CLAUDE_MODEL="claude-opus-5",
                  ACCOUNT_RESEARCH_MAX_TOKENS="4096")
    assert isinstance(pkg.MODEL, Claude)
    assert pkg.MODEL.model == "claude-opus-5"
    assert pkg.MODEL.max_tokens == 4096
    assert pkg.model_name() == "claude-opus-5"


def test_claude_default_model_and_effort(monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.delenv("ACCOUNT_RESEARCH_CLAUDE_MODEL", raising=False)
    pkg = _reload(monkeypatch, "claude", ACCOUNT_RESEARCH_CLAUDE_EFFORT="xhigh")
    assert pkg.MODEL.model == "claude-fable-5-1"
    assert pkg.GENERATE_CONFIG is not None and pkg.GENERATE_CONFIG.effort == "xhigh"


def test_unknown_provider_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="expected 'claude' or 'gemini'"):
        _reload(monkeypatch, "llama")
