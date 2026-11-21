"""HTTP fetching with transient retries/backoff and HTML text cleanup."""
from __future__ import annotations

import html
import json
import re
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
DEFAULT_HEADERS = {
    "User-Agent": "PersonalJobApplicant/1.0",
    "Accept": "application/json",
}


def _retry_delay(exc: Exception, attempt: int, backoff_base: float) -> float:
    if isinstance(exc, HTTPError) and exc.headers:
        retry_after = exc.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 10.0))
            except ValueError:
                pass
    return backoff_base * (2 ** attempt)


def get_json(
    url: str,
    *,
    timeout: int = 30,
    retries: int = 2,
    backoff_base: float = 0.5,
    urlopen_fn: Callable[..., Any] = urlopen,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Any:
    """Fetch JSON over HTTPS with bounded exponential backoff on transient failures."""
    request = Request(url, headers=DEFAULT_HEADERS)
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen_fn(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            last_exc = exc
            if exc.code not in RETRYABLE_HTTP_CODES or attempt >= retries:
                raise
            sleep_fn(_retry_delay(exc, attempt, backoff_base))
        except (URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt >= retries:
                raise
            sleep_fn(_retry_delay(exc, attempt, backoff_base))
    assert last_exc is not None
    raise last_exc


def plain_text(value: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(value or "")))
