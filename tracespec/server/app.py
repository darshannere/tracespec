from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..store import init_db
from .api import create_router


def create_app(db_path: str) -> FastAPI:
    init_db(db_path).close()
    app = FastAPI()
    app.include_router(create_router(db_path))

    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="dashboard")
    else:
        @app.get("/")
        def dashboard_fallback() -> JSONResponse:
            return JSONResponse(
                {
                    "hint": "Dashboard build not found. Run npm --prefix web run build.",
                }
            )

    return app
