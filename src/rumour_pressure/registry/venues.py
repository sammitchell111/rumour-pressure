"""Search and fetch markets on Polymarket, Kalshi and Manifold.

Parsers are pure (dict in, model out) and tested against recorded fixtures; the
`search_*` / `fetch_*` functions wrap them with network calls.
"""

import json
import logging
import re
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from rumour_pressure import config
from rumour_pressure.http import get_json
from rumour_pressure.registry import RegistryMarket
from rumour_pressure.store.models import UtcDatetime, Venue

log = logging.getLogger(__name__)

MANIFOLD_API = "https://api.manifold.markets/v0"
POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_EVENTS_CACHE_HOURS = 24


class Candidate(BaseModel):
    venue: Venue
    ref: str
    question: str
    url: str
    kind: str = "BINARY"
    close_time: UtcDatetime | None = None
    closed: bool = False
    volume: float | None = None


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _ms(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value / 1000, tz=UTC) if value else None


def mentions_any(question: str, entities: Iterable[str]) -> bool:
    """True if the question contains any entity phrase as whole words (case-insensitive)."""
    return any(
        re.search(rf"(?<!\w){re.escape(e)}(?!\w)", question, re.IGNORECASE) for e in entities
    )


# --- Manifold -----------------------------------------------------------------------


def parse_manifold_search(results: list[dict[str, Any]]) -> list[Candidate]:
    return [
        Candidate(
            venue="manifold",
            ref=r["id"],
            question=r["question"],
            url=r["url"],
            kind=r.get("outcomeType", "?"),
            close_time=_ms(r.get("closeTime")) if (r.get("closeTime") or 0) < 1e14 else None,
            closed=bool(r.get("isResolved")),
            volume=r.get("volume"),
        )
        for r in results
    ]


def parse_manifold_market(m: dict[str, Any], group: str) -> RegistryMarket:
    return RegistryMarket(
        market_id=f"manifold:{m['id']}",
        venue="manifold",
        venue_ref={"id": m["id"], "slug": m.get("slug")},
        group=group,
        question=m["question"],
        resolution_text=(m.get("textDescription") or m["question"]).strip(),
        url=m["url"],
        close_time=_ms(m.get("closeTime")) if (m.get("closeTime") or 0) < 1e14 else None,
        closed=bool(m.get("isResolved")),
    )


def search_manifold(term: str) -> list[Candidate]:
    results = get_json(
        "manifold", f"{MANIFOLD_API}/search-markets", {"term": term, "filter": "all", "limit": 500}
    )
    return parse_manifold_search(results)


def fetch_manifold(ref: str, group: str) -> RegistryMarket:
    return parse_manifold_market(get_json("manifold", f"{MANIFOLD_API}/market/{ref}"), group)


# --- Polymarket ---------------------------------------------------------------------


def parse_polymarket_search(data: dict[str, Any]) -> list[Candidate]:
    out = []
    for event in data.get("events", []):
        for m in event.get("markets", []):
            out.append(
                Candidate(
                    venue="polymarket",
                    ref=str(m["id"]),
                    question=m.get("question") or event.get("title", ""),
                    url=f"https://polymarket.com/event/{event.get('slug', '')}",
                    close_time=_iso(m.get("endDate")),
                    closed=bool(m.get("closed")),
                    volume=float(m.get("volume") or 0),
                )
            )
    return out


def parse_polymarket_market(m: dict[str, Any], group: str) -> RegistryMarket:
    token_ids = m.get("clobTokenIds") or "[]"
    if isinstance(token_ids, str):
        token_ids = json.loads(token_ids)
    events = m.get("events") or [{}]
    slug = events[0].get("slug") or m.get("slug", "")
    return RegistryMarket(
        market_id=f"polymarket:{m['id']}",
        venue="polymarket",
        venue_ref={
            "id": str(m["id"]),
            "condition_id": m.get("conditionId"),
            "clob_token_ids": token_ids,  # [YES, NO]
            "slug": m.get("slug"),
        },
        group=group,
        question=m["question"],
        resolution_text=(m.get("description") or "").strip(),
        url=f"https://polymarket.com/event/{slug}",
        close_time=_iso(m.get("endDate")),
        closed=bool(m.get("closed")),
    )


