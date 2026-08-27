import json, tempfile
from tracespec.store import init_db, upsert_session, get_session, upsert_case, list_cases, upsert_suite, get_suite, save_run, list_runs
from tracespec.models import Session, Span, SpanType, Case, Assertion, Suite, Run, RunResult


def _session(trace_id="t1"):
    root = Span(id="r", trace_id=trace_id, parent_id=None, type=SpanType.AGENT, name="agent", attrs={}, start_ms=0, end_ms=10)
    child = Span(id="c", trace_id=trace_id, parent_id="r", type=SpanType.TOOL, name="search", attrs={"tool_name": "search"}, start_ms=1, end_ms=5, error="HTTP 500")
    return Session(trace_id=trace_id, agent_name="bot", provider="openai", started_at="2026-08-01T00:00:00Z", spans=[root, child])


def test_session_roundtrip():
    conn = init_db(tempfile.mktemp(suffix=".db"))
    upsert_session(conn, _session())
    got = get_session(conn, "t1")
    assert got is not None
    assert got.agent_name == "bot"
    assert got.root().type == SpanType.AGENT
    assert got.root().children[0].error == "HTTP 500"


def test_case_and_suite_roundtrip():
    conn = init_db(tempfile.mktemp(suffix=".db"))
    case = Case(id="bot-search-001", suite="bot", name="search-001", tier="pr-smoke",
                input={"prompt": "find RTX 5090"}, assertions=[Assertion(type="tool_call", tool="search", params={"query": "RTX 5090"})],
                source_trace_id="t1")
    upsert_case(conn, case)
    assert [c.id for c in list_cases(conn, suite="bot")] == ["bot-search-001"]
    suite = Suite(name="bot", version=1, tier="pr-smoke", case_ids=["bot-search-001"])
    upsert_suite(conn, suite)
    assert get_suite(conn, "bot", 1).case_ids == ["bot-search-001"]


def test_run_roundtrip():
    conn = init_db(tempfile.mktemp(suffix=".db"))
    run = Run(id="run1", suite="bot", tier="pr-smoke", status="pass",
              results=[RunResult(case_id="c1", passed=True, pass_rate=1.0, trials_passed=5, trials=5, cost_usd=0.01, latency_ms=100, error=None)])
    save_run(conn, run)
    assert list_runs(conn, suite="bot")[0].status == "pass"
