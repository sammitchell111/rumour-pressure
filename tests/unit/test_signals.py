"""Synthetic series with known answers: decay must not look like news; injected jumps must."""

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from rumour_pressure.config import JumpParams
from rumour_pressure.signals.detrend import expected_price, implied_hazard
from rumour_pressure.signals.jumps import detect_jumps

T0 = datetime(2026, 1, 1, tzinfo=UTC)
PARAMS = JumpParams(min_delta=0.05, window_hours=24, min_trades=3)


def series(prices, n_trades=5):
    hours = [T0 + timedelta(hours=i) for i in range(len(prices))]
    return pd.DataFrame({"ts_utc": hours, "price": prices, "n_trades": n_trades, "volume": 10.0})


def detect(prices, mode="none", close=None, **kw):
    return detect_jumps("m", series(prices, **kw), PARAMS, mode=mode, close_time=close)


# --- detrending maths --------------------------------------------------------------


def test_implied_hazard_inverts_the_constant_hazard_price():
    lam, tau = 0.01, 200.0
    p = 1 - math.exp(-lam * tau)
    assert implied_hazard(p, tau) == pytest.approx(lam)


def test_expected_price_with_no_news_drifts_down_as_time_runs_out():
    p_now = 0.4
    later = expected_price(p_now, tau_days=10, step_days=1)
    assert later < p_now
    assert expected_price(p_now, tau_days=10, step_days=0) == pytest.approx(p_now)


# --- detection ---------------------------------------------------------------------


def test_flat_series_has_no_jumps():
    assert detect([0.3] * 200) == []


def test_an_injected_step_is_found_once_and_dated_at_its_onset():
    prices = [0.20] * 100 + [0.32] * 100
    (jump,) = detect(prices)
    assert jump.ts_start == T0 + timedelta(hours=100)
    assert jump.delta == pytest.approx(0.12)
    assert jump.residual == pytest.approx(0.12)


def test_a_drop_is_a_negative_jump():
    (jump,) = detect([0.50] * 100 + [0.40] * 100)
    assert jump.delta == pytest.approx(-0.10)


def test_two_separate_jumps_are_both_found():
    prices = [0.20] * 100 + [0.30] * 100 + [0.45] * 100
    jumps = detect(prices)
    assert [j.ts_start for j in jumps] == [T0 + timedelta(hours=h) for h in (100, 200)]


def test_a_move_spread_over_a_few_hours_is_one_jump():
    prices = [0.20] * 100 + [0.24, 0.28, 0.31] + [0.31] * 100
    (jump,) = detect(prices)
    assert jump.delta == pytest.approx(0.11)
    assert T0 + timedelta(hours=100) <= jump.ts_start <= T0 + timedelta(hours=102)


def test_small_moves_are_ignored():
    assert detect([0.20] * 100 + [0.23] * 100) == []


def test_thin_jumps_are_dropped_but_unknown_volume_is_kept():
    prices = [0.20] * 100 + [0.32] * 100
    assert detect(prices, n_trades=0) == []
    assert len(detect(prices, n_trades=None)) == 1


def test_pure_deadline_decay_is_not_news_under_hazard_detrending():
    # Constant hazard, 20 days to the deadline: the price slides faster near the end.
    lam, close_h = 0.08, 20 * 24
    prices = [1 - math.exp(-lam * (close_h - h) / 24) for h in range(close_h - 24)]
    close = T0 + timedelta(hours=close_h)
    assert detect(prices, mode="none", close=close) != []  # naive: decay looks like jumps
    assert detect(prices, mode="hazard", close=close) == []


def test_news_on_top_of_decay_is_still_found_under_hazard_detrending():
    lam, close_h = 0.02, 60 * 24
    prices = np.array([1 - math.exp(-lam * (close_h - h) / 24) for h in range(close_h - 48)])
    prices[700:] += 0.15  # a rumour lands at hour 700
    (jump,) = detect(
        list(np.clip(prices, 0, 1)), mode="hazard", close=T0 + timedelta(hours=close_h)
    )
    assert jump.ts_start == T0 + timedelta(hours=700)
    assert jump.residual == pytest.approx(0.15, abs=0.01)


PERSIST = JumpParams(min_delta=0.05, window_hours=24, min_trades=3, min_persistence=0.5)


def test_persistence_rejects_spikes_but_keeps_their_snap_backs():
    bounce = ([0.47] * 50 + [0.70] * 6) * 6 + [0.47] * 100  # brief spikes that snap back
    without = detect_jumps("m", series(bounce), PARAMS)
    with_ = detect_jumps("m", series(bounce), PERSIST)
    assert {j.delta > 0 for j in without} == {True, False}
    assert with_ and all(j.delta < 0 for j in with_)  # the return trip persists


ZSCORE = JumpParams(min_delta=0.05, window_hours=24, min_trades=3, min_z=3.0)


def test_noise_scaled_threshold_ignores_a_market_that_always_bounces():
    rng = np.random.default_rng(0)
    noisy = list(np.clip(0.5 + rng.choice([-0.1, 0.1], size=1500) * (rng.random(1500) < 0.1), 0, 1))
    warmup = T0 + timedelta(hours=7 * 24 + 24)  # the first week has no noise history yet
    without = [j for j in detect_jumps("m", series(noisy), PARAMS) if j.ts_start > warmup]
    with_ = [j for j in detect_jumps("m", series(noisy), ZSCORE) if j.ts_start > warmup]
    assert len(without) >= 20
    assert len(with_) <= len(without) / 4  # only rare outliers survive


def test_noise_scaled_threshold_keeps_a_modest_move_in_a_quiet_market():
    rng = np.random.default_rng(1)
    quiet = 0.30 + rng.normal(0, 0.003, size=1200)
    quiet[1000:] += 0.06
    (jump,) = detect_jumps("m", series(list(quiet)), ZSCORE)
    assert jump.ts_start == T0 + timedelta(hours=1000)


def test_a_lasting_step_passes_the_persistence_test():
    prices = [0.20] * 100 + [0.32] * 200
    assert len(detect_jumps("m", series(prices), PERSIST)) == 1


def test_a_jump_too_recent_to_judge_is_kept():
    prices = [0.20] * 100 + [0.32] * 30  # fewer than 72 hours after it
    assert len(detect_jumps("m", series(prices), PERSIST)) == 1


def test_params_hash_changes_with_parameters_and_mode():
    prices = [0.20] * 100 + [0.32] * 100
    a = detect_jumps("m", series(prices), PARAMS, mode="none")[0].params_hash
    b = detect_jumps("m", series(prices), JumpParams(min_delta=0.06), mode="none")[0].params_hash
    assert a != b
