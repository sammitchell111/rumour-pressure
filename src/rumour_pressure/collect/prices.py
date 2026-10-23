"""Shared price handling: every venue is reduced to trades, then to hourly bars.

A bar's price is the YES price at the hour's last observation; volume and n_trades are
summed over the hour. Hours with no observation have no bar (forward-fill at analysis
time). `volume=None` means "unknown" (outside the trade log's reach), never "zero".
"""

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rumour_pressure import config
from rumour_pressure.store.models import PriceRow

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Trade:
    ts: datetime
    price: float  # YES price after the trade, 0..1
    size: float  # venue units: shares, contracts or mana


def hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _clip(p: float) -> float:
    return min(1.0, max(0.0, p))


def hourly_bars(market_id: str, trades: Iterable[Trade]) -> list[PriceRow]:
    bars: dict[datetime, list[Trade]] = {}
    for t in sorted(trades, key=lambda t: t.ts):
        bars.setdefault(hour(t.ts), []).append(t)
    return [
        PriceRow(
            market_id=market_id,
            ts_utc=h,
            price=_clip(ts_[-1].price),
            volume=sum(t.size for t in ts_),
            n_trades=len(ts_),
        )
        for h, ts_ in bars.items()
    ]


def merge_history_with_trades(
    market_id: str,
    history: Iterable[tuple[datetime, float]],
    trades: Iterable[Trade],
    trade_log_complete_from: datetime | None,
) -> list[PriceRow]:
    """Prices from a venue's price history; volume and counts from its trade log.

    Hours before `trade_log_complete_from` get volume/n_trades = None (unknown).
    """
    price_by_hour: dict[datetime, float] = {}
    for t, p in sorted(history, key=lambda x: x[0]):
        price_by_hour[hour(t)] = p  # later points in the same hour win

    vol: dict[datetime, float] = {}
    cnt: dict[datetime, int] = {}
    for t in trades:
        h = hour(t.ts)
        vol[h] = vol.get(h, 0.0) + t.size
        cnt[h] = cnt.get(h, 0) + 1

    rows = []
    for h, p in price_by_hour.items():
        covered = trade_log_complete_from is not None and h >= hour(trade_log_complete_from)
        rows.append(
            PriceRow(
                market_id=market_id,
                ts_utc=h,
                price=_clip(p),
                volume=vol.get(h, 0.0) if covered else None,
                n_trades=cnt.get(h, 0) if covered else None,
            )
        )
    return rows


def cached(source: str, key: str, fetch: Callable[[], Any], reuse: bool) -> Any:
    """Fetch JSON, caching it under data/raw/<source>/<key>.json.

    With `reuse=True` (e.g. a resolved market) an existing cache is returned unfetched.
    """
    path = config.raw_cache_dir(source) / f"{key}.json"
    if reuse and path.exists():
        log.info("%s: using cached %s", source, path.name)
        return json.loads(path.read_text())
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data
