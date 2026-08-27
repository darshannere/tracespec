import dataclasses

from fastapi import APIRouter, HTTPException, Query

from ..langfuse_import import import_langfuse_api, import_langfuse_file
from ..otlp_receiver import parse_trace_json_list
from ..store import get_session, init_db, list_sessions, upsert_session


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
    conn = init_db(db_path)
    try:
        for session in sessions:
            upsert_session(conn, session)
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
        sessions = parse_trace_json_list(payload.get("records", []))
        return {"sessions": _save_sessions(db_path, sessions)}

    @router.post("/ingest/langfuse")
    def ingest_langfuse(payload: dict) -> dict:
        agent_name = payload.get("agent_name")
        if payload.get("file_path"):
            sessions = import_langfuse_file(payload["file_path"], agent_name)
        else:
            sessions = import_langfuse_api(
                payload["base_url"],
                payload["public_key"],
                payload["secret_key"],
                agent_name,
            )
        return {"sessions": _save_sessions(db_path, sessions)}

    @router.get("/traces")
    def traces(agent: str | None = None, limit: int = Query(100, ge=1)) -> list[dict]:
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
