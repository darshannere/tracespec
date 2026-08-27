import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Session, Span, SpanType
from .otlp_receiver import MODEL_PRICES


def _epoch_ms(value) -> int:
    if isinstance(value, (int, float)):
        value = int(value)
        return value // 1_000_000 if value > 10**15 else value
    if not value:
        return 0
    timestamp = str(value).replace("Z", "+00:00")
    return int(datetime.fromisoformat(timestamp).timestamp() * 1000)


def _json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _looks_like_tool(name: str) -> bool:
    normalized = name.strip().lower().replace("-", "_")
    return normalized not in {"", "chain", "workflow", "agent", "trace", "span", "root", "run", "invoke"}


def _observation_span(observation: dict, trace_id: str, is_root: bool) -> Span:
    observation_type = str(observation.get("type", "")).upper()
    name = str(observation.get("name", ""))
    if is_root:
        span_type = SpanType.AGENT
    elif observation_type == "GENERATION":
        span_type = SpanType.LLM
    elif observation_type == "SPAN" and _looks_like_tool(name):
        span_type = SpanType.TOOL
    else:
        span_type = SpanType.CHAIN

    observation_input = observation.get("input")
    observation_output = observation.get("output")
    usage = observation.get("usage") or {}
    tokens_in = usage.get("input", usage.get("input_tokens")) if isinstance(usage, dict) else None
    tokens_out = usage.get("output", usage.get("output_tokens")) if isinstance(usage, dict) else None
    model = observation.get("model")
    attrs = {
        key: value
        for key, value in {
            "model": model,
            "input": observation_input,
            "prompt": observation_input,
            "output": observation_output,
            "usage": usage if usage else None,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": _epoch_ms(observation.get("end_time")) - _epoch_ms(observation.get("start_time")),
        }.items()
        if value is not None
    }
    if span_type == SpanType.TOOL:
        attrs["tool_name"] = name
        if observation_input is not None:
            attrs["tool_params"] = _json_value(observation_input)

    prices = MODEL_PRICES.get(model, (0.0, 0.0))
    attrs["cost_usd"] = (
        int(tokens_in or 0) / 1_000_000 * prices[0]
        + int(tokens_out or 0) / 1_000_000 * prices[1]
    )
    error = None
    if str(observation.get("level", "")).upper() == "ERROR":
        error = f"langfuse:{observation.get('status_message') or ''}"

    return Span(
        id=str(observation.get("id") or observation.get("observation_id") or name),
        trace_id=trace_id,
        parent_id=(
            str(observation["parent_observation_id"])
            if observation.get("parent_observation_id")
            else None
        ),
        type=span_type,
        name=name,
        attrs=attrs,
        start_ms=_epoch_ms(observation.get("start_time")),
        end_ms=_epoch_ms(observation.get("end_time")),
        error=error,
    )


def normalize_langfuse_trace(trace_json: dict, agent_name: str | None) -> Session:
    trace_id = str(trace_json["id"])
    observations = trace_json.get("observations") or []
    root = next(
        (observation for observation in observations if not observation.get("parent_observation_id")),
        observations[0] if observations else {},
    )
    spans = [
        _observation_span(observation, trace_id, observation is root)
        for observation in observations
    ]
    spans.sort(key=lambda span: (span.parent_id is not None, span.start_ms))
    started_at = trace_json.get("timestamp")
    if not started_at:
        started_at = datetime.fromtimestamp(
            _epoch_ms(root.get("start_time")) / 1000, timezone.utc
        ).isoformat()
    return Session(
        trace_id=trace_id,
        agent_name=agent_name or str(trace_json.get("name") or "unknown"),
        provider=trace_json.get("metadata", {}).get("provider") if isinstance(trace_json.get("metadata"), dict) else None,
        started_at=str(started_at),
        spans=spans,
    )


def import_langfuse_file(path: str, agent_name: str | None = None) -> list[Session]:
    text = Path(path).read_text()
    try:
        data = json.loads(text)
        traces = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        traces = [json.loads(line) for line in text.splitlines() if line.strip()]
    return [normalize_langfuse_trace(trace, agent_name) for trace in traces]
