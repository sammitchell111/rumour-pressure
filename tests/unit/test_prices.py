import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rumour_pressure.collect import kalshi, manifold, polymarket
from rumour_pressure.collect.prices import Trade, hourly_bars, merge_history_with_trades

FIX = Path(__file__).parents[1] / "fixtures" / "prices"


def fixture(name):
    return json.loads((FIX / name).read_text())


def ts(h, m=0, s=0):
    return datetime(2026, 10, 23, h, m, s, tzinfo=UTC)


# --- shared aggregation ---------------------------------------------------------


def test_hourly_bars_close_on_the_last_trade_and_sum_volume():
    trades = [
        Trade(ts(9, 10), 0.20, 5.0),
        Trade(ts(9, 50), 0.25, 1.0),
        Trade(ts(11, 5), 0.30, 2.0),
    ]
    bars = hourly_bars("m", trades)
    assert [(b.ts_utc, b.price, b.volume, b.n_trades) for b in bars] == [
        (ts(9), 0.25, 6.0, 2),
        (ts(11), 0.30, 2.0, 1),
    ]


def test_hourly_bars_sort_trades_first():
    trades = [Trade(ts(9, 50), 0.25, 1.0), Trade(ts(9, 10), 0.20, 5.0)]
    assert hourly_bars("m", trades)[0].price == 0.25


def test_history_prices_with_trade_volume_where_the_trade_log_reaches():
    history = [(ts(8), 0.10), (ts(9), 0.12), (ts(10), 0.15), (ts(10, 30), 0.16)]
    trades = [Trade(ts(9, 20), 0.12, 3.0), Trade(ts(9, 40), 0.12, 1.0)]
    bars = merge_history_with_trades("m", history, trades, trade_log_complete_from=ts(9))
    got = {b.ts_utc: (b.price, b.volume, b.n_trades) for b in bars}
    assert got[ts(8)] == (0.10, None, None)  # before the trade log reaches: unknown, not 0
    assert got[ts(9)] == (0.12, 4.0, 2)
    assert got[ts(10)] == (0.16, 0.0, 0)  # covered and quiet: genuinely zero; last point wins


# --- Manifold -------------------------------------------------------------------


def test_manifold_bets_skip_redemptions_and_cancellations():
    trades = manifold.parse_bets(fixture("manifold_bets.json"))
    assert len(trades) == 4
    assert all(0 <= t.price <= 1 for t in trades)


def test_manifold_price_is_probability_after_the_bet():
    raw = fixture("manifold_bets.json")[0]
    (trade,) = manifold.parse_bets([raw])
    assert trade.price == pytest.approx(raw["probAfter"])
    assert trade.ts == datetime.fromtimestamp(raw["createdTime"] / 1000, tz=UTC)


# --- Polymarket -----------------------------------------------------------------

YES = "44827572479353518081244438746113968420"


def test_polymarket_history_points_parse():
    pts = polymarket.parse_history(fixture("polymarket_history.json"))
    assert len(pts) == 6
    assert all(t.tzinfo is not None and 0 <= p <= 1 for t, p in pts)


def test_polymarket_no_token_trades_convert_to_yes_price():
    raw = fixture("polymarket_trades.json")
    yes_token = next(t["asset"] for t in raw if t["outcome"] == "Yes")
    trades = polymarket.parse_trades(raw, yes_token=yes_token)
    for src, t in zip(raw, trades, strict=True):
        expected = src["price"] if src["asset"] == yes_token else 1 - src["price"]
        assert t.price == pytest.approx(expected)


# --- Kalshi ---------------------------------------------------------------------


def test_kalshi_trades_use_yes_price_and_contract_count():
    raw = fixture("kalshi_trades.json")
    trades = kalshi.parse_trades(raw["trades"])
    first = raw["trades"][0]
    assert trades[0].price == pytest.approx(float(first["yes_price_dollars"]))
    assert trades[0].size == pytest.approx(float(first["count_fp"]))
    assert trades[0].ts.tzinfo is not None
