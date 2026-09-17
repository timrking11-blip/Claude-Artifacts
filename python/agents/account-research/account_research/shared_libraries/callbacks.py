"""Callback functions for the Account Research agent."""

import logging
import time

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest

logger = logging.getLogger(__name__)

RATE_LIMIT_SECS = 60
RPM_QUOTA = 1000


def rate_limit_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    """Throttle model calls to RPM_QUOTA per RATE_LIMIT_SECS.

    Mirrors the fomc-research sample: minimizes 429 Resource Exhausted errors
    from Vertex on long multi-agent runs.
    """
    now = time.time()
    if "timer_start" not in callback_context.state:
        callback_context.state["timer_start"] = now
        callback_context.state["request_count"] = 1
        return

    request_count = callback_context.state["request_count"] + 1
    elapsed_secs = now - callback_context.state["timer_start"]

    if request_count > RPM_QUOTA:
        delay = RATE_LIMIT_SECS - elapsed_secs + 1
        if delay > 0:
            logger.debug("rate limit: sleeping %i seconds", delay)
            time.sleep(delay)
        callback_context.state["timer_start"] = now
        callback_context.state["request_count"] = 1
    else:
        callback_context.state["request_count"] = request_count
