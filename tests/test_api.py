from fastapi.testclient import TestClient

from tracespec.server.app import create_app


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
    assert detail.json()["trace_id"] == "trace-1"
    assert detail.json()["spans"]["id"] == "root"
    assert detail.json()["spans"]["type"] == "AGENT"


def test_trace_list_filters_agent_and_limit(tmp_path):
    client = TestClient(create_app(str(tmp_path / "tracespec.db")))
    client.post(
        "/api/ingest/otlp",
        json={"records": [_record("one", name="first"), _record("two", name="second")]},
    )

    traces = client.get("/api/traces", params={"agent": "second", "limit": 1})
    assert [trace["trace_id"] for trace in traces.json()] == ["two"]


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
