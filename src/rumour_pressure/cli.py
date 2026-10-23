"""`rp` command-line interface. Commands not yet built say which task builds them."""

import contextlib
import logging
from datetime import UTC, datetime
from typing import Annotated

import typer

from rumour_pressure import config
from rumour_pressure.store import Warehouse

app = typer.Typer(help="Rumour pressure vs. market price.", no_args_is_help=True)
registry_app = typer.Typer(help="Market registry.", no_args_is_help=True)
app.add_typer(registry_app, name="registry")

MarketOpt = Annotated[str, typer.Option("--market", help="Market ID from the registry.")]


def _not_yet(task: str) -> None:
    typer.echo(f"Not built yet — arrives in {task} (see PLAN.md).")
    raise typer.Exit(code=2)


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command("init-db")
def init_db() -> None:
    """Create the warehouse and its tables if they don't exist."""
    path = config.warehouse_path()
    with Warehouse(path) as wh:
        typer.echo(f"Warehouse ready at {path} ({len(wh.tables())} tables).")


@registry_app.command("find")
def registry_find(
    entity: Annotated[list[str], typer.Option("--entity", "-e", help="Name or alias; repeatable.")],
    venue: Annotated[
        list[str] | None, typer.Option("--venue", help="Limit to venue(s); repeatable.")
    ] = None,
    topic: Annotated[
        str | None, typer.Option("--topic", help="Regex the question must also match.")
    ] = None,
    min_volume: Annotated[float, typer.Option(help="Hide markets below this volume.")] = 0.0,
    open_only: Annotated[bool, typer.Option("--open-only")] = False,
) -> None:
    """List markets on each venue whose question names the entity (open and resolved)."""
    import re

    from rumour_pressure.registry import venues as v

    cands = v.find(entity, venues=venue or list(v.SEARCH))
    cands = [
        c
        for c in cands
        if (c.volume or 0) >= min_volume
        and not (open_only and c.closed)
        and (not topic or re.search(topic, c.question, re.IGNORECASE))
    ]
    cands.sort(key=lambda c: (c.venue, c.close_time or datetime.max.replace(tzinfo=UTC)))
    for c in cands:
        close = f"{c.close_time:%Y-%m-%d}" if c.close_time else "    -     "
        state = "closed" if c.closed else "open  "
        typer.echo(
            f"{c.venue:<10} {close} {state} vol={c.volume or 0:>10,.0f} {c.kind[:6]:<6} "
            f"{c.ref:<28} {c.question[:80]}"
        )
    typer.echo(f"\n{len(cands)} candidates. Add one with: rp registry add <venue> <ref> --group G")


@registry_app.command("add")
def registry_add(
    venue: Annotated[str, typer.Argument(help="polymarket | kalshi | manifold")],
    refs: Annotated[list[str], typer.Argument(help="Venue market id(s) or ticker(s).")],
    group: Annotated[str, typer.Option("--group", "-g", help="e.g. pregnancy, wedding")],
    entity_key: Annotated[
        list[str] | None, typer.Option("--entity-key", "-k", help="Repeatable.")
    ] = None,
) -> None:
    """Fetch full market details (incl. resolution text) and record them in the registry."""
    from rumour_pressure.registry import load_registry, save_registry
    from rumour_pressure.registry import venues as v

    reg = load_registry()
    keys = entity_key or ["Taylor Swift", "Travis Kelce"]
    for ref in refs:
        market = v.FETCH[venue](ref, group).model_copy(update={"entity_keys": keys})
        if not market.resolution_text:
            typer.echo(f"warning: {market.market_id} has no resolution text", err=True)
        reg = reg.upsert(market)
        typer.echo(f"added {market.market_id}: {market.question[:70]}")
    save_registry(reg)


@registry_app.command("sync")
def registry_sync() -> None:
    """Write the registry's markets into the warehouse `markets` table."""
    from rumour_pressure.registry import load_registry

    reg = load_registry()
    with Warehouse(config.warehouse_path()) as wh:
        n = wh.upsert(m.to_row() for m in reg.markets)
    typer.echo(f"Synced {n} markets to the warehouse.")


PRICE_SOURCES = ("manifold", "polymarket", "kalshi")


