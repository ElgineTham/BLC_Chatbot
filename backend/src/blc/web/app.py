"""The FastAPI app: chat API plus the static page."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from blc.web.answerer import Answerer
from blc.web.requests import BadRequest, parse_chat_request
from blc.web.stream import stream_answer

FRONTEND_DIR = Path(__file__).resolve().parents[4] / "frontend"
LOGO_URL = "/assets/blc_logo.png"
MANIFEST_URL = "/manifest.webmanifest"
NDJSON = "application/x-ndjson"


def create_app(answer: Answerer) -> FastAPI:
    """The web app (API + page). Calls `answer` only from POST /api/chat."""
    app = FastAPI()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")

    @app.get("/style.css")
    def stylesheet() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "style.css", media_type="text/css")

    @app.get("/app.js")
    def script() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "app.js", media_type="text/javascript")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(MANIFEST_URL)
    def manifest() -> FileResponse:
        return FileResponse(
            FRONTEND_DIR / "manifest.webmanifest", media_type="application/manifest+json"
        )

    @app.post("/api/chat")
    async def chat(request: Request):
        try:
            body = await request.json()
            question, history = parse_chat_request(body)
        except (BadRequest, ValueError) as exc:
            message = str(exc) if isinstance(exc, BadRequest) else "Body must be JSON."
            return JSONResponse({"error": message}, status_code=400)
        return StreamingResponse(stream_answer(answer, question, history), media_type=NDJSON)

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
    return app
