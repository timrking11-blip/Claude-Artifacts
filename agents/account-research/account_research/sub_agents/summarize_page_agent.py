"""Summarize a fetched web page. Wrapped as an AgentTool by research_agent."""

from google.adk.agents import Agent

from ..model import GENERATE_CONFIG, MODEL
from ..shared_libraries.callbacks import rate_limit_callback
from . import summarize_page_agent_prompt

SummarizePageAgent = Agent(
    model=MODEL,
    name="summarize_page_agent",
    description="Summarize the web page most recently fetched into state.",
    instruction=summarize_page_agent_prompt.PROMPT,
    output_key="website_summary",
    generate_content_config=GENERATE_CONFIG,
    before_model_callback=rate_limit_callback,
)
