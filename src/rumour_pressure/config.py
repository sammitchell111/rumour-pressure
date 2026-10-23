"""Paths, rate limits and analysis defaults. Everything tunable lives here, not in modules."""

import os
import secrets
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


def live_stage_dir(source: str) -> Path:
    """Where long-running loggers stage records for ingest (they never open the warehouse)."""
    return data_dir() / "live" / source


def author_salt() -> str:
    """Salt for hashing author IDs. From RP_AUTHOR_SALT, else a per-install secret file.

    The salt must stay the same across runs, or the same author gets different hashes.
    """
    if salt := os.environ.get("RP_AUTHOR_SALT"):
        return salt
    path = data_dir() / ".author_salt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(16))
        path.chmod(0o600)
    return path.read_text().strip()


# Used by the Bluesky logger until the market registry (Task 3) supplies keywords.
DEFAULT_LIVE_KEYWORDS = ("Taylor Swift", "Swifties", "Swiftie", "#TaylorSwift", "Travis Kelce")


@dataclass(frozen=True)
class RateLimits:
    """Minimum seconds between requests, per source."""

    gdelt: float = 5.0
    arctic_shift: float = 0.7
    wikipedia: float = 0.1
    manifold: float = 0.1
    polymarket: float = 0.2
    kalshi: float = 1.0  # 5 req/s drew HTTP 429s in testing


@dataclass(frozen=True)
class JumpParams:
    """Defaults for jump detection; stored with each jump as params_hash."""

    min_delta: float = 0.05  # 5 probability points
    window_hours: int = 24
    min_trades: int = 3


RATE_LIMITS = RateLimits()
JUMP_PARAMS = JumpParams()
