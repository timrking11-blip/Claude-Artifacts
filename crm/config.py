"""Single source of truth for endpoints, credentials and sync tunables.

Everything the pipeline talks to is named here exactly once. If an endpoint
moves, this is the only file that changes.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Endpoints -------------------------------------------------------------

# The Mintlify-hosted Explorium *documentation* MCP. Read-only; no credentials.
# NOTE: this URL follows Mintlify's `<docs-host>/mcp` convention and was not
# reachable from the environment this repo was scaffolded in (egress blocked),
# so it is unverified. If `explorium-docs` fails to connect, correct it here
# and in .mcp.json -- those are the only two places it appears.
EXPLORIUM_DOCS_MCP_URL = os.environ.get(
    "EXPLORIUM_DOCS_MCP_URL", "https://developers.explorium.ai/mcp"
)

# The Explorium AgentSource *data* MCP. Separate server, separate host.
EXPLORIUM_AGENTSOURCE_MCP_URL = os.environ.get(
    "EXPLORIUM_AGENTSOURCE_MCP_URL", "https://mcp.explorium.ai/mcp"
)

APOLLO_API_BASE = os.environ.get("APOLLO_API_BASE", "https://api.apollo.io/api/v1")
EXPLORIUM_API_BASE = os.environ.get(
    "EXPLORIUM_API_BASE", "https://api.explorium.ai/v1"
)

# --- Credentials -----------------------------------------------------------

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")
EXPLORIUM_API_KEY = os.environ.get("EXPLORIUM_API_KEY", "")

# --- Paths -----------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
STAGING_DIR = DATA_DIR / "staging"
MASTER_DIR = DATA_DIR / "master"
MASTER_CONTACTS = MASTER_DIR / "contacts.json"
CHANGELOG = DATA_DIR / "CHANGELOG.md"

APOLLO_STAGING = STAGING_DIR / "apollo.json"
EXPLORIUM_STAGING = STAGING_DIR / "explorium.json"

# --- Sync tunables ---------------------------------------------------------

# Apollo caps search at 100 records/page, 500 pages.
APOLLO_PAGE_SIZE = 100
APOLLO_MAX_PAGES = int(os.environ.get("APOLLO_MAX_PAGES", "50"))

# Explorium enrichment is batched; keep batches modest so a failure costs little.
EXPLORIUM_BATCH_SIZE = 50

# Writes back to Apollo mutate the user's CRM and can spend credits, so the
# pipeline refuses to do it unless this is explicitly turned on.
APOLLO_WRITEBACK_ENABLED = (
    os.environ.get("APOLLO_WRITEBACK_ENABLED", "false").lower() == "true"
)

REQUEST_TIMEOUT = 30
MAX_RETRIES = 4
