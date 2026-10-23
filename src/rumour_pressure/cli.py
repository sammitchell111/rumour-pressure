"""`rp` command-line interface. Commands not yet built say which task builds them."""

import contextlib
import logging
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
def registry_find(entity: Annotated[str, typer.Option("--entity")]) -> None:
    """Search venues for long-horizon markets about an entity."""
    _not_yet("Task 3")


@app.command()
def collect(
    source: Annotated[str, typer.Argument(help="Source name, or 'all'.")],
    market: Annotated[str | None, typer.Option("--market", help="Market ID.")] = None,
    since: Annotated[str | None, typer.Option(help="YYYY-MM-DD")] = None,
) -> None:
    """Backfill one source (or all) for a market. `bluesky` loads the live logger's output."""
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

    keywords = keyword or list(config.DEFAULT_LIVE_KEYWORDS)
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
def signals(market: MarketOpt) -> None:
    """Detrend prices, detect jumps and build the stance index."""
    _not_yet("Task 6")


@app.command("panel-count")
def panel_count(
    candidates: Annotated[str, typer.Option()] = "registry/candidates.yaml",
) -> None:
    """Count qualifying jumps across candidate markets."""
    _not_yet("Task 7")
