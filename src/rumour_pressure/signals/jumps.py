"""Jump detection on an hourly, forward-filled price series.

A jump is a run of hours whose residual move over the trailing window is at least
`min_delta`. Each run yields one jump:
  - ts_end   = the hour where |residual| peaks (first such hour);
  - ts_start = the onset: the hour inside that window with the biggest single-hour move
               in the jump's direction — the timestamp the lead-lag analysis compares to;
  - delta    = raw price change over the window; residual = detrended change.
Jumps whose window holds fewer than `min_trades` known trades are dropped; if the trade
count is unknown (outside a venue's trade log) the jump is kept with n_trades = None.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime

import numpy as np
import pandas as pd

from rumour_pressure.config import JumpParams
from rumour_pressure.signals.detrend import residuals
from rumour_pressure.store.models import JumpRow

ALGO_VERSION = "jumps-v1"


def params_hash(params: JumpParams, mode: str) -> str:
    blob = json.dumps({"params": asdict(params), "mode": mode, "algo": ALGO_VERSION})
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def _aware(ts) -> datetime:
    ts = pd.Timestamp(ts)
    return (ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")).to_pydatetime()


def _window_sum(values: pd.Series) -> tuple[float, bool]:
    """(sum of known values, whether any were unknown)."""
    known = values.dropna()
    return float(known.sum()), len(known) < len(values)


def detect_jumps(
    market_id: str,
    grid: pd.DataFrame,
    params: JumpParams,
    mode: str = "none",
    close_time: datetime | None = None,
) -> list[JumpRow]:
    """`grid`: one row per consecutive hour with ts_utc, price, n_trades, volume."""
    grid = grid.sort_values("ts_utc").reset_index(drop=True)
    if grid.empty:
        return []
    w = params.window_hours
    p = grid["price"].to_numpy(dtype=float)
    r = residuals(grid["ts_utc"], grid["price"], w, mode, close_time)
    flagged = np.abs(np.nan_to_num(r)) >= params.min_delta - 1e-12
    if params.min_z > 0:
        # Noise = std of residuals in the lookback, ending before the current window so
        # the jump being tested can't inflate its own yardstick.
        noise = (
            pd.Series(r)
            .rolling(params.noise_lookback_hours, min_periods=7 * 24)
            .std()
            .shift(w)
            .to_numpy()
        )
        with np.errstate(invalid="ignore"):
            big_enough = np.where(np.isnan(noise), True, np.abs(r) >= params.min_z * noise)
        flagged &= big_enough
    phash = params_hash(params, mode)

    jumps: list[JumpRow] = []
    i, n = 0, len(p)
    while i < n:
        if not flagged[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and flagged[j + 1]:
            j += 1
        peak = i + int(np.argmax(np.abs(r[i : j + 1])))
        sign = np.sign(r[peak])
        lo = peak - w
        steps = np.diff(p[lo : peak + 1]) * sign  # moves into hours lo+1 .. peak
        onset = lo + 1 + int(np.argmax(steps))

        window = grid.iloc[lo + 1 : peak + 1]
        trades, trades_unknown = _window_sum(window["n_trades"])
        volume, volume_unknown = _window_sum(window["volume"])
        if not trades_unknown and trades < params.min_trades:
            i = j + 1
            continue
        thin_but_unknown = trades_unknown and trades < params.min_trades

        # Persistence: news moves the price and it stays moved; bid/ask bounce reverts.
        # Jumps too recent to judge (no data `persistence_hours` later) are kept.
        later = peak + params.persistence_hours
        move = p[peak] - p[lo]
        if params.min_persistence > 0 and later < n and move != 0:
            kept = (p[later] - p[lo]) / move
            if kept < params.min_persistence:
                i = j + 1
                continue

        onset_ts = _aware(grid.at[onset, "ts_utc"])
        if jumps and jumps[-1].ts_start == onset_ts:  # same onset as the previous run: merge
            i = j + 1
            continue

        jumps.append(
            JumpRow(
                market_id=market_id,
                ts_start=onset_ts,
                ts_end=_aware(grid.at[peak, "ts_utc"]),
                delta=float(p[peak] - p[lo]),
                residual=float(r[peak]),
                params_hash=phash,
                volume=None if volume_unknown and volume == 0 else volume,
                n_trades=None
                if thin_but_unknown or (trades_unknown and trades == 0)
                else int(trades),
            )
        )
        i = j + 1
    return jumps
