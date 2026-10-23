from datetime import UTC, datetime
from pathlib import Path

from rumour_pressure.dashboard import data
from rumour_pressure.store import Warehouse
from rumour_pressure.store.models import MarketRow, PriceRow


def t(h):
    return datetime(2026, 10, 23, h, tzinfo=UTC)


def make_wh(tmp_path):
    wh = Warehouse(tmp_path / "wh.duckdb")
    wh.upsert(
        [
            MarketRow(
                market_id="m1", venue="manifold", question="Q?", resolution_text="R", url="u"
            ),
            PriceRow(market_id="m1", ts_utc=t(1), price=0.2, volume=3.0, n_trades=1),
            PriceRow(market_id="m1", ts_utc=t(4), price=0.5, volume=1.0, n_trades=1),
        ]
    )
    return wh


def test_price_grid_forward_fills_quiet_hours(tmp_path):
    with make_wh(tmp_path) as wh:
        grid = data.price_grid(wh.con, ["m1"])
    assert list(grid["price"]) == [0.2, 0.2, 0.2, 0.5]
    assert list(grid["observed"]) == [True, False, False, True]


def test_price_grid_respects_the_date_window(tmp_path):
    with make_wh(tmp_path) as wh:
        grid = data.price_grid(wh.con, ["m1"], start=t(2), end=t(3))
    assert len(grid) == 2
    assert list(grid["price"]) == [0.2, 0.2]  # carried in from before the window


def test_markets_summarises_bars(tmp_path):
    with make_wh(tmp_path) as wh:
        mk = data.markets(wh.con)
    assert mk.loc[0, "n_bars"] == 2
    assert mk.loc[0, "volume"] == 4.0


def test_dashboard_renders_against_a_warehouse(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    make_wh(tmp_path).close()
    monkeypatch.setenv("RP_DATA_DIR", str(tmp_path))
    (tmp_path / "wh.duckdb").rename(tmp_path / "warehouse.duckdb")
    app = Path(__file__).parents[2] / "src" / "rumour_pressure" / "dashboard" / "app.py"
    at = AppTest.from_file(str(app), default_timeout=30).run()
    assert not at.exception, at.exception
    assert "price on a shared hourly timeline" in at.title[0].value
