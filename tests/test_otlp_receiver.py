import json
from pathlib import Path

from tracespec.models import SpanType
from tracespec.otlp_receiver import detect_dialect, map_json_span, parse_trace_json_list


FIXTURES = Path(__file__).parent / "fixtures"


def _records(name):
    with (FIXTURES / name).open() as file:
        return [json.loads(line) for line in file]


def test_openinference_parse():
    records = _records("openinference.jsonl")
    sessions = parse_trace_json_list(records)
    session = sessions[0]

    assert session.agent_name == "support-bot"
    assert session.root().type == SpanType.AGENT
    assert session.root().children[0].type == SpanType.LLM
    tool = session.root().children[1]
    assert tool.type == SpanType.TOOL
    assert tool.error == "HTTP 500"
    assert tool.attrs["tool_name"] == "search_catalog"


def test_genai_parse_matches_openinference():
    openinference = parse_trace_json_list(_records("openinference.jsonl"))[0]
    genai = parse_trace_json_list(_records("genai.jsonl"))[0]
    openinference_tool = openinference.root().children[1]
    genai_tool = genai.root().children[1]

    assert openinference_tool.type == genai_tool.type == SpanType.TOOL
    assert openinference_tool.error == genai_tool.error == "HTTP 500"
    assert openinference_tool.attrs["tool_name"] == genai_tool.attrs["tool_name"]
    assert openinference.agent_name == genai.agent_name == "support-bot"


def test_dialect_detection_and_canonical_mapping():
    openinference = _records("openinference.jsonl")[1]
    genai = _records("genai.jsonl")[1]

    assert detect_dialect(openinference) == "openinference"
    assert detect_dialect(genai) == "genai"

    span = map_json_span(openinference)
    assert span.attrs["model"] == "gpt-4o-mini"
    assert span.attrs["prompt"] == "Find the replacement filter"
    assert span.attrs["output"] == "I will search the catalog."
    assert span.attrs["tokens_in"] == 100
    assert span.attrs["tokens_out"] == 40
    assert span.attrs["latency_ms"] == 500
    assert span.start_ms == 1722470400100
