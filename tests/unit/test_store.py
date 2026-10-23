from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from rumour_pressure.store import Warehouse
from rumour_pressure.store.models import MarketRow, PostRow, PriceRow, StanceRow

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def wh(tmp_path):
    with Warehouse(tmp_path / "test.duckdb") as w:
        yield w


def test_schema_creates_every_table(wh):
    expected = {"markets", "prices", "attention", "posts", "stance", "jumps", "logger_gaps"}
    assert expected <= wh.tables()


def test_upserting_same_rows_twice_writes_no_duplicates(wh):
    rows = [PriceRow(market_id="m1", ts_utc=T0, price=0.2)]
    wh.upsert(rows)
    wh.upsert(rows)
    assert wh.count("prices") == 1


def test_upsert_updates_existing_row_in_place(wh):
    wh.upsert([PriceRow(market_id="m1", ts_utc=T0, price=0.2)])
    wh.upsert([PriceRow(market_id="m1", ts_utc=T0, price=0.3, volume=10.0)])
    assert wh.query("select price, volume from prices") == [(0.3, 10.0)]


def test_price_outside_unit_interval_is_rejected():
    with pytest.raises(ValidationError):
        PriceRow(market_id="m1", ts_utc=T0, price=1.2)


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValidationError):
        PriceRow(market_id="m1", ts_utc=datetime(2026, 10, 1, 12), price=0.2)


def test_non_utc_timestamps_are_stored_as_utc(wh):
    from zoneinfo import ZoneInfo

    paris = datetime(2026, 10, 1, 14, 0, tzinfo=ZoneInfo("Europe/Paris"))
    wh.upsert([PriceRow(market_id="m1", ts_utc=paris, price=0.2)])
    (ts,) = wh.query("select ts_utc from prices")[0]
    assert ts.replace(tzinfo=UTC) == T0


def test_new_prompt_version_adds_a_label_instead_of_overwriting(wh):
    base = dict(post_id="reddit:abc", market_id="m1", confidence=0.9, model="qwen3.5:9b")
    wh.upsert([StanceRow(**base, label="supports_yes", prompt_version="v1", classified_at=T0)])
    wh.upsert([StanceRow(**base, label="supports_no", prompt_version="v2", classified_at=T0)])
    assert wh.count("stance") == 2


def test_stance_label_must_be_one_of_three():
    with pytest.raises(ValidationError):
        StanceRow(
            post_id="reddit:abc",
            market_id="m1",
            label="maybe",
            confidence=0.5,
            model="x",
            prompt_version="v1",
            classified_at=T0,
        )


def test_list_columns_round_trip(wh):
    wh.upsert(
        [
            MarketRow(
                market_id="manifold:abc",
                venue="manifold",
                question="Will X happen?",
                resolution_text="Resolves YES if X.",
                url="https://example.com",
                entity_keys=["Taylor Swift", "Travis Kelce"],
            )
        ]
    )
    assert wh.query("select entity_keys from markets") == [(["Taylor Swift", "Travis Kelce"],)]


def test_mixed_row_types_in_one_call(wh):
    wh.upsert(
        [
            PriceRow(market_id="m1", ts_utc=T0, price=0.2),
            PostRow(
                post_id="bluesky:1",
                source="bluesky",
                ts_utc=T0,
                channel="jetstream",
                author_hash="h",
                text="hello",
                url="https://bsky.app/x",
                collected_at=T0,
            ),
        ]
    )
    assert (wh.count("prices"), wh.count("posts")) == (1, 1)
