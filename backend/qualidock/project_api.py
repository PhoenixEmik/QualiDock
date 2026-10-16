"""Authenticated project routes share the application's existing API protections."""
import asyncio
import sqlite3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .catalog import CatalogConflict


class CreateEntity(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fields: dict = Field(max_length=12)


class EditEntity(CreateEntity):
    revision: int = Field(strict=True, ge=1)


class AttachAnalysis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    analysis_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    assignments: list[dict] = Field(default_factory=list, max_length=500)


class CaptureEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sample_ids: list[str] | None = Field(default=None, min_length=1, max_length=500)


class SampleImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format: str = Field(pattern=r'^(csv|json)$')
    content: str = Field(max_length=1024 * 1024)
    fingerprint: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


class AssignFiles(BaseModel):
    model_config = ConfigDict(extra='forbid')
    assignments: list[dict] = Field(min_length=1, max_length=500)


class CorrectAssignment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(strict=True, ge=1)
    assignment: dict = Field(max_length=9)
    reason: str = Field(min_length=1, max_length=2000)


class ProjectAnalysis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: str = Field(min_length=8, max_length=128)
    name: str = Field(default='', max_length=120)
    mode: str = Field(default='both', pattern=r'^(both|fastqc)$')
    paths: list[str] = Field(min_length=1, max_length=500)
    threads: int = Field(default=1, strict=True, ge=1)
    output_root: str | None = None
    input_pairing: list[dict] = Field(max_length=500)
    sample_groups: list[dict] = Field(max_length=500)


class CohortQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_ids: list[str] | None = Field(default=None, min_length=1, max_length=5)
    sample_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    sequencing_run_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    metric: str = Field(default='q30_percent', max_length=80)
    filters: dict = Field(default_factory=dict, max_length=8)
    rule: dict | None = Field(default=None, max_length=1)
    group_by: str = Field(default='file', pattern=r'^(file|run)$')
    adapter: str | None = Field(default=None, max_length=200)
    position: str | None = Field(default=None, max_length=200)
    offset: int = Field(default=0, strict=True, ge=0)
    limit: int = Field(default=100, strict=True, ge=1, le=100)
    definition_id: str | None = Field(default=None, pattern=r'^definition-[a-f0-9]{24}$')


class CohortExport(CohortQuery):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    format: str = Field(default='csv', pattern=r'^(csv|tsv)$')
    mode: str = Field(default='spreadsheet', pattern=r'^(spreadsheet|verbatim)$')
    exclusions: bool = False


class ContextRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^seq_[a-f0-9]{32}$')
    revision: int = Field(strict=True, ge=1)


class BulkRunContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_ids: list[str] = Field(min_length=1, max_length=5)
    records: list[ContextRecord] = Field(min_length=1, max_length=100)
    fields: dict = Field(min_length=1, max_length=3)


class BatchPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sample_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    sequencing_run_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    options: dict = Field(default_factory=dict, max_length=8)


class BatchStart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plan_id: str = Field(pattern=r'^bpl_[a-f0-9]{32}$')
    idempotency_key: str = Field(min_length=8, max_length=128)
    retry_of: str | None = Field(default=None, pattern=r'^bat_[a-f0-9]{32}$')


def project_router(manager):
    router = APIRouter(prefix='/api')
    catalog = manager.catalog
    from .project_management import ProjectManagement
    management = ProjectManagement(catalog)
    from .project_intake import ProjectIntake
    intake = ProjectIntake(manager)
    from .cohort import CohortComparisons
    comparisons = CohortComparisons(manager)

    async def call(method, *args, **kwargs):
        try:
            if asyncio.iscoroutinefunction(method):
                return await method(*args, **kwargs)
            return await asyncio.to_thread(method, *args, **kwargs)
        except CatalogConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (sqlite3.OperationalError, OSError) as exc:
            raise HTTPException(503, 'Project storage is unavailable, busy or not writable; check its owner, permissions and filesystem') from exc

    def kind(collection):
        if collection not in {'samples', 'sequencing-runs'}:
            raise HTTPException(404, 'Unknown project collection')
        return 'sample' if collection == 'samples' else 'sequencing_run'

    @router.get('/projects')
    async def projects(search: str = '', offset: int = 0, limit: int = 25, status: str = 'active'):
        return await call(catalog.listing, search=search, offset=offset, limit=limit, status=status)

    @router.post('/projects', status_code=201)
    async def create_project(body: CreateEntity):
        return await call(catalog.create, 'project', body.fields)

    @router.get('/unassigned-analyses')
    async def unassigned(offset: int = 0, limit: int = 25):
        return await call(catalog.unassigned, offset, limit)

    @router.get('/projects/{project_id}')
    async def project(project_id: str):
        return await call(catalog.detail, project_id)

    @router.patch('/projects/{project_id}')
    async def edit_project(project_id: str, body: EditEntity):
        # Ensure this endpoint cannot modify a nested sample by passing its ID.
        await call(catalog.detail, project_id)
        return await call(catalog.edit, project_id, body.revision, body.fields)

    @router.get('/projects/{project_id}/associations')
    async def associations(project_id: str, offset: int = 0, limit: int = 100, sample_id: str | None = None, sequencing_run_id: str | None = None):
        return await call(catalog.associations, project_id, offset, limit, sample_id, sequencing_run_id)

    @router.get('/projects/{project_id}/analyses')
    async def analyses(project_id: str, offset: int = 0, limit: int = 25):
        return await call(catalog.links, project_id, offset, limit)

    @router.post('/projects/{project_id}/analyses', status_code=201)
    async def attach(project_id: str, body: AttachAnalysis):
        return await call(catalog.attach, project_id, body.analysis_id, body.assignments)

    @router.post('/projects/{project_id}/analyses/{link_id}/evidence', status_code=201)
    async def capture(project_id: str, link_id: str, body: CaptureEvidence):
        return await call(catalog.capture, project_id, link_id, body.sample_ids)

    @router.get('/projects/{project_id}/evidence/{evidence_id}')
    async def evidence(project_id: str, evidence_id: str):
        return await call(catalog.evidence, project_id, evidence_id)

    @router.get('/projects/{project_id}/evidence')
    async def evidence_page(project_id: str, offset: int = 0, limit: int = 25):
        return await call(catalog.evidence_page, project_id, offset, limit)

    @router.post('/projects/{project_id}/samples/import')
    async def import_samples(project_id: str, body: SampleImport):
        return await call(management.import_samples, project_id, body.content, body.format, body.fingerprint)

    @router.get('/projects/{project_id}/analyses/{link_id}/inventory')
    async def inventory(project_id: str, link_id: str):
        return await call(management.inventory, project_id, link_id)

    @router.post('/projects/{project_id}/analyses/{link_id}/assignments')
    async def assign(project_id: str, link_id: str, body: AssignFiles):
        return await call(management.add_assignments, project_id, link_id, body.assignments)

    @router.patch('/projects/{project_id}/associations/{association_id}')
    async def correct(project_id: str, association_id: str, body: CorrectAssignment):
        return await call(management.revise_assignment, project_id, association_id, body.revision, body.assignment, body.reason)

    @router.post('/projects/{project_id}/start-analysis', status_code=201)
    async def start_project_analysis(project_id: str, body: ProjectAnalysis):
        configuration = body.model_dump(exclude={'request_key', 'paths'})
        configuration['raw_paths'] = body.paths
        return await call(intake.start, project_id, body.request_key, **configuration)

    def comparison_arguments(project_id, body):
        arguments = body.model_dump()
        arguments['project_ids'] = arguments['project_ids'] or [project_id]
        if project_id not in arguments['project_ids']:
            raise ValueError('The current project must remain in the selected comparison scope')
        return arguments

    @router.post('/projects/{project_id}/comparisons/query')
    async def compare(project_id: str, body: CohortQuery):
        return await call(comparisons.query, **comparison_arguments(project_id, body))

    @router.post('/projects/{project_id}/comparisons/export')
    async def export_comparison(project_id: str, body: CohortExport):
        from fastapi.responses import Response
        arguments = comparison_arguments(project_id, body)
        arguments.pop('offset'); arguments.pop('limit')
        content = await call(comparisons.export, **arguments)
        return Response(content, media_type='text/tab-separated-values' if body.format == 'tsv' else 'text/csv',
                        headers={'Content-Disposition': f'attachment; filename="qualidock-cohort.{body.format}"', 'Content-Security-Policy': "sandbox; default-src 'none'"})

    @router.patch('/projects/{project_id}/comparisons/run-context')
    async def update_context(project_id: str, body: BulkRunContext):
        if project_id not in body.project_ids:
            raise ValueError('Current project must be included')
        return await call(comparisons.update_run_context, body.project_ids, [record.model_dump() for record in body.records], body.fields)

    @router.post('/projects/{project_id}/batches/preview')
    async def batch_preview(project_id: str, body: BatchPreview):
        return await call(manager.batches.preview, project_id, body.sample_ids, body.sequencing_run_ids, body.options)

    @router.post('/projects/{project_id}/batches', status_code=202)
    async def batch_start(project_id: str, body: BatchStart):
        return await call(manager.batches.start, project_id, body.plan_id, body.idempotency_key, body.retry_of)

    @router.get('/projects/{project_id}/batches')
    async def batch_list(project_id: str, offset: int = 0, limit: int = 25):
        return await call(manager.batches.listing, project_id, offset, limit)

    @router.get('/projects/{project_id}/batches/{attempt_id}')
    async def batch_detail(project_id: str, attempt_id: str):
        return await call(manager.batches.read, project_id, attempt_id)

    @router.get('/projects/{project_id}/batch-plans/{plan_id}')
    async def batch_plan(project_id: str, plan_id: str):
        return manager.batches.public(await call(manager.batches.read_plan, project_id, plan_id))

    @router.post('/projects/{project_id}/batches/{attempt_id}/cancel')
    async def batch_cancel(project_id: str, attempt_id: str):
        return await call(manager.batches.cancel, project_id, attempt_id)

    @router.get('/projects/{project_id}/{collection}')
    async def entities(project_id: str, collection: str, search: str = '', offset: int = 0, limit: int = 25, status: str = 'active'):
        return await call(catalog.listing, kind(collection), project_id, search, offset, limit, status)

    @router.post('/projects/{project_id}/{collection}', status_code=201)
    async def create_entity(project_id: str, collection: str, body: CreateEntity):
        return await call(catalog.create, kind(collection), body.fields, project_id)

    @router.get('/projects/{project_id}/{collection}/{entity_id}')
    async def get_entity(project_id: str, collection: str, entity_id: str):
        def read():
            with catalog.transaction() as db:
                return catalog.entity(db, entity_id, kind(collection), project_id)
        return await call(read)

    @router.patch('/projects/{project_id}/{collection}/{entity_id}')
    async def edit_entity(project_id: str, collection: str, entity_id: str, body: EditEntity):
        await get_entity(project_id, collection, entity_id)
        return await call(catalog.edit, entity_id, body.revision, body.fields, project_id)

    return router
