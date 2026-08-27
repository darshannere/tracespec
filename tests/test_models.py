from tracespec.models import Span, SpanType, Session


def test_span_tree():
    root = Span(id="r", trace_id="t", parent_id=None, type=SpanType.AGENT, name="agent", attrs={}, start_ms=0, end_ms=10)
    child = Span(id="c", trace_id="t", parent_id="r", type=SpanType.TOOL, name="search", attrs={}, start_ms=1, end_ms=5)
    s = Session(trace_id="t", agent_name="bot", provider=None, started_at="2026-08-01T00:00:00Z", spans=[root, child])
    assert s.root() is root
    assert len(root.children) == 1
    assert root.children[0] is child
    assert root.depth() == 1
