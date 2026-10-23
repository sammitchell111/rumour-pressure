"""`rp` command-line interface. Commands not yet built say which task builds them."""

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
    market: MarketOpt,
    since: Annotated[str | None, typer.Option(help="YYYY-MM-DD")] = None,
) -> None:
    """Backfill one source (or all) for a market."""
    _not_yet("Tasks 4-10")


@app.command("bluesky-log")
def bluesky_log() -> None:
    """Run the live Bluesky logger (long-running)."""
    _not_yet("Task 2")


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
