import json
from pathlib import Path

from tracespec.langfuse_import import import_langfuse_file
from tracespec.models import SpanType
from tracespec.otlp_receiver import parse_trace_json_list


FIXTURES = Path(__file__).parent / "fixtures"


def test_langfuse_file_import():
    sessions = import_langfuse_file(str(FIXTURES / "langfuse.jsonl"))

    assert len(sessions) == 1
    session = sessions[0]
    assert session.agent_name == "support-bot"
    assert session.root().type == SpanType.AGENT
    assert session.root().children[0].type == SpanType.LLM
    tool = session.root().children[1]
    assert tool.type == SpanType.TOOL
    assert tool.attrs["tool_name"] == "search_catalog"
    assert tool.attrs["tool_params"] == {"query": "replacement filter"}
    assert tool.error == "langfuse:HTTP 500"
    assert session.root().children[0].attrs["tokens_in"] == 100
    assert session.root().children[0].attrs["tokens_out"] == 40


def test_langfuse_json_list_import_with_agent_override(tmp_path):
    source = tmp_path / "traces.json"
    trace = json.loads((FIXTURES / "langfuse.jsonl").read_text())
    source.write_text(json.dumps([trace]))

    sessions = import_langfuse_file(str(source), agent_name="renamed-agent")

    assert sessions[0].agent_name == "renamed-agent"


def test_langfuse_roundtrip_matches_otlp_tool():
    langfuse_tool = import_langfuse_file(str(FIXTURES / "langfuse.jsonl"))[0].root().children[1]
    otlp_records = [
        json.loads(line)
        for line in (FIXTURES / "langfuse_otlp_twin.jsonl").read_text().splitlines()
    ]
    otlp_tool = parse_trace_json_list(otlp_records)[0].root().children[1]

    assert langfuse_tool.attrs["tool_name"] == otlp_tool.attrs["tool_name"]
    assert langfuse_tool.attrs["tool_params"] == otlp_tool.attrs["tool_params"]
    assert langfuse_tool.error == "langfuse:HTTP 500"
    assert otlp_tool.error == "HTTP 500"
