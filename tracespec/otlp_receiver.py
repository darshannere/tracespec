import json
from datetime import datetime, timezone

from .models import Session, Span, SpanType


MODEL_PRICES = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "claude-3-5-sonnet": (3.0, 15.0),
}


def _attributes(record: dict) -> dict:
    attributes = record.get("attributes") or {}
    if isinstance(attributes, dict):
        return {key: _value(value) for key, value in attributes.items()}
    return {
        item["key"]: _value(item.get("value"))
        for item in attributes
        if isinstance(item, dict) and "key" in item
    }


def _value(value):
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "intValue", "doubleValue", "boolValue", "bytesValue"):
        if key in value:
            return value[key]
    return value


def _attr(record: dict, attrs: dict, *keys: str):
    for key in keys:
        if key in attrs:
            return attrs[key]
        if key in record:
            return record[key]
    return None


def _number(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _epoch_ms(value) -> int:
    timestamp = _number(value)
    return timestamp // 1_000_000 if timestamp > 10**15 else timestamp


def _span_type(record: dict, attrs: dict) -> SpanType:
    kind = _attr(record, attrs, "openinference.span.kind")
    if kind is not None:
        try:
            return SpanType(str(kind).upper())
        except ValueError:
            return SpanType.UNKNOWN

    operation = _attr(record, attrs, "gen_ai.operation.name")
    return {
        "create_agent": SpanType.AGENT,
        "invoke_agent_client": SpanType.CHAIN,
        "invoke_agent_internal": SpanType.CHAIN,
        "invoke_workflow": SpanType.CHAIN,
        "execute_tool": SpanType.TOOL,
        "generate_content": SpanType.LLM,
    }.get(operation, SpanType.UNKNOWN)


def detect_dialect(record: dict) -> str:
    attrs = _attributes(record)
    if _attr(record, attrs, "openinference.span.kind") is not None:
        return "openinference"
    if _attr(record, attrs, "gen_ai.operation.name") is not None:
        return "genai"
    return "unknown"


def map_json_span(record: dict) -> Span:
    attrs = _attributes(record)
    start_ms = _epoch_ms(_attr(record, attrs, "start_time_unix_nano", "startTimeUnixNano", "start_ms"))
    end_ms = _epoch_ms(_attr(record, attrs, "end_time_unix_nano", "endTimeUnixNano", "end_ms"))
    model = _attr(record, attrs, "llm.model_name", "gen_ai.request.model")
    tokens_in = _attr(record, attrs, "llm.token_count.prompt", "gen_ai.usage.input_tokens")
    tokens_out = _attr(record, attrs, "llm.token_count.completion", "gen_ai.usage.output_tokens")
    tool_name = _attr(record, attrs, "openinference.tool.name", "llm.tool_name", "gen_ai.tool.name")
    prompt = _attr(record, attrs, "input.value", "gen_ai.input")
    output = _attr(record, attrs, "output.value", "gen_ai.output")

    canonical = {}
    for key, value in (
        ("model", model),
        ("tool_name", tool_name),
        ("prompt", prompt),
        ("output", output),
        ("tokens_in", _number(tokens_in) if tokens_in is not None else None),
        ("tokens_out", _number(tokens_out) if tokens_out is not None else None),
        ("latency_ms", end_ms - start_ms),
    ):
        if value is not None:
            canonical[key] = value

    if isinstance(prompt, dict):
        canonical["tool_params"] = prompt
    elif isinstance(prompt, str):
        try:
            parsed_prompt = json.loads(prompt)
        except json.JSONDecodeError:
            parsed_prompt = None
        if isinstance(parsed_prompt, dict):
            canonical["tool_params"] = parsed_prompt

    price = MODEL_PRICES.get(model, (0.0, 0.0))
    canonical["cost_usd"] = (
        canonical.get("tokens_in", 0) / 1_000_000 * price[0]
        + canonical.get("tokens_out", 0) / 1_000_000 * price[1]
    )

    status = record.get("status", {})
    status_code = status.get("code") if isinstance(status, dict) else status
    error = _attr(
        record,
        attrs,
        "error.type",
        "gen_ai.error.type",
        "exception.type",
        "error.message",
        "gen_ai.error.message",
        "exception.message",
    )
    if error is None and status_code not in (None, "OK", "STATUS_CODE_OK", 0, 1, "0", "1"):
        error = status.get("message") if isinstance(status, dict) else None
        error = error or str(status_code)

    trace_id = _attr(record, attrs, "trace_id", "traceId", "gen_ai.conversation.id", "trace.trace_id")
    span_id = _attr(record, attrs, "span_id", "spanId", "id")
    parent_id = _attr(record, attrs, "parent_id", "parent_span_id", "parentSpanId", "parentId")

    return Span(
        id=str(span_id or ""),
        trace_id=str(trace_id or ""),
        parent_id=str(parent_id) if parent_id else None,
        type=_span_type(record, attrs),
        name=str(record.get("name", "")),
        attrs=canonical,
        start_ms=start_ms,
        end_ms=end_ms,
        error=str(error) if error is not None else None,
    )


def _trace_id(record: dict) -> str | None:
    attrs = _attributes(record)
    value = _attr(record, attrs, "trace_id", "traceId", "gen_ai.conversation.id", "trace.trace_id")
    return str(value) if value else None


def _group_records(records: list[dict]) -> list[tuple[str, list[dict]]]:
    groups: dict[str, list[dict]] = {}
    current: str | None = None
    fallback_number = 0
    for record in records:
        trace_id = _trace_id(record)
        parent_id = _attr(record, _attributes(record), "parent_id", "parent_span_id", "parentSpanId", "parentId")
        if trace_id is None:
            if not parent_id:
                fallback_number += 1
                current = f"trace-{fallback_number}"
            trace_id = current or "trace-1"
        current = trace_id
        groups.setdefault(trace_id, []).append(record)
    return list(groups.items())


def parse_trace_json_list(records: list[dict]) -> list[Session]:
    sessions = []
    for trace_id, group in _group_records(records):
        spans = [map_json_span(record) for record in group]
        for span in spans:
            span.trace_id = trace_id
        spans.sort(key=lambda span: (span.parent_id is not None, span.start_ms))
        root = spans[0]
        root_record = next(
            (record for record in group if not _attr(record, _attributes(record), "parent_id", "parent_span_id", "parentSpanId", "parentId")),
            group[0],
        )
        root_attrs = _attributes(root_record)
        provider = root_attrs.get("llm.provider") or root_attrs.get("gen_ai.system")
        started_at = datetime.fromtimestamp(root.start_ms / 1000, timezone.utc).isoformat()
        sessions.append(Session(trace_id, root.name, provider, started_at, spans))
    return sessions
