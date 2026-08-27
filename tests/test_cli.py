import pytest
from typer.testing import CliRunner

import tracespec.cli as cli


runner = CliRunner()


def test_cli_registers_task_5_command_tree():
    commands = (
        ("ingest", "otlp"),
        ("ingest", "langfuse"),
        ("distill",),
        ("gate", "run"),
        ("gate", "lock"),
        ("optimize", "propose"),
        ("optimize", "validate"),
        ("serve",),
    )

    for command in commands:
        result = runner.invoke(cli.app, [*command, "--help"])
        assert result.exit_code == 0


@pytest.mark.parametrize(
    "command",
    [
        ("ingest", "otlp"),
        ("ingest", "langfuse"),
        ("distill",),
        ("gate", "run"),
        ("gate", "lock"),
        ("optimize", "propose"),
        ("optimize", "validate"),
    ],
)
def test_later_task_commands_are_stubs(command):
    with pytest.raises(NotImplementedError):
        runner.invoke(cli.app, [*command], catch_exceptions=False)


def test_serve_builds_app_with_db_path_and_runs_uvicorn(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "create_app", lambda db_path: calls.append(("app", db_path)) or "app")
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))

    result = runner.invoke(
        cli.app,
        ["serve", "--db", "custom.db", "--host", "127.0.0.1", "--port", "9000"],
    )

    assert result.exit_code == 0
    assert calls == [
        ("app", "custom.db"),
        ("app", {"host": "127.0.0.1", "port": 9000}),
    ]
