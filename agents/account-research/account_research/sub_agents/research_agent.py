"""Research coordinator for the Account Research agent."""

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

from .. import MODEL
from ..shared_libraries.callbacks import rate_limit_callback
from ..tools.fetch_page import fetch_page_tool
from ..tools.ledger import assess_ledger_quality_tool, list_account_contacts_tool
from ..tools.mcp_toolsets import google_cloud_toolsets
from ..tools.store_state import store_state_tool
from . import research_agent_prompt
from .summarize_page_agent import SummarizePageAgent

ResearchAgent = Agent(
    model=MODEL,
    name="research_agent",
    description=(
        "Gather everything the ledger and the web know about the requested "
        "account, for the analysis agent."
    ),
    instruction=research_agent_prompt.PROMPT,
    tools=[
        store_state_tool,
        list_account_contacts_tool,
        assess_ledger_quality_tool,
        fetch_page_tool,
        AgentTool(SummarizePageAgent),
        # Google Cloud MCP servers (BigQuery, Agent Registry). Empty unless
        # ACCOUNT_RESEARCH_ENABLE_MCP=1 and credentials are available.
        *google_cloud_toolsets(),
    ],
    before_model_callback=rate_limit_callback,
)
