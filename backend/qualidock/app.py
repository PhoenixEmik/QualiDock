import asyncio
import base64
from contextlib import asynccontextmanager
from copy import deepcopy
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
from .delivery import export_data, csv_export, expected_template


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


class SampleConfigurationRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=500)


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class IntegrityRequest(BaseModel):
    mode: Literal['full', 'quick'] = 'full'


class ExpectedDeliveryRequest(BaseModel):
    format: Literal['csv','json']
    content: str = Field(max_length=1024 * 1024)


class QuantityTarget(BaseModel):
    sample_id: str = Field(max_length=128)
    metric: Literal['reads','read_pairs','bases']
    minimum: int = Field(strict=True,ge=0,le=2**53-1)


class YieldConfigRequest(BaseModel):
    assay: str = Field(default='Unspecified',max_length=120)
    input_stage: Literal['unknown','raw_fastq','upstream_processed'] = 'unknown'
    processing_notes: str = Field(default='',max_length=2000)
    targets: list[QuantityTarget] = Field(default_factory=list,max_length=500)


class EvidenceDocument(BaseModel):
    name: Literal['SampleSheet.csv','Demultiplex_Stats.csv','Quality_Metrics.csv','Index_Hopping_Counts.csv','fastq_list.csv']
    content_base64: str = Field(max_length=2800000)


class DemultiplexRequest(BaseModel):
    documents: list[EvidenceDocument] = Field(min_length=1,max_length=5)
    declared_tool_version: str = Field(default='',max_length=120)
    declared_run_id: str = Field(default='',max_length=200)


class FastQCReleaseRule(BaseModel):
    module: str = Field(min_length=1,max_length=120)
    allowed_statuses: list[Literal['pass','warn','fail']] = Field(min_length=1,max_length=3)


class ReleasePolicyRequest(BaseModel):
    version: str = Field(min_length=1,max_length=120)
    assay: str = Field(min_length=1,max_length=120)
    required_checks: list[Literal['integrity','expected_delivery','quantity','demultiplex','screening']] = Field(max_length=5)
    fastqc_rules: list[FastQCReleaseRule] = Field(default_factory=list,max_length=20)


class ReleaseEvaluationRequest(BaseModel):
    sample_ids: list[str] = Field(min_length=1,max_length=500)


class ReleaseActionRequest(ReleaseEvaluationRequest):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    action: Literal['approve','needs_review','block','waive']
    reason: str = Field(min_length=1,max_length=2000)
    rule_id: str | None = Field(default=None,max_length=200)
    reviewer_label: str = Field(default='',max_length=120)


class ReleaseExportRequest(ReleaseEvaluationRequest):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    include_reports: bool = False
    acknowledge_report_paths: bool = False
    include_paths: bool = False
    mode: Literal['spreadsheet','verbatim'] = 'spreadsheet'


class ScreeningRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1,max_length=500)
    database_id: str = Field(min_length=1,max_length=80)
    threads: int = Field(default=1,ge=1,le=32)
    assay: str = Field(default='Unspecified',min_length=1,max_length=120)
    expected_taxids: list[str] = Field(default_factory=list,max_length=20)


class AnalysisRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    mode: Literal["both", "fastqc", "multiqc"] = "both"
    paths: list[str] = Field(min_length=1, max_length=500)
    threads: int = Field(default=1, ge=1, le=32)
    input_pairing: list[ReadAssignment] | None = Field(default=None, max_length=500)
    sample_groups: list[SampleGroup] | None = Field(default=None, max_length=500)
    output_root: str | None = Field(default=None, max_length=4096)
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
    from .project_api import project_router
    app.include_router(project_router(manager))

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
        return Response("Analysis or project record not found", status_code=404)

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
                                    output_root=body.output_root, rerun_of=body.rerun_of)

    @app.get("/api/output-locations")
    async def output_locations():
        return await asyncio.to_thread(manager.stores.listing)

    @app.post("/api/sample-configuration")
    async def sample_configuration(body: SampleConfigurationRequest):
        return await asyncio.to_thread(manager.sample_configuration, body.paths)

    @app.patch("/api/runs/{run_id}")
    async def rename_run(run_id: str, body: RenameRequest):
        return manager.rename(run_id, body.name)

    @app.get("/api/runs/{run_id}/configuration")
    async def run_configuration(run_id: str):
        return await asyncio.to_thread(manager.configuration, run_id)

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

    @app.get('/api/runs/{run_id}/delivery')
    async def delivery(run_id: str):
        return await asyncio.to_thread(manager.delivery.inspect, run_id, deepcopy(manager.runs[run_id]))

    @app.get('/api/runs/{run_id}/expected-template')
    async def delivery_template(run_id: str):
        data = await asyncio.to_thread(manager.delivery.inspect, run_id, deepcopy(manager.runs[run_id]))
        return Response(json.dumps(expected_template(data),indent=2)+'\n',media_type='application/octet-stream',headers={
            'Content-Disposition':f'attachment; filename="qualidock-{run_id}-expected-template.json"',
            'Content-Security-Policy':"sandbox; default-src 'none'"})

    @app.post('/api/runs/{run_id}/expected-delivery')
    async def expected_delivery(run_id: str, body: ExpectedDeliveryRequest):
        return manager.delivery.expected(run_id, body.content, body.format)

    @app.post('/api/runs/{run_id}/yield-targets')
    async def yield_targets(run_id: str, body: YieldConfigRequest):
        data = await asyncio.to_thread(manager.delivery.inspect, run_id, deepcopy(manager.runs[run_id]))
        return manager.delivery.targets(run_id,body.model_dump(),{entry['sample_id'] for entry in data['files']})

    @app.post('/api/runs/{run_id}/demultiplex')
    async def demultiplex(run_id: str, body: DemultiplexRequest):
        if len({item.name for item in body.documents}) != len(body.documents):
            raise ValueError('Duplicate evidence document names')
        documents = {item.name:base64.b64decode(item.content_base64,validate=True) for item in body.documents}
        return manager.delivery.import_demultiplex(run_id,documents,body.declared_tool_version,body.declared_run_id)

    @app.get('/api/screening')
    async def screening_config():
        return await manager.screening.config()

    @app.post('/api/runs/{run_id}/screening',status_code=202)
    async def screening(run_id: str,body: ScreeningRequest):
        return await manager.screening.start(run_id,**body.model_dump())

    @app.post('/api/runs/{run_id}/screening/cancel')
    async def cancel_screening(run_id: str):
        return await manager.screening.cancel(run_id)

    @app.get('/api/runs/{run_id}/screening-metrics')
    async def screening_metrics(run_id: str,file_id: str):
        record = manager.runs[run_id].get('screening',{})
        row = next((row for row in record.get('files',[]) if row['id']==file_id and row.get('metrics_artifact')),None)
        if row is None:raise HTTPException(404,'Screening file evidence is unavailable')
        path = manager.artifact(run_id,row['metrics_artifact'])
        from .metrics import bounded_text
        return json.loads(await asyncio.to_thread(bounded_text,path))

    @app.post('/api/runs/{run_id}/release-policy')
    async def release_policy(run_id: str,body: ReleasePolicyRequest):
        return manager.release.policy(run_id,body.model_dump())

    @app.post('/api/runs/{run_id}/release-review/evaluate')
    async def release_evaluate(run_id: str,body: ReleaseEvaluationRequest):
        result = await asyncio.to_thread(manager.release.inspect,run_id,body.sample_ids,deepcopy(manager.runs[run_id]))
        return {key:value for key,value in result.items() if key not in {'delivery','files'}}

    @app.post('/api/runs/{run_id}/release-review')
    async def release_action(run_id: str,body: ReleaseActionRequest):
        snapshot = deepcopy(manager.runs[run_id])
        evaluation = await asyncio.to_thread(manager.release.inspect,run_id,body.sample_ids,snapshot)
        if snapshot['updated_at'] != manager.runs[run_id]['updated_at'] or evaluation['fingerprint'] != body.fingerprint:
            raise HTTPException(409,'Release evidence changed; refresh the evaluation before recording a review')
        return manager.release.action(run_id,evaluation,body.action,body.reason,body.rule_id,body.reviewer_label)

    @app.post('/api/runs/{run_id}/release-exports',status_code=202)
    async def release_export(run_id: str,body: ReleaseExportRequest):
        return await manager.exports.start(run_id,**body.model_dump())

    @app.post('/api/runs/{run_id}/release-exports/cancel')
    async def cancel_release_export(run_id: str):
        return await manager.exports.cancel(run_id)

    @app.get('/api/runs/{run_id}/delivery-manifest')
    async def delivery_manifest(run_id: str, format: Literal['json','csv']='json', mode: Literal['spreadsheet','verbatim']='spreadsheet', include_paths: bool=False):
        data = await asyncio.to_thread(manager.delivery.inspect, run_id, deepcopy(manager.runs[run_id]))
        text = json.dumps(export_data(data,include_paths),indent=2,allow_nan=False)+'\n' if format == 'json' else csv_export(data,mode,include_paths)
        return Response(text,media_type='application/octet-stream',headers={
            'Content-Disposition':f'attachment; filename="qualidock-{run_id}-manifest-{mode}.{format}"',
            'Content-Security-Policy':"sandbox; default-src 'none'"})

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
