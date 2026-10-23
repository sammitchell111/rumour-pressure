"""Polymarket prices: hourly price history (complete) + trade log (volume; capped depth).

The price-history endpoint returns a full hourly series when given only a start time; its
`interval=max` form returns nothing for resolved markets. The public trade log pages to
roughly 10,000 trades, so on big markets early hours get volume = None (unknown).
Wallet addresses and profile fields are never kept.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from rumour_pressure.collect.prices import Trade, cached, hour, merge_history_with_trades
from rumour_pressure.http import get_json
from rumour_pressure.registry import RegistryMarket
from rumour_pressure.store.models import PriceRow

log = logging.getLogger(__name__)

CLOB = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
TRADE_PAGE = 500
TRADE_FIELDS = ("asset", "side", "size", "price", "timestamp", "outcome", "transactionHash")
HISTORY_START_TS = 1_500_000_000  # before Polymarket existed: "from the beginning"


def parse_history(data: dict[str, Any]) -> list[tuple[datetime, float]]:
    return [
        (datetime.fromtimestamp(p["t"], tz=UTC), float(p["p"])) for p in data.get("history", [])
    ]


def parse_trades(trades: list[dict[str, Any]], yes_token: str) -> list[Trade]:
    """A NO-token trade at price p means the YES price is 1 - p."""
    return [
        Trade(
            ts=datetime.fromtimestamp(t["timestamp"], tz=UTC),
            price=float(t["price"]) if t["asset"] == yes_token else 1 - float(t["price"]),
            size=float(t["size"]),
        )
        for t in trades
    ]


def fetch_history(yes_token: str) -> dict[str, Any]:
    return get_json(
        "polymarket",
        f"{CLOB}/prices-history",
        {"market": yes_token, "startTs": HISTORY_START_TS, "fidelity": 60},
    )


def fetch_trades(condition_id: str) -> dict[str, Any]:
    """Newest-first trades until the API's offset cap. Returns trades + whether complete."""
    trades: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "market": condition_id,
            "limit": TRADE_PAGE,
            "offset": offset,
            "takerOnly": "false",
        }
        try:
            page = get_json("polymarket", f"{DATA_API}/trades", params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:  # offset cap reached
                return {"trades": trades, "complete": False}
            raise
        trades += [{k: t.get(k) for k in TRADE_FIELDS} for t in page]
        if len(page) < TRADE_PAGE:
            return {"trades": trades, "complete": True}
        offset += TRADE_PAGE


def collect_prices(market: RegistryMarket) -> list[PriceRow]:
    ref = market.venue_ref
    yes_token = ref["clob_token_ids"][0]
    key = ref["id"]
    history = cached(
        "polymarket", f"history_{key}", lambda: fetch_history(yes_token), market.closed
    )
    log_ = cached(
        "polymarket", f"trades_{key}", lambda: fetch_trades(ref["condition_id"]), market.closed
    )
    trades = parse_trades(log_["trades"], yes_token)
    points = parse_history(history)
    if log_["complete"]:
        reach = min((p[0] for p in points), default=None)
    else:
        oldest = min((t.ts for t in trades), default=None)
        # The oldest hour in a capped log may be partial, so volume is known from the next.
        reach = hour(oldest) + timedelta(hours=1) if oldest else None
    rows = merge_history_with_trades(market.market_id, points, trades, reach)
    log.info(
        "polymarket %s: %d history points, %d trades (%s) -> %d hourly bars",
        key,
        len(points),
        len(trades),
        "complete" if log_["complete"] else "capped",
        len(rows),
    )
    return rows
