import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from rumour_pressure.registry import Registry, RegistryMarket, load_registry, save_registry, venues

FIX = Path(__file__).parents[1] / "fixtures" / "registry"


def fixture(name):
    return json.loads((FIX / name).read_text())


# --- search parsing -------------------------------------------------------------


def test_manifold_search_parses_candidates():
    cands = venues.parse_manifold_search(fixture("manifold_search.json"))
    by_ref = {c.ref: c for c in cands}
    c = by_ref["6RugqEP5UC"]
    assert c.venue == "manifold"
    assert c.question == "Taylor Swift announces pregnancy before 2029?"
    assert c.kind == "BINARY"
    assert c.close_time.tzinfo is not None


def test_polymarket_search_flattens_events_into_markets():
    cands = venues.parse_polymarket_search(fixture("polymarket_search.json"))
    assert cands, "expected markets"
    assert all(c.venue == "polymarket" and c.ref.isdigit() for c in cands)
    assert any(c.closed for c in cands) or all(not c.closed for c in cands)


def test_kalshi_events_become_one_candidate_per_market():
    cands = venues.parse_kalshi_events(fixture("kalshi_events.json"))
    dress = [c for c in cands if c.ref.startswith("KXSWIFTWEDDING")]
    assert len(dress) == 2
    assert all("Wedding Dress" in c.question for c in dress)


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Taylor Swift pregnant before 2027?", True),
        ("Will D'Andre Swift have 1,000+ rushing yards?", False),
        ("Taylor & Travis divorce in 2026?", True),  # matched by the second alias
        ("Who will be elected president in 2028?", False),
    ],
)
def test_entity_filter(question, expected):
    assert venues.mentions_any(question, ["Taylor Swift", "Taylor & Travis"]) is expected


# --- full market fetch parsing ---------------------------------------------------


def test_polymarket_market_keeps_token_ids_and_rules():
    m = venues.parse_polymarket_market(fixture("polymarket_market.json"), group="pregnancy")
    assert m.market_id == "polymarket:1048199"
    assert m.resolution_text.startswith("This market will resolve")
    assert len(m.venue_ref["clob_token_ids"]) == 2
    assert m.venue_ref["condition_id"].startswith("0x")
    assert m.close_time == datetime(2027, 1, 1, 4, 59, tzinfo=UTC)


def test_manifold_market_uses_text_description_as_rules():
    m = venues.parse_manifold_market(fixture("manifold_market.json"), group="pregnancy")
    assert m.market_id == "manifold:6RugqEP5UC"
    assert "miscarriage" in m.resolution_text


def test_kalshi_market_combines_primary_and_secondary_rules():
    m = venues.parse_kalshi_market(fixture("kalshi_market.json"), group="wedding")
    assert m.market_id == "kalshi:KXSWIFTWEDDING-26DEC31-DIO"
    assert "Dior" in m.resolution_text
    assert m.venue_ref["event_ticker"] == "KXSWIFTWEDDING-26DEC31"


# --- registry file ---------------------------------------------------------------


def make_market(ref="1", **kw):
    return RegistryMarket(
        market_id=f"polymarket:{ref}",
        venue="polymarket",
        venue_ref={"id": ref},
        group=kw.get("group", "pregnancy"),
        question="Q?",
        resolution_text="Resolves YES if...",
        url="https://polymarket.com/x",
        entity_keys=kw.get("entity_keys", ["Taylor Swift"]),
    )


def test_registry_round_trips_through_yaml(tmp_path):
    reg = Registry(markets=[make_market("1"), make_market("2", group="wedding")])
    path = tmp_path / "markets.yaml"
    save_registry(reg, path)
    assert load_registry(path) == reg


def test_duplicate_market_ids_are_rejected():
    with pytest.raises(ValidationError):
        Registry(markets=[make_market("1"), make_market("1")])


def test_upsert_replaces_a_market_with_the_same_id():
    reg = Registry(markets=[make_market("1")])
    reg = reg.upsert(make_market("1", group="wedding"))
    assert [m.group for m in reg.markets] == ["wedding"]


def test_live_keywords_are_the_union_of_entity_keys_and_extras():
    reg = Registry(
        markets=[make_market("1", entity_keys=["Taylor Swift", "Travis Kelce"]), make_market("2")],
        extra_live_keywords=["Swifties"],
    )
    assert reg.live_keywords() == ["Swifties", "Taylor Swift", "Travis Kelce"]


def test_registry_market_converts_to_a_warehouse_row():
    row = make_market("1").to_row()
    assert row.market_id == "polymarket:1"
    assert row.entity_keys == ["Taylor Swift"]
