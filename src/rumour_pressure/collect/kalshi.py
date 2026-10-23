"""Kalshi prices from the public trade log (cursor-paged; no user identifiers)."""

import logging
from datetime import datetime
from typing import Any

from rumour_pressure.collect.prices import Trade, cached, hourly_bars
from rumour_pressure.http import get_json
from rumour_pressure.registry import RegistryMarket
from rumour_pressure.store.models import PriceRow

log = logging.getLogger(__name__)

API = "https://api.elections.kalshi.com/trade-api/v2"
PAGE = 1000


def parse_trades(trades: list[dict[str, Any]]) -> list[Trade]:
    return [
        Trade(
            ts=datetime.fromisoformat(t["created_time"].replace("Z", "+00:00")),
            price=float(t["yes_price_dollars"]),
            size=float(t.get("count_fp") or t.get("count") or 0),
        )
        for t in trades
    ]


def fetch_trades(ticker: str) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"ticker": ticker, "limit": PAGE}
        if cursor:
            params["cursor"] = cursor
        page = get_json("kalshi", f"{API}/markets/trades", params)
        trades += page.get("trades", [])
        cursor = page.get("cursor")
        if not cursor or not page.get("trades"):
            return trades


def collect_prices(market: RegistryMarket) -> list[PriceRow]:
    ticker = market.venue_ref["ticker"]
    raw = cached("kalshi", f"trades_{ticker}", lambda: fetch_trades(ticker), market.closed)
    rows = hourly_bars(market.market_id, parse_trades(raw))
    log.info("kalshi %s: %d trades -> %d hourly bars", ticker, len(raw), len(rows))
    return rows
