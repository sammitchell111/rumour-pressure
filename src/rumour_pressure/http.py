"""Polite HTTP: per-source rate limits, retries on 429/5xx, a descriptive User-Agent."""

import logging
import time
from typing import Any

import httpx

from rumour_pressure import config

log = logging.getLogger(__name__)

MAX_RETRIES = 5
_last_call: dict[str, float] = {}
_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            headers={"User-Agent": config.USER_AGENT}, timeout=30.0, follow_redirects=True
        )
    return _client


def _wait_turn(source: str) -> None:
    min_gap = getattr(config.RATE_LIMITS, source, 0.0)
    elapsed = time.monotonic() - _last_call.get(source, 0.0)
    if elapsed < min_gap:
        time.sleep(min_gap - elapsed)
    _last_call[source] = time.monotonic()


def get_json(source: str, url: str, params: dict[str, Any] | None = None) -> Any:
    """GET a JSON endpoint, respecting `source`'s rate limit and backing off when asked."""
    for attempt in range(MAX_RETRIES):
        _wait_turn(source)
        resp = client().get(url, params=params)
        if resp.status_code == 429 or resp.status_code >= 500:
            delay = float(resp.headers.get("Retry-After") or 2**attempt * 2)
            log.warning("%s %s -> %s; retrying in %.0fs", source, url, resp.status_code, delay)
            time.sleep(delay)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"{source}: gave up on {url} after {MAX_RETRIES} attempts")
