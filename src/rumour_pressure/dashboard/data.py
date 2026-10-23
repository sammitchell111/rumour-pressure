"""Queries behind the dashboard. Pure functions over a DuckDB connection, so they're testable.

The dashboard opens the warehouse read-only. Prices are stored as hourly bars only for
hours with activity; `price_grid` forward-fills them onto a full hourly grid per market
(starting at each market's first bar, ending at its last), marking observed hours.
"""

import duckdb
import pandas as pd

from rumour_pressure.store.queries import price_grid  # noqa: F401  (re-exported)


def connect_read_only(path: str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(path, read_only=True)


def markets(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT m.market_id, m.venue, m.question, m.resolution_text, m.url, m.close_time,
               count(p.ts_utc) AS n_bars, min(p.ts_utc) AS first_bar, max(p.ts_utc) AS last_bar,
               sum(p.volume) AS volume
        FROM markets m LEFT JOIN prices p USING (market_id)
        GROUP BY ALL
        ORDER BY m.close_time NULLS LAST, m.market_id
        """
    ).df()


def jumps(con: duckdb.DuckDBPyConnection, market_ids: list[str]) -> pd.DataFrame:
    """Detected jumps with the context the analysis filters on.

    days_remaining: days from onset to the market's close (time-remaining rule).
    is_resolution:  the price ends the jump within 3 points of 0 or 1 — the outcome becoming
                    known, which says little about rumour.
    """
    if not market_ids:
        return pd.DataFrame()
    return con.execute(
        """
        SELECT j.*, m.question,
               date_diff('hour', j.ts_start, m.close_time) / 24.0 AS days_remaining,
               p.price AS price_after,
               (p.price <= 0.03 OR p.price >= 0.97) AS is_resolution
        FROM jumps j
        JOIN markets m USING (market_id)
        LEFT JOIN prices p ON p.market_id = j.market_id AND p.ts_utc = j.ts_end
        WHERE j.market_id IN (SELECT unnest(?))
        ORDER BY j.ts_start
        """,
        [market_ids],
    ).df()
