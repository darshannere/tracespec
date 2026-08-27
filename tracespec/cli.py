import os

import typer
import uvicorn

from .server.app import create_app


DEFAULT_DB_PATH = os.getenv("TRACESPEC_DB_PATH", "tracespec.db")

app = typer.Typer(no_args_is_help=True)
ingest_app = typer.Typer(no_args_is_help=True)
gate_app = typer.Typer(no_args_is_help=True)
optimize_app = typer.Typer(no_args_is_help=True)

app.add_typer(ingest_app, name="ingest")
app.add_typer(gate_app, name="gate")
app.add_typer(optimize_app, name="optimize")


@ingest_app.command("otlp")
def ingest_otlp(
    db: str = typer.Option(DEFAULT_DB_PATH, "--db"),
    file: str = typer.Option("", "--file", "-f"),
) -> None:
    raise NotImplementedError


@ingest_app.command("langfuse")
def ingest_langfuse(
    db: str = typer.Option(DEFAULT_DB_PATH, "--db"),
    file_path: str = typer.Option("", "--file-path"),
    base_url: str = typer.Option("", "--base-url"),
    public_key: str = typer.Option("", "--public-key"),
    secret_key: str = typer.Option("", "--secret-key"),
    agent_name: str = typer.Option("", "--agent-name"),
) -> None:
    raise NotImplementedError


@app.command("distill")
def distill(
    db: str = typer.Option(DEFAULT_DB_PATH, "--db"),
    agent: str = typer.Option("", "--agent"),
    out_dir: str = typer.Option(".tracespec", "--out-dir"),
    suite: str = typer.Option("", "--suite"),
    tier: str = typer.Option("pr-smoke", "--tier"),
) -> None:
    raise NotImplementedError


@gate_app.command("run")
def gate_run(
    suite_path: str = typer.Option("", "--suite-path"),
    harness_cmd: str = typer.Option("", "--harness-cmd"),
    tier: str = typer.Option("pr-smoke", "--tier"),
    n: int = typer.Option(5, "--n"),
    mode: str = typer.Option("recorded", "--mode"),
    out_dir: str = typer.Option(".tracespec", "--out-dir"),
) -> None:
    raise NotImplementedError


@gate_app.command("lock")
def gate_lock(
    suite_path: str = typer.Option("", "--suite-path"),
    results: str = typer.Option("", "--results"),
) -> None:
    raise NotImplementedError


@optimize_app.command("propose")
def optimize_propose(
    agent: str = typer.Option("", "--agent"),
    db: str = typer.Option(DEFAULT_DB_PATH, "--db"),
) -> None:
    raise NotImplementedError


@optimize_app.command("validate")
def optimize_validate(
    proposal_id: str = typer.Option("", "--proposal-id"),
    db: str = typer.Option(DEFAULT_DB_PATH, "--db"),
    harness_cmd: str = typer.Option("", "--harness-cmd"),
) -> None:
    raise NotImplementedError


@app.command("serve")
def serve(
    db: str = typer.Option(DEFAULT_DB_PATH, "--db"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
) -> None:
    uvicorn.run(create_app(db), host=host, port=port)
