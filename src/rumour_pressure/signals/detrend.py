"""Constant-hazard detrending for deadline markets ("will X happen by date D?").

If the event arrives at a constant daily rate λ, the fair YES price with τ days left is
    P = 1 − exp(−λ τ).
So a price implies λ = −ln(1 − P) / τ, and with no news the price after `step` days is
    1 − exp(−λ (τ − step)).
The residual — actual minus that expected drift — is the part of a move that is news.
"""

import math
from datetime import datetime

import numpy as np
import pandas as pd

EPS = 1e-4  # keeps logs finite at prices of exactly 0 or 1


def implied_hazard(p: float, tau_days: float) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return -math.log(1 - p) / tau_days


def expected_price(p: float, tau_days: float, step_days: float) -> float:
    remaining = tau_days - step_days
    if remaining <= 0:
        return 0.0
    return 1 - math.exp(-implied_hazard(p, tau_days) * remaining)


def residuals(
    ts: pd.Series,
    prices: pd.Series,
    window_hours: int,
    mode: str,
    close_time: datetime | None,
) -> np.ndarray:
    """Residual move over the trailing window, per hour (NaN where undefined).

    mode="none": plain change P_t − P_{t−w}.
    mode="hazard": P_t minus the no-news expectation from P_{t−w}; NaN once the deadline
    falls inside the window (the baseline is undefined there) or if there's no close time.
    """
    p = prices.to_numpy(dtype=float)
    out = np.full(len(p), np.nan)
    w = window_hours
    if len(p) <= w:
        return out
    base, now = p[:-w], p[w:]
    if mode == "none":
        out[w:] = now - base
        return out
    if mode != "hazard":
        raise ValueError(f"unknown detrend mode: {mode}")
    if close_time is None:
        return out
    close = pd.Timestamp(close_time)
    stamps = pd.to_datetime(ts)
    if stamps.dt.tz is None:
        stamps = stamps.dt.tz_localize("UTC")
    if close.tzinfo is None:
        close = close.tz_localize("UTC")
    tau = ((close - stamps).dt.total_seconds() / 86400).to_numpy()[:-w]
    step = w / 24
    pb = np.clip(base, EPS, 1 - EPS)
    with np.errstate(divide="ignore", invalid="ignore"):
        lam = -np.log(1 - pb) / tau
        expected = np.where(tau - step > 0, 1 - np.exp(-lam * (tau - step)), np.nan)
    out[w:] = now - expected
    return out
