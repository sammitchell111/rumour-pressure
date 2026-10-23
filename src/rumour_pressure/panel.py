"""Panel feasibility count (PLAN.md Task 7): are there enough informative jumps?

Counts qualifying jumps per market and family, and *independent events*: qualifying
jumps in the same family whose onsets fall within `EVENT_GAP` of each other are one
event (one rumour often moves several related markets). Compares the default jump
filters with the plain 5-point rule.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module

from rumour_pressure.config import JUMP_PARAMS, JumpParams
from rumour_pressure.registry import Registry
from rumour_pressure.signals.jumps import params_hash
from rumour_pressure.signals.run import MIN_DAYS_REMAINING, detect_for_market
from rumour_pressure.store import Warehouse

log = logging.getLogger(__name__)

EVENT_GAP = timedelta(hours=24)
PLAIN_RULE = JumpParams(min_persistence=0.0, min_z=0.0)


def independent_events(onsets: list[datetime], gap: timedelta = EVENT_GAP) -> int:
    """Count clusters of onsets where each is within `gap` of the previous one."""
    events, last = 0, None
    for t in sorted(onsets):
        if last is None or t - last > gap:
            events += 1
        last = t
    return events


@dataclass
class FamilyCount:
    family: str
    source: str  # "panel" or "flagship"
    venues: set[str]
    markets: int
    markets_with_data: int
    qualifying: int
    events: int
    qualifying_plain: int
    events_plain: int


def collect_and_count(
    wh: Warehouse, registry: Registry, source: str, collect: bool = True
) -> tuple[list[FamilyCount], list[str]]:
    by_family: dict[str, list] = {}
    failed: list[str] = []
    for m in registry.markets:
        if collect:
            try:
                rows = import_module(f"rumour_pressure.collect.{m.venue}").collect_prices(m)
            except Exception as exc:
                log.error("collect failed for %s: %s", m.market_id, exc)
                failed.append(m.market_id)
                continue
            wh.upsert([m.to_row()])
            wh.upsert(rows)
        default = detect_for_market(wh, m, JUMP_PARAMS)
        plain = detect_for_market(wh, m, PLAIN_RULE, store=False)
        by_family.setdefault(m.group, []).append((m, default, plain))

    out = []
    for family, items in by_family.items():
        d_onsets = [t for _, d, _ in items for t in d.qualifying_onsets]
        p_onsets = [t for _, _, p in items for t in p.qualifying_onsets]
        out.append(
            FamilyCount(
                family=family,
                source=source,
                venues={m.venue for m, _, _ in items},
                markets=len(items),
                markets_with_data=sum(d.n_bars > 0 for _, d, _ in items),
                qualifying=len(d_onsets),
                events=independent_events(d_onsets),
                qualifying_plain=len(p_onsets),
                events_plain=independent_events(p_onsets),
            )
        )
    return out, failed


def _totals(rows: list[FamilyCount]) -> dict[str, int]:
    return {
        "families": len(rows),
        "families_with_events": sum(r.events > 0 for r in rows),
        "markets": sum(r.markets for r in rows),
        "markets_with_data": sum(r.markets_with_data for r in rows),
        "qualifying": sum(r.qualifying for r in rows),
        "events": sum(r.events for r in rows),
        "qualifying_plain": sum(r.qualifying_plain for r in rows),
        "events_plain": sum(r.events_plain for r in rows),
    }


def render_report(panel: list[FamilyCount], flagships: list[FamilyCount], failed: list[str]) -> str:
    p, f = _totals(panel), _totals(flagships)
    both = _totals(panel + flagships)
    lines = [
        "# Panel feasibility count",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `rp panel-count`.",
        "",
        "## Headline",
        "",
        f"**{both['events']} independent qualifying events** across "
        f"{both['families_with_events']} families with at least one event "
        f"({p['events']} from the {p['families']}-family panel, {f['events']} from the Taylor "
        f"Swift flagships). The go/no-go bar set in the plan was dozens to low hundreds.",
        "",
        "| | Families | Markets (with data) | Qualifying jumps | Independent events |"
        " Jumps, plain 5-pt rule | Events, plain rule |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, t in (("Panel", p), ("Flagships", f), ("Total", both)):
        lines.append(
            f"| {label} | {t['families']} | {t['markets']} ({t['markets_with_data']}) | "
            f"{t['qualifying']} | {t['events']} | {t['qualifying_plain']} | {t['events_plain']} |"
        )
    lines += [
        "",
        "## Definitions",
        "",
        f"- **Jump** (default filters, `params_hash` {params_hash(JUMP_PARAMS, 'hazard')} / "
        f"{params_hash(JUMP_PARAMS, 'none')}): detrended move ≥ "
        f"{JUMP_PARAMS.min_delta * 100:.0f} points in {JUMP_PARAMS.window_hours} h, "
        f"≥ {JUMP_PARAMS.min_trades} trades, keeps ≥ {JUMP_PARAMS.min_persistence:.0%} of its "
        f"move {JUMP_PARAMS.persistence_hours} h later, and ≥ {JUMP_PARAMS.min_z:g}× the "
        "market's own 30-day noise.",
        "- **Plain rule**: the 5-point rule alone, for comparison.",
        f"- **Qualifying**: ≥ {MIN_DAYS_REMAINING:.0f} days before the market's deadline and not "
        "a resolution move (ending within 3 points of 0 or 1).",
        f"- **Independent event**: qualifying jumps in one family within "
        f"{EVENT_GAP.total_seconds() / 3600:.0f} h of each other count once.",
        "- **Panel selection rule**: see `scripts/build_panel_candidates.py`.",
        "",
        "## By family",
        "",
        "| Family | Source | Venues | Markets | Qualifying jumps | Events | Events, plain rule |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in sorted(panel + flagships, key=lambda r: (-r.events, r.family)):
        lines.append(
            f"| {r.family} | {r.source} | {', '.join(sorted(r.venues))} | {r.markets} | "
            f"{r.qualifying} | {r.events} | {r.events_plain} |"
        )
    if failed:
        lines += ["", "## Collection failures", ""] + [f"- {m}" for m in failed]
    return "\n".join(lines) + "\n"
