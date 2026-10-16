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


def project_router(manager):
    router = APIRouter(prefix='/api')
    catalog = manager.catalog

    async def call(method, *args, **kwargs):
        try:
            return await asyncio.to_thread(method, *args, **kwargs)
        except CatalogConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except sqlite3.OperationalError as exc:
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
    async def associations(project_id: str, offset: int = 0, limit: int = 100):
        return await call(catalog.associations, project_id, offset, limit)

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
