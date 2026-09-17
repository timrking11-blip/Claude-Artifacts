"""Account Research agent: an account brief from the CRM master ledger."""

import logging
import warnings

from google.adk.agents import Agent

from . import GENERATE_CONFIG, MODEL, model_name, root_agent_prompt
from .shared_libraries.callbacks import rate_limit_callback
from .sub_agents.analysis_agent import AnalysisAgent
from .sub_agents.research_agent import ResearchAgent
from .tools.ledger import find_account_tool
from .tools.store_state import store_state_tool

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")

logger = logging.getLogger(__name__)
logger.debug("Using MODEL: %s", model_name())

root_agent = Agent(
    model=MODEL,
    name="root_agent",
    description=(
        "Resolve the account the user asks about against the CRM master "
        "ledger, then coordinate research and an account brief."
    ),
    instruction=root_agent_prompt.PROMPT,
    tools=[find_account_tool, store_state_tool],
    sub_agents=[
        ResearchAgent,
        AnalysisAgent,
    ],
    generate_content_config=GENERATE_CONFIG,
    before_model_callback=rate_limit_callback,
)
