"""Minimal retrying JSON client over the stdlib.

Deliberately dependency-free: the weekly job then needs no install step, so a
transient PyPI outage can never be the reason a sync fails to run.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from crm import config

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"{status} from {url}: {body[:300]}")
        self.status = status
        self.body = body
        self.url = url


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """POST JSON, retrying transient failures with exponential backoff."""
    timeout = timeout or config.REQUEST_TIMEOUT
    body = json.dumps(payload).encode()
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    hdrs.update(headers or {})

    last_error: Exception | None = None
    for attempt in range(config.MAX_RETRIES):
        req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            if exc.code not in RETRYABLE_STATUS:
                # A 4xx that is not rate limiting is a bug in our request;
                # retrying just burns time and, on some endpoints, credits.
                raise HttpError(exc.code, detail, url) from exc
            last_error = HttpError(exc.code, detail, url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc

        if attempt < config.MAX_RETRIES - 1:
            delay = 2 ** (attempt + 1)
            log.warning("%s failed (%s); retrying in %ss", url, last_error, delay)
            time.sleep(delay)

    raise last_error if last_error else RuntimeError(f"{url} failed")
