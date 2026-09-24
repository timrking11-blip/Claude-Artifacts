"""Prequalification sub-agent: turns the research into a proposal, and files it."""

from google.adk.agents import Agent

from ..model import GENERATE_CONFIG, MODEL
from ..shared_libraries.callbacks import rate_limit_callback
from ..tools.write_proposal import write_proposal_tool
from . import prequal_agent_prompt

PrequalAgent = Agent(
    model=MODEL,
    name="prequal_agent",
    description=(
        "Write a prequalification proposal in reply to an inbound request, "
        "from the gathered research, and save it to data/proposals/."
    ),
    instruction=prequal_agent_prompt.PROMPT,
    tools=[write_proposal_tool],
    generate_content_config=GENERATE_CONFIG,
    before_model_callback=rate_limit_callback,
)
