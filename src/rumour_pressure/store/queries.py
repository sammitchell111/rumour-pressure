"""Shared read queries over the warehouse (used by signals and the dashboard)."""

from datetime import UTC, datetime

import duckdb
import pandas as pd


def _naive_utc(ts: datetime | None) -> datetime | None:
    """The warehouse stores naive UTC; aware inputs are converted, naive ones assumed UTC."""
    if ts is None or ts.tzinfo is None:
        return ts
    return ts.astimezone(UTC).replace(tzinfo=None)


def price_grid(
    con: duckdb.DuckDBPyConnection,
    market_ids: list[str],
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    """Hourly, forward-filled prices: market_id, ts_utc, price, volume, n_trades, observed."""
    if not market_ids:
        return pd.DataFrame(
            columns=["market_id", "ts_utc", "price", "volume", "n_trades", "observed"]
        )
    start, end = _naive_utc(start), _naive_utc(end)
    return con.execute(
        """
        WITH span AS (
            SELECT market_id, min(ts_utc) AS lo, max(ts_utc) AS hi
            FROM prices WHERE market_id IN (SELECT unnest(?)) GROUP BY market_id
        ),
        grid AS (
            SELECT market_id, unnest(generate_series(lo, hi, INTERVAL 1 HOUR)) AS ts_utc
            FROM span
        ),
        filled AS (  -- fill before filtering, so a window starts with the carried-in price
            SELECT g.market_id, g.ts_utc,
                   last_value(p.price IGNORE NULLS)
                       OVER (PARTITION BY g.market_id ORDER BY g.ts_utc) AS price,
                   p.volume, p.n_trades, p.price IS NOT NULL AS observed
            FROM grid g LEFT JOIN prices p USING (market_id, ts_utc)
        )
        SELECT * FROM filled
        WHERE (? IS NULL OR ts_utc >= ?) AND (? IS NULL OR ts_utc <= ?)
        ORDER BY market_id, ts_utc
        """,
        [market_ids, start, start, end, end],
    ).df()
