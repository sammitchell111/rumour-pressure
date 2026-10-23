"""DuckDB warehouse with idempotent upserts."""

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from rumour_pressure.store.models import Row
from rumour_pressure.store.schema import DDL

log = logging.getLogger(__name__)


def _to_db(value: Any) -> Any:
    """UTC-aware datetimes are stored naive (the warehouse is UTC by convention)."""
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class Warehouse:
    def __init__(self, path: Path | str):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(path))
        self.con.execute(DDL)

    def __enter__(self) -> "Warehouse":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.con.close()

    def upsert(self, rows: Iterable[Row]) -> int:
        """Insert rows, replacing any with the same primary key. Returns rows written."""
        by_type: dict[type[Row], list[Row]] = defaultdict(list)
        for row in rows:
            by_type[type(row)].append(row)

        written = 0
        for model, batch in by_type.items():
            cols = list(model.model_fields)
            placeholders = ", ".join("?" for _ in cols)
            sql = (
                f"INSERT OR REPLACE INTO {model.table} ({', '.join(cols)}) VALUES ({placeholders})"
            )
            values = [[_to_db(getattr(r, c)) for c in cols] for r in batch]
            self.con.executemany(sql, values)
            written += len(batch)
            log.info("upserted %d rows into %s", len(batch), model.table)
        return written

    def delete_posts(self, post_ids: Iterable[str]) -> None:
        """Remove posts (and any stance labels on them), e.g. when an author deletes one."""
        ids = list(post_ids)
        if not ids:
            return
        for table in ("stance", "posts"):
            self.con.execute(f"DELETE FROM {table} WHERE post_id IN (SELECT unnest(?))", [ids])
        log.info("deleted %d posts at their authors' request", len(ids))

    def tables(self) -> set[str]:
        return {name for (name,) in self.con.execute("SHOW TABLES").fetchall()}

    def count(self, table: str) -> int:
        if table not in self.tables():
            raise ValueError(f"unknown table: {table}")
        return self.con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def query(self, sql: str, params: list[Any] | None = None) -> list[tuple]:
        return self.con.execute(sql, params or []).fetchall()


__all__ = ["Warehouse"]
