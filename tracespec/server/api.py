import dataclasses
import tempfile
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..langfuse_import import import_langfuse_api, import_langfuse_file
from ..otlp_receiver import parse_trace_json_list
from ..store import get_session, init_db, list_sessions, upsert_session

MAX_TRACE_LIMIT = 1000
LANGFUSE_API_FIELDS = ("base_url", "public_key", "secret_key")
IMPORT_ERRORS = (OSError, TypeError, ValueError, KeyError, AttributeError, IndexError, OverflowError)


def _unprocessable(error: str, message: str) -> NoReturn:
    raise HTTPException(status_code=422, detail={"error": error, "message": message})


def _validate_session(session) -> None:
    if not session.spans:
        _unprocessable("invalid_session", "session must contain at least one span")

    by_id = {}
    for span in session.spans:
        if not span.id or span.id in by_id:
            _unprocessable("invalid_session", "session spans must have unique non-empty ids")
        by_id[span.id] = span

    if any(span.parent_id is not None and span.parent_id not in by_id for span in session.spans):
        _unprocessable("invalid_session", "session span parents must reference an existing span")
    roots = [span for span in session.spans if span.parent_id is None]
    if len(roots) != 1:
        _unprocessable("invalid_session", "session must contain exactly one root span")

    for span in session.spans:
        seen = set()
        current = span
        while current.parent_id in by_id:
            if current.id in seen:
                _unprocessable("invalid_session", "session span parents must not contain cycles")
            seen.add(current.id)
            current = by_id[current.parent_id]


def _validate_sessions(sessions) -> None:
    for session in sessions:
        _validate_session(session)


def _safe_file_path(file_path: str) -> str:
    try:
        path = Path(file_path).expanduser().resolve()
        allowed_roots = (
            Path.cwd().resolve(),
            Path(__file__).resolve().parents[2],
            Path(tempfile.gettempdir()).resolve(),
        )
    except (OSError, RuntimeError, TypeError):
        _unprocessable("invalid_langfuse_file", "file_path is not readable")
    if not any(path == root or root in path.parents for root in allowed_roots):
        _unprocessable("invalid_langfuse_file", "file_path is outside the allowed import directories")
    return str(path)


def _langfuse_mode(payload: dict) -> tuple[str, dict]:
    file_mode = "file_path" in payload
    api_mode = any(field in payload for field in LANGFUSE_API_FIELDS)
    if file_mode and api_mode:
        _unprocessable("invalid_langfuse_request", "choose exactly one Langfuse input mode")

    agent_name = payload.get("agent_name")
    if agent_name is not None and (not isinstance(agent_name, str) or not agent_name.strip()):
        _unprocessable("invalid_langfuse_request", "agent_name must be a non-empty string")

    if file_mode:
        file_path = payload["file_path"]
        if not isinstance(file_path, str) or not file_path.strip():
            _unprocessable("invalid_langfuse_request", "file_path must be a non-empty string")
        return "file", {"file_path": _safe_file_path(file_path), "agent_name": agent_name}

    if not api_mode:
        _unprocessable("invalid_langfuse_request", "provide file_path or all Langfuse API credentials")
    if any(
        not isinstance(payload.get(field), str) or not payload[field].strip()
        for field in LANGFUSE_API_FIELDS
    ):
        _unprocessable("invalid_langfuse_request", "Langfuse API credentials must be non-empty strings")
    parsed_url = urlparse(payload["base_url"])
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        _unprocessable("invalid_langfuse_request", "base_url must be an http(s) URL")
    return "api", {
        "base_url": payload["base_url"],
        "public_key": payload["public_key"],
        "secret_key": payload["secret_key"],
        "agent_name": agent_name,
    }


def _span_json(span) -> dict:
    data = dataclasses.asdict(span)
    data["type"] = span.type.value
    data["children"] = [_span_json(child) for child in span.children]
    return data


def _session_json(session) -> dict:
    return {
        "trace_id": session.trace_id,
        "agent_name": session.agent_name,
        "provider": session.provider,
        "started_at": session.started_at,
        "verdict": session.verdict,
        "spans": _span_json(session.root()),
    }


def _save_sessions(db_path: str, sessions) -> int:
    _validate_sessions(sessions)
    conn = init_db(db_path)
    try:
        conn.execute("BEGIN")
        for session in sessions:
            upsert_session(conn, session, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return len(sessions)


def create_router(db_path: str) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @router.post("/ingest/otlp")
    def ingest_otlp(payload: dict) -> dict:
        records = payload.get("records")
        if "records" not in payload or not isinstance(records, list) or any(
            not isinstance(record, dict) for record in records
        ):
            _unprocessable("invalid_otlp_request", "records must be a list of objects")
        try:
            sessions = parse_trace_json_list(records)
        except (TypeError, ValueError, KeyError, AttributeError):
            _unprocessable("invalid_otlp_request", "records contain an invalid trace span")
        return {"sessions": _save_sessions(db_path, sessions)}

    @router.post("/ingest/langfuse")
    def ingest_langfuse(payload: dict) -> dict:
        mode, values = _langfuse_mode(payload)
        try:
            if mode == "file":
                sessions = import_langfuse_file(values["file_path"], values["agent_name"])
            else:
                sessions = import_langfuse_api(**values)
        except IMPORT_ERRORS:
            _unprocessable("invalid_langfuse_file", "Langfuse file is missing, unreadable, or malformed")
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail={"error": "langfuse_api_error", "message": "Langfuse API request failed"},
            ) from exc
        return {"sessions": _save_sessions(db_path, sessions)}

    @router.get("/traces")
    def traces(agent: str | None = None, limit: int = Query(100, ge=1, le=MAX_TRACE_LIMIT)) -> list[dict]:
        conn = init_db(db_path)
        try:
            sessions = list_sessions(conn, agent_name=agent, limit=limit)
        finally:
            conn.close()
        return [
            {
                "trace_id": session.trace_id,
                "agent_name": session.agent_name,
                "started_at": session.started_at,
                "verdict": session.verdict,
                "span_count": len(session.spans),
            }
            for session in sessions
        ]

    @router.get("/traces/{trace_id}")
    def trace(trace_id: str) -> dict:
        conn = init_db(db_path)
        try:
            session = get_session(conn, trace_id)
        finally:
            conn.close()
        if session is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return _session_json(session)

    return router
