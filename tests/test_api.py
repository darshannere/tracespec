import json

import pytest
import httpx
from fastapi.testclient import TestClient

import tracespec.server.api as api
from tracespec.server.app import create_app
from tracespec.models import Session, Span, SpanType


def _record(trace_id="trace-1", span_id="root", parent_id=None, name="support-agent"):
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_id": parent_id,
        "name": name,
        "start_ms": 1000,
        "end_ms": 1100,
        "attributes": {"openinference.span.kind": "AGENT"},
    }


def test_health_and_otlp_trace_endpoints(tmp_path):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    assert client.get("/api/health").json() == {"status": "ok"}
    response = client.post("/api/ingest/otlp", json={"records": [_record()]})

    assert response.status_code == 200
    assert response.json() == {"sessions": 1}
    assert client.get("/api/traces").json() == [
        {
            "trace_id": "trace-1",
            "agent_name": "support-agent",
            "started_at": "1970-01-01T00:00:01+00:00",
            "verdict": "ok",
            "span_count": 1,
        }
    ]

    detail = client.get("/api/traces/trace-1")
    assert detail.status_code == 200
    assert detail.json() == {
        "trace_id": "trace-1",
        "agent_name": "support-agent",
        "provider": None,
        "started_at": "1970-01-01T00:00:01+00:00",
        "verdict": "ok",
        "spans": {
            "id": "root",
            "trace_id": "trace-1",
            "parent_id": None,
            "type": "AGENT",
            "name": "support-agent",
            "attrs": {"latency_ms": 100, "cost_usd": 0.0},
            "start_ms": 1000,
            "end_ms": 1100,
            "error": None,
            "children": [],
        },
    }


def test_trace_list_filters_agent_and_limit(tmp_path):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))
    client.post(
        "/api/ingest/otlp",
        json={"records": [_record("one", name="first"), _record("two", name="second")]},
    )

    traces = client.get("/api/traces", params={"agent": "second", "limit": 1})
    assert [trace["trace_id"] for trace in traces.json()] == ["two"]


def test_trace_detail_serializes_nested_children(tmp_path):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))
    client.post(
        "/api/ingest/otlp",
        json={
            "records": [
                _record(),
                _record(span_id="child", parent_id="root", name="search"),
            ]
        },
    )

    child = client.get("/api/traces/trace-1").json()["spans"]["children"][0]
    assert child["id"] == "child"
    assert child["parent_id"] == "root"
    assert child["name"] == "search"
    assert child["children"] == []


def test_langfuse_file_ingest(tmp_path):
    source = tmp_path / "trace.json"
    source.write_text(
        '{"id":"lf-1","name":"langfuse-agent","timestamp":"2026-08-01T00:00:00Z",'
        '"observations":[{"id":"obs-1","type":"SPAN","name":"root"}]}'
    )
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    response = client.post(
        "/api/ingest/langfuse",
        json={"file_path": str(source), "agent_name": "overridden-agent"},
    )

    assert response.status_code == 200
    assert response.json() == {"sessions": 1}
    assert client.get("/api/traces/lf-1").json()["agent_name"] == "overridden-agent"


def test_missing_trace_returns_not_found(tmp_path):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    assert client.get("/api/traces/missing").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"records": {"trace_id": "trace-1"}},
        {"records": [_record(), None]},
        {"records": [_record(), "not a record"]},
    ],
)
def test_otlp_ingest_rejects_missing_or_invalid_records(tmp_path, payload):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    response = client.post("/api/ingest/otlp", json=payload)

    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"file_path": ""},
        {"file_path": "trace.json", "base_url": "https://example.com"},
        {"base_url": "https://example.com", "public_key": "public"},
        {"base_url": "https://example.com", "public_key": "", "secret_key": "secret"},
        {"base_url": 3, "public_key": "public", "secret_key": "secret"},
    ],
)
def test_langfuse_ingest_requires_one_valid_mode(tmp_path, payload):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    response = client.post("/api/ingest/langfuse", json=payload)

    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.parametrize("path", ["missing.json", "/etc/passwd"])
def test_langfuse_file_ingest_rejects_unreadable_or_unsafe_path(tmp_path, path):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))
    file_path = path if path.startswith("/") else str(tmp_path / path)

    response = client.post("/api/ingest/langfuse", json={"file_path": file_path})

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_langfuse_file"


