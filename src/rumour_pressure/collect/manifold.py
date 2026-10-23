"""Manifold prices from the full bet history (play money; every bet records probAfter)."""

import logging
from datetime import UTC, datetime
from typing import Any

from rumour_pressure.collect.prices import Trade, cached, hourly_bars
from rumour_pressure.http import get_json
from rumour_pressure.registry import RegistryMarket
from rumour_pressure.store.models import PriceRow

log = logging.getLogger(__name__)

API = "https://api.manifold.markets/v0"
PAGE = 1000


def parse_bets(bets: list[dict[str, Any]]) -> list[Trade]:
    """Bets -> trades. Redemptions, cancelled and unfilled orders don't move the price."""
    return [
        Trade(
            ts=datetime.fromtimestamp(b["createdTime"] / 1000, tz=UTC),
            price=float(b["probAfter"]),
            size=abs(float(b.get("amount") or 0)),
        )
        for b in bets
        if not b.get("isRedemption")
        and not b.get("isCancelled")
        and (b.get("amount") or 0) != 0
        and b.get("probAfter") is not None
    ]


def fetch_bets(contract_id: str) -> list[dict[str, Any]]:
    """All bets for a market, paging backwards from the newest. User IDs are dropped."""
    out: list[dict[str, Any]] = []
    before = None
    while True:
        params: dict[str, Any] = {"contractId": contract_id, "limit": PAGE}
        if before:
            params["before"] = before
        page = get_json("manifold", f"{API}/bets", params)
        out += [{k: v for k, v in b.items() if k not in ("userId", "fills")} for b in page]
        if len(page) < PAGE:
            return out
        before = page[-1]["id"]


def collect_prices(market: RegistryMarket) -> list[PriceRow]:
    ref = market.venue_ref["id"]
    bets = cached("manifold", f"bets_{ref}", lambda: fetch_bets(ref), reuse=market.closed)
    rows = hourly_bars(market.market_id, parse_bets(bets))
    log.info("manifold %s: %d bets -> %d hourly bars", ref, len(bets), len(rows))
    return rows
