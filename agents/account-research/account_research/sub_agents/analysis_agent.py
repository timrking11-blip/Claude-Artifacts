"""Analysis sub-agent: turns the research into an account brief."""

from google.adk.agents import Agent

from .. import MODEL
from ..shared_libraries.callbacks import rate_limit_callback
from . import analysis_agent_prompt

AnalysisAgent = Agent(
    model=MODEL,
    name="analysis_agent",
    description="Write the account brief from the gathered research.",
    instruction=analysis_agent_prompt.PROMPT,
    before_model_callback=rate_limit_callback,
)
