"""'fetch_page' tool: retrieve a web page as plain text into state."""

import html
import logging
import re
import urllib.error
import urllib.request

from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

# Enough for a homepage; keeps the summarize_page prompt well inside context.
MAX_CHARS = 20_000


def _to_text(markup: str) -> str:
    """Strip scripts, styles and tags; collapse whitespace."""
    markup = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", markup)
    markup = re.sub(r"(?s)<[^>]+>", " ", markup)
    text = html.unescape(markup)
    return re.sub(r"\s+", " ", text).strip()


def fetch_page_tool(url: str, tool_context: ToolContext) -> dict[str, str]:
    """Retrieves 'url', converts it to plain text, and stores it in state.

    Args:
      url: URL to fetch.
      tool_context: ToolContext object.

    Returns:
      A dict with "status" and (optional) "message" keys.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    logger.debug("Fetching page: %s", url)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        message = f"Failed to fetch page {url}: {err}"
        logger.error(message)
        return {"status": "ERROR", "message": message}
    text = _to_text(raw)[:MAX_CHARS]
    tool_context.state.update({"page_contents": text, "page_url": url})
    return {"status": "OK", "message": f"{len(text)} characters of text stored"}
