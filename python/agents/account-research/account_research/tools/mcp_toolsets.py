"""Google Cloud MCP servers (BigQuery, Agent Registry) as ADK toolsets.

These are the same servers registered in the repo's .mcp.json, here attached
to research_agent as tools. They are attached only when
ACCOUNT_RESEARCH_ENABLE_MCP is truthy AND Application Default Credentials are
available; otherwise `google_cloud_toolsets()` returns [] and the agent runs
without them. That keeps `import account_research.agent` working in tests,
CI and on machines without gcloud.

Auth follows Google's generic-client recipe -- a bearer access token plus the
x-goog-user-project quota header -- but through ADK's `header_provider`, so
the token is refreshed per request rather than pasted once and left to expire.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from google.adk.agents.readonly_context import ReadonlyContext

logger = logging.getLogger(__name__)

# The x-goog-user-project quota header. Google accepts either the project
# number or the ID, so GOOGLE_CLOUD_PROJECT works as the last fallback and
# most setups need nothing else. No default: a hardcoded project would send
# someone else's quota header from a fork of this repo.
PROJECT = (
    os.getenv("GCP_PROJECT")
    or os.getenv("GOOGLE_CLOUD_PROJECT_NUMBER")
    or os.getenv("GOOGLE_CLOUD_PROJECT")
    or ""
)

SERVERS = {
    "bigquery": "https://bigquery.googleapis.com/mcp",
    "agentregistry": "https://agentregistry.googleapis.com/mcp",
}

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def enabled() -> bool:
    return os.getenv("ACCOUNT_RESEARCH_ENABLE_MCP", "0").strip().lower() in ("1", "true", "yes")


def _header_provider() -> Callable[["ReadonlyContext"], dict[str, str]]:
    """Build a per-request header callable backed by refreshable ADC."""
    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(scopes=SCOPES)
    transport = google.auth.transport.requests.Request()

    def provide(_context: "ReadonlyContext") -> dict[str, str]:
        if not credentials.valid:
            credentials.refresh(transport)
        return {
            "Authorization": f"Bearer {credentials.token}",
            "x-goog-user-project": PROJECT,
        }

    return provide


def google_cloud_toolsets() -> list[Any]:
    """The MCP toolsets to attach, or [] when disabled or not authenticated."""
    if not enabled():
        logger.info("Google Cloud MCP toolsets off (ACCOUNT_RESEARCH_ENABLE_MCP unset)")
        return []
    if not PROJECT:
        logger.warning(
            "Google Cloud MCP toolsets disabled: no project for the "
            "x-goog-user-project header. Set GOOGLE_CLOUD_PROJECT (or "
            "GOOGLE_CLOUD_PROJECT_NUMBER) before importing the agent."
        )
        return []
    try:
        from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

        provide = _header_provider()
    except Exception as exc:  # noqa: BLE001 - missing mcp lib or no ADC: run without
        logger.warning("Google Cloud MCP toolsets disabled: %s", exc)
        return []

    toolsets = []
    for name, url in SERVERS.items():
        toolsets.append(
            McpToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url=url,
                    headers={"x-goog-user-project": PROJECT},
                ),
                header_provider=provide,
                tool_name_prefix=name,
            )
        )
    logger.info("attached Google Cloud MCP toolsets: %s", list(SERVERS))
    return toolsets
