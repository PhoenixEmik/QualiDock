import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

from .config import Settings
from .files import PathViolation
from .manager import RunManager


class SessionRequest(BaseModel):
    token: str = Field(max_length=512)


class AnalysisRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    mode: Literal["both", "fastqc", "multiqc"] = "both"
    paths: list[str] = Field(min_length=1, max_length=500)
    threads: int = Field(default=1, ge=1, le=32)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    manager = RunManager(settings)
    session = secrets.token_urlsafe(32)
    cookie = "qualidock_" + hashlib.sha256(settings.prefix.encode()).hexdigest()[:12]

    @asynccontextmanager
    async def lifespan(app):
        if hasattr(os, "geteuid") and os.geteuid() == 0 and not settings.allow_root:
            raise RuntimeError("QualiDock must run under a regular Unix user, never root")
        manager.start()
        try:
            yield
        finally:
            await manager.close()

    app = FastAPI(title="QualiDock", version="0.1.0.dev0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager
    app.state.settings = settings

    @app.middleware("http")
    async def protect(request: Request, call_next):
        # /node retains its prefix. /rnode strips it. Accept both layouts while generating relative URLs.
        path = request.scope["path"]
        if settings.prefix and (path == settings.prefix or path.startswith(settings.prefix + "/")):
            request.scope["path"] = path[len(settings.prefix):] or "/"
            request.scope["root_path"] = settings.prefix
            request.scope["raw_path"] = request.scope["path"].encode()
        api = request.scope["path"].startswith("/api/")
        if api:
            origin = request.headers.get("origin")
            # Browser mutations always require a custom header; cross-origin forms cannot supply it.
            if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("x-qualidock-request") != "1":
                return Response("Missing request header", 403)
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return Response("Cross-origin access denied", 403)
            if request.scope["path"] != "/api/session":
                bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
                authenticated = secrets.compare_digest(request.cookies.get(cookie, ""), session) or secrets.compare_digest(bearer, settings.token)
                if not authenticated:
                    return Response("Session authentication required", 401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        if api:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(PathViolation)
    async def bad_path(request, exc):
        return Response(str(exc), status_code=403)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return Response("Analysis not found", status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return Response(str(exc), status_code=400)

    @app.post("/api/session")
    async def login(body: SessionRequest, response: Response):
        if not secrets.compare_digest(body.token, settings.token):
            raise HTTPException(401, "Invalid session token")
        response.set_cookie(cookie, session, httponly=True, samesite="strict", secure=settings.secure_cookie, path=(settings.prefix or "") + "/")
        return {"authenticated": True}

    @app.delete("/api/session")
    async def logout(response: Response):
        response.delete_cookie(cookie, path=(settings.prefix or "") + "/")
        return {"authenticated": False}

    @app.get("/api/config")
    async def config():
        return {"roots": [str(p) for p in manager.files.roots], "cpus": settings.cpus,
                "memory_mb": settings.memory_mb, "max_threads": settings.max_threads, "prefix": settings.prefix,
                "tools": {"fastqc": shutil.which(settings.fastqc) is not None, "multiqc": shutil.which(settings.multiqc) is not None}}

    @app.get("/api/files")
    async def files(path: str, offset: int = 0, limit: int = 500):
        if offset < 0 or not 1 <= limit <= 500:
            raise HTTPException(400, "Invalid pagination")
        return manager.files.browse(path, offset, limit)

    @app.get("/api/runs")
    async def runs():
        return manager.list()

    @app.post("/api/runs", status_code=201)
    async def create_run(body: AnalysisRequest):
        return manager.create(body.name, body.mode, body.paths, body.threads)

    @app.get("/api/runs/{run_id}")
    async def run(run_id: str):
        return manager.runs[run_id]

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id: str):
        return await manager.cancel(run_id)

    @app.get("/api/runs/{run_id}/metrics")
    async def metrics(run_id: str):
        path = manager.directory(run_id) / "metrics.json"
        if not path.exists():
            return {"schema_version": 1, "samples": []}
        if path.is_symlink():
            raise PathViolation("Metrics are unavailable")
        return json.loads(path.read_text())

    @app.get("/api/runs/{run_id}/logs")
    async def logs(run_id: str, offset: int = 0):
        path = manager.directory(run_id) / "analysis.log"
        if path.is_symlink():
            raise PathViolation("Log is unavailable")
        with path.open("rb") as stream:
            stream.seek(max(0, offset))
            content = stream.read(128 * 1024)
            return {"text": content.decode("utf-8", errors="replace"), "offset": stream.tell(), "size": path.stat().st_size}

    @app.get("/api/runs/{run_id}/download")
    async def download(run_id: str, path: str):
        artifact = manager.artifact(run_id, path)
        # All artifacts are attachments, including complete HTML. No HTML is embedded in the UI.
        return FileResponse(artifact, media_type="application/octet-stream", filename=artifact.name, headers={"Content-Security-Policy": "sandbox; default-src 'none'"})

    @app.get("/api/events")
    async def events(request: Request):
        async def stream():
            revision = -1
            while not await request.is_disconnected():
                if revision != manager.revision:
                    revision = manager.revision
                    yield f"id: {revision}\nevent: runs\ndata: {json.dumps(manager.list())}\n\n"
                else:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})

    if settings.frontend.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend, html=True), name="frontend")
    else:
        @app.get("/")
        async def no_frontend():
            return Response("Build the frontend with: cd frontend && npm install && npm run build", 503)
    return app