def search_polymarket(term: str) -> list[Candidate]:
    data = get_json(
        "polymarket",
        f"{POLYMARKET_GAMMA}/public-search",
        {"q": term, "limit_per_type": 50, "keep_closed_markets": 1},
    )
    return parse_polymarket_search(data)


def fetch_polymarket(ref: str, group: str) -> RegistryMarket:
    return parse_polymarket_market(
        get_json("polymarket", f"{POLYMARKET_GAMMA}/markets/{ref}"), group
    )


# --- Kalshi ---------------------------------------------------------------------------


def parse_kalshi_events(data: dict[str, Any]) -> list[Candidate]:
    out = []
    for event in data.get("events", []):
        for m in event.get("markets", []):
            label = m.get("yes_sub_title") or ""
            out.append(
                Candidate(
                    venue="kalshi",
                    ref=m["ticker"],
                    question=f"{event.get('title', '')} :: {label}".strip(" :"),
                    url=f"https://kalshi.com/markets/{event.get('series_ticker', '').lower()}",
                    close_time=_iso(m.get("close_time")),
                    closed=m.get("status") not in (None, "active", "open", "initialized"),
                    volume=float(m.get("volume_fp") or m.get("volume") or 0),
                )
            )
    return out


def parse_kalshi_market(data: dict[str, Any], group: str) -> RegistryMarket:
    m = data["market"]
    rules = "\n\n".join(r for r in (m.get("rules_primary"), m.get("rules_secondary")) if r)
    series = m["event_ticker"].split("-")[0].lower()
    return RegistryMarket(
        market_id=f"kalshi:{m['ticker']}",
        venue="kalshi",
        venue_ref={"ticker": m["ticker"], "event_ticker": m["event_ticker"], "series": series},
        group=group,
        question=m.get("title") or m["ticker"],
        resolution_text=rules.strip(),
        url=f"https://kalshi.com/markets/{series}",
        close_time=_iso(m.get("close_time")),
        closed=m.get("status") not in (None, "active", "open", "initialized"),
    )


def _kalshi_open_events() -> dict[str, Any]:
    """All open Kalshi events with nested markets. Kalshi has no text search, so we scan,
    caching the result for a day (a full scan is ~80 pages)."""
    cache = config.raw_cache_dir("kalshi") / "open_events.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < KALSHI_EVENTS_CACHE_HOURS * 3600:
        return json.loads(cache.read_text())
    events, cursor = [], None
    while True:
        params = {"status": "open", "limit": 200, "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        page = get_json("kalshi", f"{KALSHI_API}/events", params)
        events += page.get("events", [])
        cursor = page.get("cursor")
        log.info("kalshi: %d events scanned", len(events))
        if not cursor:
            break
    # Keep only what the finder reads: the raw scan is ~400 MB, this is a few MB.
    market_keys = ("ticker", "yes_sub_title", "close_time", "status", "volume_fp", "volume")
    data = {
        "events": [
            {
                "title": e.get("title"),
                "series_ticker": e.get("series_ticker"),
                "markets": [{k: m.get(k) for k in market_keys} for m in e.get("markets", [])],
            }
            for e in events
        ]
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    return data


def search_kalshi(term: str) -> list[Candidate]:
    return parse_kalshi_events(_kalshi_open_events())


def fetch_kalshi(ref: str, group: str) -> RegistryMarket:
    return parse_kalshi_market(get_json("kalshi", f"{KALSHI_API}/markets/{ref}"), group)


# --- dispatch -------------------------------------------------------------------------

SEARCH = {"manifold": search_manifold, "polymarket": search_polymarket, "kalshi": search_kalshi}
FETCH = {"manifold": fetch_manifold, "polymarket": fetch_polymarket, "kalshi": fetch_kalshi}


def find(entities: list[str], venues: Iterable[str] = SEARCH) -> list[Candidate]:
    """Candidates on each venue whose question names any of `entities`, deduplicated."""
    found: dict[tuple[str, str], Candidate] = {}
    for venue in venues:
        for term in entities:
            try:
                results = SEARCH[venue](term)
            except Exception as exc:  # one venue failing shouldn't hide the others
                log.error("%s search failed: %s", venue, exc)
                break
            for c in results:
                if mentions_any(c.question, entities):
                    found[(c.venue, c.ref)] = c
            if venue == "kalshi":
                break  # Kalshi search is a full scan; one pass covers every term
    return list(found.values())
