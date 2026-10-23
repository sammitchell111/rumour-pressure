from datetime import UTC, datetime, timedelta

from rumour_pressure.panel import FamilyCount, independent_events, render_report

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def at(h):
    return T0 + timedelta(hours=h)


def test_jumps_within_a_day_of_each_other_are_one_event():
    assert independent_events([at(0), at(5), at(20)]) == 1


def test_jumps_more_than_a_day_apart_are_separate_events():
    assert independent_events([at(0), at(30), at(100)]) == 3


def test_a_chain_of_close_jumps_stays_one_event():
    assert independent_events([at(0), at(20), at(40), at(60)]) == 1


def test_order_does_not_matter():
    assert independent_events([at(100), at(0), at(30)]) == 3


def test_no_jumps_no_events():
    assert independent_events([]) == 0


def fam(name, source, events):
    return FamilyCount(name, source, {"polymarket"}, 2, 2, events * 2, events, events * 5, events)


def test_report_totals_panel_and_flagships():
    report = render_report(
        [fam("obama", "panel", 3), fam("xi", "panel", 0)], [fam("pregnancy", "flagship", 4)], []
    )
    assert "**7 independent qualifying events**" in report
    assert "| obama | panel |" in report
    assert "Collection failures" not in report


def test_report_lists_collection_failures():
    report = render_report([fam("a", "panel", 1)], [], ["polymarket:1"])
    assert "- polymarket:1" in report
