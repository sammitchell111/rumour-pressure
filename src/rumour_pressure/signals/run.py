"""Run jump detection for registry markets and store the results."""

from dataclasses import dataclass

from rumour_pressure.config import JUMP_PARAMS, JumpParams
from rumour_pressure.registry import RegistryMarket
from rumour_pressure.signals.jumps import detect_jumps, params_hash
from rumour_pressure.store import Warehouse
from rumour_pressure.store.queries import price_grid

# Venues whose bars come only from trades: an hour without a bar had zero trades.
# (Polymarket bars come from price history, so a missing count there means "unknown".)
TRADE_BAR_VENUES = ("manifold", "kalshi")
MIN_DAYS_REMAINING = 60.0
RESOLUTION_BAND = 0.03


@dataclass(frozen=True)
class MarketJumps:
    market_id: str
    question: str
    n_jumps: int
    n_qualifying: int  # ≥ MIN_DAYS_REMAINING days left and not a resolution move


def detect_for_market(
    wh: Warehouse, market: RegistryMarket, params: JumpParams = JUMP_PARAMS
) -> MarketJumps:
    grid = price_grid(wh.con, [market.market_id])
    if market.venue in TRADE_BAR_VENUES:
        grid[["n_trades", "volume"]] = grid[["n_trades", "volume"]].fillna(0)
    rows = detect_jumps(
        market.market_id, grid, params, mode=market.detrend, close_time=market.close_time
    )
    wh.replace_jumps(market.market_id, params_hash(params, market.detrend), rows)

    qualifying = 0
    for j in rows:
        price_after = grid.loc[grid["ts_utc"] == j.ts_end.replace(tzinfo=None), "price"]
        p = float(price_after.iloc[0]) if len(price_after) else 0.5
        resolution = p <= RESOLUTION_BAND or p >= 1 - RESOLUTION_BAND
        days_left = (
            (market.close_time - j.ts_start).total_seconds() / 86400
            if market.close_time
            else float("inf")
        )
        qualifying += days_left >= MIN_DAYS_REMAINING and not resolution
    return MarketJumps(market.market_id, market.question, len(rows), qualifying)
