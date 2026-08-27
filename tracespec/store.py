import dataclasses
import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import yaml

from .models import (
    Assertion,
    Case,
    Cluster,
    Proposal,
    Run,
    RunResult,
    Session,
    Span,
    SpanType,
    Suite,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
    trace_id TEXT PRIMARY KEY,
    agent_name TEXT,
    provider TEXT,
    started_at TEXT,
    verdict TEXT,
    spans_json TEXT
);
CREATE TABLE IF NOT EXISTS clusters(
    id TEXT PRIMARY KEY,
    agent_name TEXT,
    signature TEXT,
    label TEXT,
    count INTEGER,
    trace_ids_json TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS cases(
    id TEXT PRIMARY KEY,
    suite TEXT,
    name TEXT,
    tier TEXT,
    input_json TEXT,
    assertions_json TEXT,
    source_trace_id TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS suites(
    name TEXT,
    version INTEGER,
    tier TEXT,
    case_ids_json TEXT,
    baseline_json TEXT,
    created_at TEXT,
    PRIMARY KEY(name, version)
);
CREATE TABLE IF NOT EXISTS runs(
    id TEXT PRIMARY KEY,
    suite TEXT,
    tier TEXT,
    status TEXT,
    results_json TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS proposals(
    id TEXT PRIMARY KEY,
    patch_json TEXT,
    status TEXT,
    verdict_json TEXT,
    created_at TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, default=lambda item: item.value if isinstance(item, Enum) else item)


def _span_dict(span: Span) -> dict:
    data = dataclasses.asdict(span)
    data["type"] = span.type.value
    data.pop("children", None)
    return data


def _span(data: dict) -> Span:
    return Span(**{**data, "type": SpanType(data["type"])})


def _session(data: sqlite3.Row | tuple) -> Session:
    trace_id, agent_name, provider, started_at, verdict, spans_json = data
    return Session(
        trace_id=trace_id,
        agent_name=agent_name,
        provider=provider,
        started_at=started_at,
        spans=[_span(span) for span in json.loads(spans_json)],
        verdict=verdict,
    )


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_session(conn: sqlite3.Connection, session: Session, commit: bool = True) -> None:
    conn.execute(
        """INSERT INTO sessions(trace_id, agent_name, provider, started_at, verdict, spans_json)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(trace_id) DO UPDATE SET agent_name=excluded.agent_name,
             provider=excluded.provider, started_at=excluded.started_at,
             verdict=excluded.verdict, spans_json=excluded.spans_json""",
        (session.trace_id, session.agent_name, session.provider, session.started_at,
         session.verdict, _json([_span_dict(span) for span in session.spans])),
    )
    if commit:
        conn.commit()


def list_sessions(conn: sqlite3.Connection, agent_name: str | None = None, limit: int = 100) -> list[Session]:
    if agent_name is None:
        rows = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE agent_name = ? ORDER BY started_at DESC LIMIT ?",
            (agent_name, limit),
        ).fetchall()
    return [_session(row) for row in rows]


def get_session(conn: sqlite3.Connection, trace_id: str) -> Session | None:
    row = conn.execute("SELECT * FROM sessions WHERE trace_id = ?", (trace_id,)).fetchone()
    return _session(row) if row else None


def upsert_cluster(conn: sqlite3.Connection, cluster: Cluster) -> None:
    conn.execute(
        """INSERT INTO clusters(id, agent_name, signature, label, count, trace_ids_json, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET agent_name=excluded.agent_name,
             signature=excluded.signature, label=excluded.label, count=excluded.count,
             trace_ids_json=excluded.trace_ids_json, updated_at=excluded.updated_at""",
        (cluster.id, cluster.agent_name, cluster.signature, cluster.label, cluster.count,
         _json(cluster.trace_ids), _now()),
    )
    conn.commit()


def list_clusters(conn: sqlite3.Connection, agent_name: str | None = None) -> list[Cluster]:
    if agent_name is None:
        rows = conn.execute("SELECT id, agent_name, signature, label, count, trace_ids_json FROM clusters").fetchall()
    else:
        rows = conn.execute(
            "SELECT id, agent_name, signature, label, count, trace_ids_json FROM clusters WHERE agent_name = ?",
            (agent_name,),
        ).fetchall()
    return [Cluster(*row[:4], count=row[4], trace_ids=json.loads(row[5])) for row in rows]


def upsert_case(conn: sqlite3.Connection, case: Case) -> None:
    conn.execute(
        """INSERT INTO cases(id, suite, name, tier, input_json, assertions_json, source_trace_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET suite=excluded.suite, name=excluded.name,
             tier=excluded.tier, input_json=excluded.input_json,
             assertions_json=excluded.assertions_json, source_trace_id=excluded.source_trace_id""",
        (case.id, case.suite, case.name, case.tier, _json(case.input),
         _json([dataclasses.asdict(assertion) for assertion in case.assertions]),
         case.source_trace_id, _now()),
    )
    conn.commit()


def _case(row: tuple) -> Case:
    case_id, suite, name, tier, input_json, assertions_json, source_trace_id = row[:7]
    return Case(
        id=case_id,
        suite=suite,
        name=name,
        tier=tier,
        input=json.loads(input_json),
        assertions=[Assertion(**assertion) for assertion in json.loads(assertions_json)],
        source_trace_id=source_trace_id,
    )


def list_cases(conn: sqlite3.Connection, suite: str | None = None, tier: str | None = None) -> list[Case]:
    query = "SELECT id, suite, name, tier, input_json, assertions_json, source_trace_id FROM cases"
    params: list[object] = []
    conditions = []
    if suite is not None:
        conditions.append("suite = ?")
        params.append(suite)
    if tier is not None:
        conditions.append("tier = ?")
        params.append(tier)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id"
    return [_case(row) for row in conn.execute(query, params).fetchall()]


def upsert_suite(conn: sqlite3.Connection, suite: Suite) -> None:
    conn.execute(
        """INSERT INTO suites(name, version, tier, case_ids_json, baseline_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(name, version) DO UPDATE SET tier=excluded.tier,
             case_ids_json=excluded.case_ids_json, baseline_json=excluded.baseline_json""",
        (suite.name, suite.version, suite.tier, _json(suite.case_ids), _json(suite.baseline), _now()),
    )
    conn.commit()


def get_suite(conn: sqlite3.Connection, name: str, version: int | None = None) -> Suite | None:
    if version is None:
        row = conn.execute("SELECT * FROM suites WHERE name = ? ORDER BY version DESC LIMIT 1", (name,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM suites WHERE name = ? AND version = ?", (name, version)).fetchone()
    if not row:
        return None
    return Suite(row[0], row[1], row[2], json.loads(row[3]), json.loads(row[4]))


def save_run(conn: sqlite3.Connection, run: Run) -> None:
    conn.execute(
        """INSERT INTO runs(id, suite, tier, status, results_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET suite=excluded.suite, tier=excluded.tier,
             status=excluded.status, results_json=excluded.results_json""",
        (run.id, run.suite, run.tier, run.status,
         _json([dataclasses.asdict(result) for result in run.results]), _now()),
    )
    conn.commit()


def list_runs(conn: sqlite3.Connection, suite: str | None = None, limit: int = 50) -> list[Run]:
    if suite is None:
        rows = conn.execute("SELECT id, suite, tier, status, results_json FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, suite, tier, status, results_json FROM runs WHERE suite = ? ORDER BY created_at DESC LIMIT ?",
            (suite, limit),
        ).fetchall()
    return [Run(row[0], row[1], row[2], row[3], [RunResult(**result) for result in json.loads(row[4])]) for row in rows]


def upsert_proposal(conn: sqlite3.Connection, proposal: Proposal) -> None:
    conn.execute(
        """INSERT INTO proposals(id, patch_json, status, verdict_json, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET patch_json=excluded.patch_json,
             status=excluded.status, verdict_json=excluded.verdict_json""",
        (proposal.id, _json(proposal.patch), proposal.status, _json(proposal.verdict), _now()),
    )
    conn.commit()


def list_proposals(conn: sqlite3.Connection, status: str | None = None) -> list[Proposal]:
    if status is None:
        rows = conn.execute("SELECT id, patch_json, status, verdict_json FROM proposals ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT id, patch_json, status, verdict_json FROM proposals WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    return [Proposal(row[0], json.loads(row[1]), row[2], json.loads(row[3])) for row in rows]


def import_suite_yaml(path: str) -> Suite:
    with Path(path).open() as file:
        data = yaml.safe_load(file) or {}
    return Suite(
        name=data["name"],
        version=data["version"],
        tier=data["tier"],
        case_ids=data.get("cases", []),
        baseline=data.get("baseline", {}),
    )


def export_suite_yaml(suite: Suite, cases: list[Case], path: str) -> None:
    del cases
    data = {
        "name": suite.name,
        "version": suite.version,
        "tier": suite.tier,
        "baseline": suite.baseline,
        "cases": suite.case_ids,
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as file:
        yaml.safe_dump(data, file, sort_keys=False)
