"""Paths, rate limits and analysis defaults. Everything tunable lives here, not in modules."""

import os
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = "rumour-pressure/0.1 (research; https://github.com/sammitchell111/rumour-pressure)"


def data_dir() -> Path:
    """Root for the warehouse and raw caches. Override with RP_DATA_DIR."""
    return Path(os.environ.get("RP_DATA_DIR", "data"))


def warehouse_path() -> Path:
    return data_dir() / "warehouse.duckdb"


def raw_cache_dir(source: str) -> Path:
    return data_dir() / "raw" / source


@dataclass(frozen=True)
class RateLimits:
    """Minimum seconds between requests, per source."""

    gdelt: float = 5.0
    arctic_shift: float = 0.7
    wikipedia: float = 0.1
    manifold: float = 0.1
    polymarket: float = 0.2
    kalshi: float = 0.2


@dataclass(frozen=True)
class JumpParams:
    """Defaults for jump detection; stored with each jump as params_hash."""

    min_delta: float = 0.05  # 5 probability points
    window_hours: int = 24
    min_trades: int = 3


RATE_LIMITS = RateLimits()
JUMP_PARAMS = JumpParams()
