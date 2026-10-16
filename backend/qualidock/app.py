import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

from .config import Settings
from .files import PathViolation, DirectoryChanged
from .manager import RunManager
from .preview import PREVIEW_PATH, application_csp, report_preview, UnsupportedPreview
from .history import page as history_page, invalidation


class SessionRequest(BaseModel):
    token: str = Field(max_length=512)


class ReadAssignment(BaseModel):
    path: str = Field(max_length=4096)
    read: Literal["R1", "R2"] | None = None
    pair_key: str | None = Field(default=None, max_length=2048)
    paired: bool = False
    mate: str | None = Field(default=None, max_length=4096)
    source: Literal["auto", "confirmed", "manual"] = "auto"
    assignment: Literal["paired", "single", "unpaired"] | None = None
    lane: str | None = Field(default=None, max_length=80)
    chunk: str | None = Field(default=None, max_length=80)


class SampleGroup(BaseModel):
    id: str = Field(max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    files: list[str] = Field(min_length=1, max_length=500)
    source: Literal["auto", "confirmed", "manual"] = "auto"


class DatasetReference(BaseModel):
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    dataset_id: str = Field(min_length=1, max_length=128)


class ReuseRequest(BaseModel):
    dataset_ids: list[str] = Field(min_length=1, max_length=500)


class SampleConfigurationRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=500)
    input_datasets: list[DatasetReference] = Field(default_factory=list, max_length=500)


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class IntegrityRequest(BaseModel):
    mode: Literal['full', 'quick'] = 'full'


class AnalysisRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    mode: Literal["both", "fastqc", "multiqc", "fastp", "seqkit-stats", "seqkit-sample", "seqkit-filter", "seqkit-extract"] = "both"
    paths: list[str] = Field(min_length=1, max_length=500)
    threads: int = Field(default=1, ge=1, le=32)
    input_pairing: list[ReadAssignment] | None = Field(default=None, max_length=500)
    sample_groups: list[SampleGroup] | None = Field(default=None, max_length=500)
    output_root: str | None = Field(default=None, max_length=4096)
    processing_options: dict | None = None
    input_datasets: list[DatasetReference] | None = Field(default=None, max_length=500)
    rerun_of: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


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
            # Sandboxed reports have an opaque Origin. Also reject cross-site
            # navigations to private APIs (ordinary attachment navigation remains
            # available to the authenticated, same-origin application).
            if request.headers.get("sec-fetch-site") == "cross-site":
                return Response("Cross-origin access denied", 403)
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
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy", application_csp(request.headers.get("host", ""), settings.prefix))
        if api:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(PathViolation)
    async def bad_path(request, exc):
        return Response(str(exc), status_code=403)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return Response("Analysis not found", status_code=404)

    @app.exception_handler(DirectoryChanged)
    async def stale_directory(request, exc):
        return Response(str(exc), status_code=409)

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
                "tools": {name: info["compatible"] for name, info in (await manager.detect_tools()).items()},
                "tool_details": manager.tool_info, "default_output": str(manager.stores.default),
                "output_locations": await asyncio.to_thread(manager.stores.listing)}

    @app.get("/api/files")
    async def files(path: str, offset: int = 0, limit: int = 500, snapshot: str | None = None, refresh: bool = False):
        if offset < 0 or not 1 <= limit <= 500:
            raise HTTPException(400, "Invalid pagination")
        return await asyncio.to_thread(manager.files.browse, path, offset, limit, snapshot, refresh)

    @app.get("/api/runs")
    async def runs():
        return manager.list()

    @app.get("/api/history")
    async def history(offset: int = 0, limit: int = 25, search: str = '', state: str = 'all', mode: str = 'all', order: str = 'created-desc', revision: int | None = None):
        if revision is not None and revision != manager.revision:
            raise HTTPException(409, 'Analysis history changed; refresh this page')
        return history_page(manager.runs, manager.revision, offset=offset, limit=limit, search=search, state=state, mode=mode, order=order)

    @app.post("/api/runs", status_code=201)
    async def create_run(body: AnalysisRequest):
        return await manager.create(body.name, body.mode, body.paths, body.threads,
                                    input_pairing=[record.model_dump(exclude_unset=True) for record in body.input_pairing] if body.input_pairing is not None else None,
                                    sample_groups=[group.model_dump() for group in body.sample_groups] if body.sample_groups is not None else None,
                                    output_root=body.output_root, rerun_of=body.rerun_of, processing_options=body.processing_options,
                                    input_datasets=[record.model_dump() for record in body.input_datasets] if body.input_datasets is not None else None)

    @app.get("/api/output-locations")
    async def output_locations():
        return await asyncio.to_thread(manager.stores.listing)

    @app.post("/api/sample-configuration")
    async def sample_configuration(body: SampleConfigurationRequest):
        return await asyncio.to_thread(manager.sample_configuration, body.paths, input_datasets=[r.model_dump() for r in body.input_datasets])

    @app.patch("/api/runs/{run_id}")
    async def rename_run(run_id: str, body: RenameRequest):
        return manager.rename(run_id, body.name)

    @app.get("/api/runs/{run_id}/configuration")
    async def run_configuration(run_id: str):
        return await asyncio.to_thread(manager.configuration, run_id)

    @app.get('/api/runs/{run_id}/datasets')
    async def derived_inputs(run_id: str):
        from .datasets import draft
        return await asyncio.to_thread(draft, manager, run_id)

    @app.post('/api/runs/{run_id}/reuse')
    async def reuse_inputs(run_id: str, body: ReuseRequest):
        from .datasets import draft
        return await asyncio.to_thread(draft, manager, run_id, body.dataset_ids)

    @app.post("/api/runs/{run_id}/multiqc", status_code=201)
    async def aggregate(run_id: str):
        source = manager.runs[run_id]
        return await manager.create(f"MultiQC · {source['name']}"[:120], "multiqc", [str(manager.directory(run_id) / "fastqc")], min(source.get("threads", 1), settings.max_threads), source_run_id=run_id, output_root=str(manager.directory(run_id).parent))

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

    @app.post('/api/runs/{run_id}/integrity', status_code=202)
    async def start_integrity(run_id: str, body: IntegrityRequest):
        return await manager.validation.start(run_id, body.mode)

    @app.post('/api/runs/{run_id}/integrity/cancel')
    async def cancel_integrity(run_id: str):
        return await manager.validation.cancel(run_id)

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
        # Downloads remain opaque attachments, including complete HTML.
        return FileResponse(artifact, media_type="application/octet-stream", filename=artifact.name, headers={"Content-Security-Policy": "sandbox; default-src 'none'"})

    @app.api_route(PREVIEW_PATH, methods=["GET", "HEAD"])
    async def preview(request: Request, run_id: str, path: str):
        if "\x00" in path or "\\" in path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise PathViolation("Invalid report artifact path")
        try:
            artifact = await asyncio.to_thread(manager.artifact, run_id, path)
        except FileNotFoundError:
            raise HTTPException(404, "The saved report is no longer available")
        except PermissionError:
            raise HTTPException(403, "The saved report is not readable")
        if artifact.suffix.lower() != ".html":
            raise HTTPException(415, "Only registered HTML reports can be previewed; download this file instead")
        try:
            return await asyncio.to_thread(report_preview, artifact,
                                           multiqc=path == "multiqc/multiqc_report.html",
                                           head=request.method == "HEAD")
        except UnsupportedPreview as exc:
            raise HTTPException(415, str(exc))
        except FileNotFoundError:
            raise HTTPException(404, "The saved report is no longer available")
        except PermissionError:
            raise HTTPException(403, "The saved report is not readable")

    @app.get("/api/events")
    async def events(request: Request, format: Literal['legacy', 'invalidation'] = 'legacy'):
        async def stream():
            revision = -1
            while not await request.is_disconnected():
                if revision != manager.revision:
                    revision = manager.revision
                    event, data = ('revision', invalidation(revision)) if format == 'invalidation' else ('runs', manager.list())
                    yield f"id: {revision}\nevent: {event}\ndata: {json.dumps(data)}\n\n"
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
