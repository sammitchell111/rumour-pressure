from typer.testing import CliRunner

from rumour_pressure.cli import app

runner = CliRunner()


def test_help_lists_every_command_from_the_spec():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in [
        "registry",
        "collect",
        "bluesky-log",
        "classify",
        "bench-stance",
        "signals",
        "panel-count",
        "init-db",
    ]:
        assert command in result.output


def test_init_db_creates_the_warehouse(tmp_path, monkeypatch):
    monkeypatch.setenv("RP_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["init-db"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "warehouse.duckdb").exists()


def test_unbuilt_commands_say_which_task_builds_them():
    result = runner.invoke(app, ["classify", "--market", "x"])
    assert result.exit_code != 0
    assert "Task 11" in result.output