def _collect_prices(venues: tuple[str, ...], market: str | None, group: str | None) -> None:
    from importlib import import_module

    from rumour_pressure.registry import load_registry

    reg = load_registry()
    targets = [
        m
        for m in reg.markets
        if m.venue in venues
        and (market is None or m.market_id == market)
        and (group is None or m.group == group)
    ]
    if not targets:
        typer.echo("No registry markets match.")
        raise typer.Exit(code=1)
    failed = []
    with Warehouse(config.warehouse_path()) as wh:
        wh.upsert(m.to_row() for m in targets)
        for m in targets:
            try:
                rows = import_module(f"rumour_pressure.collect.{m.venue}").collect_prices(m)
            except Exception as exc:  # keep going; report at the end
                failed.append(m.market_id)
                typer.echo(f"  FAILED {m.market_id}: {exc}")
                continue
            wh.upsert(rows)
            typer.echo(f"  {m.market_id:<42} {len(rows):>6} hourly bars  {m.question[:50]}")
    typer.echo(f"Done: {len(targets) - len(failed)}/{len(targets)} markets collected.")
    if failed:
        raise typer.Exit(code=1)


@app.command()
def collect(
    source: Annotated[
        str, typer.Argument(help="prices | manifold | polymarket | kalshi | bluesky")
    ],
    market: Annotated[str | None, typer.Option("--market", help="Registry market ID.")] = None,
    group: Annotated[str | None, typer.Option("--group", help="Registry group.")] = None,
) -> None:
    """Backfill a source for registry markets. `bluesky` loads the live logger's output."""
    if source == "prices":
        _collect_prices(PRICE_SOURCES, market, group)
        return
    if source in PRICE_SOURCES:
        _collect_prices((source,), market, group)
        return
    if source == "bluesky":
        from rumour_pressure.collect.bluesky import ingest_staged

        with Warehouse(config.warehouse_path()) as wh:
            summary = ingest_staged(config.live_stage_dir("bluesky"), wh)
        typer.echo(
            f"Loaded {summary.posts} posts, applied {summary.deletions} deletions, "
            f"{summary.gaps} logger gaps on record."
        )
        return
    _not_yet("Tasks 4-10")


@app.command("bluesky-log")
def bluesky_log(
    keyword: Annotated[
        list[str] | None,
        typer.Option("--keyword", "-k", help="Phrase to match; repeatable. Defaults to config."),
    ] = None,
) -> None:
    """Run the live Bluesky logger until Ctrl-C. Load its output with `rp collect bluesky`."""
    import asyncio

    from rumour_pressure.collect.bluesky import BlueskyLogger, Matcher
    from rumour_pressure.registry import load_registry

    keywords = keyword or load_registry().live_keywords() or list(config.DEFAULT_LIVE_KEYWORDS)
    stage = config.live_stage_dir("bluesky")
    logger = BlueskyLogger(Matcher(keywords), config.author_salt(), stage)
    typer.echo(f"Logging Bluesky posts matching {keywords} to {stage}. Ctrl-C to stop.")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(logger.run())
    typer.echo(f"Stopped. Staged {logger.posts_staged} posts this session.")


@app.command()
def classify(market: MarketOpt, limit: int | None = None) -> None:
    """Classify stance of relevant posts for a market."""
    _not_yet("Task 11")


@app.command("bench-stance")
def bench_stance(n: int = 200) -> None:
    """Measure stance-classifier throughput on this machine."""
    _not_yet("Task 11")


@app.command()
def signals(
    market: Annotated[str | None, typer.Option("--market", help="Registry market ID.")] = None,
    group: Annotated[str | None, typer.Option("--group", help="Registry group.")] = None,
) -> None:
    """Detrend prices and detect jumps for registry markets (stance index: Task 14)."""
    from rumour_pressure.registry import load_registry
    from rumour_pressure.signals.run import MIN_DAYS_REMAINING, detect_for_market

    targets = [
        m
        for m in load_registry().markets
        if (market is None or m.market_id == market) and (group is None or m.group == group)
    ]
    total = qualifying = 0
    with Warehouse(config.warehouse_path()) as wh:
        for m in targets:
            res = detect_for_market(wh, m)
            total += res.n_jumps
            qualifying += res.n_qualifying
            typer.echo(
                f"  {m.market_id:<42} {m.detrend:<6} jumps={res.n_jumps:>3} "
                f"qualifying={res.n_qualifying:>3}  {m.question[:48]}"
            )
    typer.echo(
        f"Done: {total} jumps across {len(targets)} markets; {qualifying} qualify "
        f"(≥{MIN_DAYS_REMAINING:.0f} days left, not a resolution move)."
    )


@app.command("panel-count")
def panel_count(
    candidates: Annotated[str, typer.Option()] = "registry/candidates.yaml",
) -> None:
    """Count qualifying jumps across candidate markets."""
    _not_yet("Task 7")
