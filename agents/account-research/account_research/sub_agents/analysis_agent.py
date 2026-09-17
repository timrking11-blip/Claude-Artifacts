"""Analysis sub-agent: turns the research into an account brief."""

from google.adk.agents import Agent

from ..model import GENERATE_CONFIG, MODEL
from ..shared_libraries.callbacks import rate_limit_callback
from . import analysis_agent_prompt

AnalysisAgent = Agent(
    model=MODEL,
    name="analysis_agent",
    description="Write the account brief from the gathered research.",
    instruction=analysis_agent_prompt.PROMPT,
    generate_content_config=GENERATE_CONFIG,
    before_model_callback=rate_limit_callback,
)