def test_langfuse_file_ingest_rejects_malformed_json(tmp_path):
    source = tmp_path / "malformed.json"
    source.write_text("not json")
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    response = client.post("/api/ingest/langfuse", json={"file_path": str(source)})

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_langfuse_file"


def test_langfuse_file_ingest_rejects_malformed_trace(tmp_path):
    source = tmp_path / "malformed-trace.json"
    source.write_text(json.dumps({"observations": []}))
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    response = client.post("/api/ingest/langfuse", json={"file_path": str(source)})

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_langfuse_file"


def test_langfuse_ingest_rejects_empty_trace(tmp_path):
    source = tmp_path / "empty.json"
    source.write_text(json.dumps({"id": "empty", "observations": []}))
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    response = client.post("/api/ingest/langfuse", json={"file_path": str(source)})

    assert response.status_code == 422
    assert client.get("/api/traces").json() == []


def test_otlp_ingest_rejects_cyclic_parent_relationship(tmp_path):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))
    records = [
        _record(span_id="a", parent_id="b"),
        _record(span_id="b", parent_id="a"),
    ]

    response = client.post("/api/ingest/otlp", json={"records": records})

    assert response.status_code == 422
    assert client.get("/api/traces").json() == []


def test_otlp_ingest_rejects_multiple_roots(tmp_path):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))
    records = [_record(span_id="a"), _record(span_id="b")]

    response = client.post("/api/ingest/otlp", json={"records": records})

    assert response.status_code == 422
    assert client.get("/api/traces").json() == []


def test_otlp_ingest_rejects_dangling_parent(tmp_path):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    response = client.post(
        "/api/ingest/otlp",
        json={"records": [_record(parent_id="missing")]},
    )

    assert response.status_code == 422
    assert client.get("/api/traces").json() == []


def test_trace_list_limit_has_an_upper_bound(tmp_path):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    response = client.get("/api/traces", params={"limit": 1001})

    assert response.status_code == 422


def test_in_memory_database_is_explicitly_rejected():
    with pytest.raises(ValueError, match="in-memory"):
        create_app(":memory:")


def test_batch_ingest_rolls_back_when_a_later_session_fails(tmp_path, monkeypatch):
    db_path = str(tmp_path / "tracespec.db")
    client = TestClient(create_app(db_path), raise_server_exceptions=False)
    original_upsert = api.upsert_session
    calls = 0

    def fail_on_second(conn, session, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated storage failure")
        original_upsert(conn, session, **kwargs)

    monkeypatch.setattr(api, "upsert_session", fail_on_second)
    response = client.post(
        "/api/ingest/otlp",
        json={"records": [_record("one"), _record("two")]},
    )

    assert response.status_code == 500
    assert client.get("/api/traces").json() == []


def test_langfuse_api_ingest_forwards_credentials_and_persists(monkeypatch, tmp_path):
    calls = []
    session = Session(
        trace_id="api-1",
        agent_name="api-agent",
        provider="langfuse",
        started_at="2026-08-01T00:00:00Z",
        spans=[Span("root", "api-1", None, SpanType.AGENT, "api-agent", {}, 0, 1)],
    )

    def importer(base_url, public_key, secret_key, agent_name):
        calls.append((base_url, public_key, secret_key, agent_name))
        return [session]

    monkeypatch.setattr(api, "import_langfuse_api", importer)
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    response = client.post(
        "/api/ingest/langfuse",
        json={
            "base_url": "https://langfuse.example",
            "public_key": "public",
            "secret_key": "secret",
            "agent_name": "api-agent",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"sessions": 1}
    assert calls == [("https://langfuse.example", "public", "secret", "api-agent")]
    assert client.get("/api/traces/api-1").json()["provider"] == "langfuse"


def test_langfuse_api_errors_are_structured(monkeypatch, tmp_path):
    def importer(**kwargs):
        raise httpx.HTTPError("offline")

    monkeypatch.setattr(api, "import_langfuse_api", importer)
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))

    response = client.post(
        "/api/ingest/langfuse",
        json={
            "base_url": "https://langfuse.example",
            "public_key": "public",
            "secret_key": "secret",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "langfuse_api_error"


def test_dashboard_fallback_returns_build_hint(tmp_path):
    response = TestClient(create_app(str(tmp_path / "tracespec.db"))).get("/")

    assert response.status_code == 200
    assert "hint" in response.json()
