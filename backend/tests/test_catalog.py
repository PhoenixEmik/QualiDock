"""Project relationship metadata is synthetic; QC doubles exercise orchestration.

Genuine scientific output coverage is separate in test_catalog_real.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from qualidock.app import create_app
from qualidock.manager import RunManager
from test_workspace import start, wait
from test_release_review import prepare, evaluation, action


def headers(settings):
    return {'Authorization': f'Bearer {settings.token}', 'X-QualiDock-Request': '1'}


def create(client, path='/api/projects', name='Project A', **fields):
    response = client.post(path, json={'fields': {'display_name': name, **fields}})
    assert response.status_code == 201, response.text
    return response.json()


def domain(client, name='Project A'):
    project = create(client, name=name)
    base = '/api/projects/' + project['id']
    sample = create(client, base + '/samples', 'Same label', declared_identifier='S1', assay='RNA-seq')
    sequencing = create(client, base + '/sequencing-runs', 'Run 1', platform='Declared Illumina', sequenced_at='2026-10-16', input_stage='raw_fastq')
    return project, base, sample, sequencing


def attach(client, base, run, sample, sequencing):
    files = client.get('/api/runs/' + run['id'] + '/delivery').json()['files']
    assignments = [{'file_id': file['file_id'], 'sample_id': sample['id'], 'sequencing_run_id': sequencing['id'], 'read': file['read'], 'lane': 'L001', 'chunk': '001', 'source': 'user_confirmed'} for file in files]
    response = client.post(base + '/analyses', json={'analysis_id': run['id'], 'assignments': assignments})
    assert response.status_code == 201, response.text
    return response.json(), assignments


def test_many_to_many_runs_samples_and_legacy_restart_without_manifest_rewrite(setup):
    settings, root = setup
    original = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir()}
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        old = wait(client, start(client, root, mode='fastqc')['id'])
        manifest = settings.output / old['id'] / 'manifest.json'
        saved = manifest.read_bytes()
        p, base, sample, sequencing = domain(client)
        second = create(client, base + '/sequencing-runs', 'Supplementary sequencing')
        other_sample = create(client, base + '/samples', 'Other sample')
        link, assignments = attach(client, base, old, sample, sequencing)
        rerun = wait(client, start(client, root, mode='fastqc')['id'])
        attach(client, base, rerun, sample, second)
        third = wait(client, start(client, root, mode='fastqc')['id'])
        attach(client, base, third, other_sample, sequencing)
        legacy = wait(client, start(client, root, mode='fastqc')['id'])
        assert manifest.read_bytes() == saved
        detail = client.get(base).json()
        assert detail['counts'] == {'sample': 2, 'sequencing_run': 2, 'analyses': 3, 'associations': 6}
        assert detail['qc_readiness'] == detail['release_readiness'] == 'unknown'
        assert client.get('/api/unassigned-analyses').json()['items'][0]['id'] == legacy['id']
        evidence = client.post(base + '/analyses/' + link['id'] + '/evidence', json={}).json()
        assert evidence['snapshot']['qc_artifacts'][0]['artifact'] == 'metrics.json'
        evidence_page = client.get(base + '/evidence').json()
        assert evidence_page['total'] == 1 and evidence_page['items'][0]['id'] == evidence['id']
        assert 'snapshot' not in evidence_page['items'][0]
        assert str(root) not in json.dumps(evidence)
        assert str(settings.output) not in json.dumps(client.get(base + '/analyses').json())
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.get(base).json()['counts'] == detail['counts']
        assert client.get(base + '/evidence/' + evidence['id']).json() == evidence
        assert client.get('/api/runs/' + legacy['id']).json()['state'] == 'completed'
        assert client.get('/api/unassigned-analyses').json()['total'] == 1
        assert client.get(base + '/associations').json()['total'] == 6
    assert original == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir()}


def test_duplicate_labels_cross_project_references_and_atomic_conflict_rejected(client, setup):
    _, root = setup
    p1, base1, s1, seq1 = domain(client)
    p2, base2, s2, seq2 = domain(client, 'Other project')
    assert s1['declared']['display_name'] == s2['declared']['display_name']
    assert s1['id'] != s2['id']
    assert client.get(base1 + '/samples/' + s2['id']).status_code == 400
    assert client.patch(base1 + '/samples/' + s2['id'], json={'revision': 1, 'fields': {'notes': 'Cross project'}}).status_code == 400
    run = wait(client, start(client, root, mode='fastqc')['id'])
    file = client.get('/api/runs/' + run['id'] + '/delivery').json()['files'][0]
    assignment = {'file_id': file['file_id'], 'sample_id': s2['id'], 'sequencing_run_id': seq1['id']}
    result = client.post(base1 + '/analyses', json={'analysis_id': run['id'], 'assignments': [assignment]})
    assert result.status_code == 400
    assert client.get(base1 + '/analyses').json()['total'] == 0
    assignment['sample_id'] = s1['id']
    for invalid in [[assignment, assignment], [{**assignment, 'file_id': 'unknown'}], [{**assignment, 'path': '/private/secret.fastq'}], [{**assignment, 'sample_id': []}], [{**assignment, 'source': 'auto'}], [{**assignment, 'read': []}], [{**assignment, 'source': {'invalid': True}}]]:
        assert client.post(base1 + '/analyses', json={'analysis_id': run['id'], 'assignments': invalid}).status_code in {400, 422}
    link, _ = attach(client, base1, run, s1, seq1)
    assert client.post(base2 + '/analyses', json={'analysis_id': run['id']}).status_code == 409
    assert client.post(base2 + '/analyses/' + link['id'] + '/evidence', json={}).status_code == 400


def test_declaration_edits_do_not_rewrite_approvals_or_evidence(client, setup):
    settings, root = setup
    run, analysis_base, ids = prepare(client, root)
    approved = action(client, analysis_base, evaluation(client, analysis_base, ids)).json()
    _, base, sample, sequencing = domain(client)
    link, _ = attach(client, base, run, sample, sequencing)
    endpoint = base + '/analyses/' + link['id'] + '/evidence'
    before = client.post(endpoint, json={'sample_ids': ids}).json()
    assert before['snapshot']['release']['decision'] == approved
    assert client.post(endpoint, json={'sample_ids': ids}).json()['id'] == before['id']
    changed = client.patch(base + '/samples/' + sample['id'], json={'revision': 1, 'fields': {'display_name': 'Corrected declared label'}})
    assert changed.status_code == 200
    assert client.patch(base + '/samples/' + sample['id'], json={'revision': 1, 'fields': {'notes': 'Stale'}}).status_code == 409
    after = client.post(endpoint, json={'sample_ids': ids}).json()
    assert after['id'] != before['id'] and after['sha256'] != before['sha256']
    assert client.get(base + '/evidence/' + before['id']).json() == before
    assert evaluation(client, analysis_base, ids)['decision'] == approved
    assert evaluation(client, analysis_base, ids)['review_state'] == 'approved'
    assert client.get(analysis_base).json()['release_reviews'][-1] == approved


def test_legacy_installation_and_schema_upgrade_rollback_are_non_destructive(setup):
    settings, root = setup
    legacy_id = 'e' * 32
    directory = settings.output / legacy_id
    directory.mkdir(parents=True)
    manifest = directory / 'manifest.json'
    raw = json.dumps({'schema_version': 1, 'id': legacy_id, 'state': 'completed', 'name': 'Unassigned v1', 'mode': 'fastqc', 'created_at': '2026-01-01', 'inputs': [], 'reports': []}).encode()
    manifest.write_bytes(raw)
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.get('/api/unassigned-analyses').json()['items'][0]['id'] == legacy_id
        create(client)
    assert manifest.read_bytes() == raw
    db_path = settings.output / 'projects.sqlite3'
    with sqlite3.connect(db_path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        db.execute('PRAGMA user_version=99')
    pending = json.loads(raw)
    pending['state'] = 'queued'
    pending_bytes = json.dumps(pending).encode()
    manifest.write_bytes(pending_bytes)
    before = db_path.read_bytes()
    manager = RunManager(settings)
    with pytest.raises(ValueError, match='newer'):
        manager.start()
    assert not manager.stores.locks and db_path.read_bytes() == before
    assert manifest.read_bytes() == pending_bytes
    with sqlite3.connect(db_path) as db:
        db.execute('PRAGMA user_version=1')
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.get('/api/projects').json()['total'] == 1
        assert client.get('/api/runs/' + legacy_id).json()['state'] == 'interrupted'


@pytest.mark.parametrize('attack', ['symlink', 'hardlink', 'public', 'unversioned', 'journal_symlink'])
def test_catalog_unsafe_storage_is_rejected_without_touching_external_files(setup, attack):
    settings, root = setup
    settings.output.mkdir(mode=0o700)
    target = root / 'protected'
    target.write_text('original bytes')
    target.chmod(0o600)
    path = settings.output / 'projects.sqlite3'
    if attack == 'symlink': path.symlink_to(target)
    elif attack == 'hardlink': os.link(target, path)
    elif attack == 'public': path.write_text('invalid'); path.chmod(0o644)
    elif attack == 'unversioned': path.touch(mode=0o600)
    else: Path(str(path) + '-journal').symlink_to(target)
    manager = RunManager(settings)
    with pytest.raises((ValueError, OSError)):
        manager.start()
    assert target.read_text() == 'original bytes'
    assert not manager.stores.locks


def test_missing_inputs_symlink_escape_and_unknown_analyses_do_not_create_links(client, setup):
    _, root = setup
    _, base, sample, sequencing = domain(client)
    run = wait(client, start(client, root, mode='fastqc')['id'])
    paths = list(root.glob('*.fastq'))
    files = client.get('/api/runs/' + run['id'] + '/delivery').json()['files']
    assignment = {'file_id': files[0]['file_id'], 'sample_id': sample['id'], 'sequencing_run_id': sequencing['id']}
    source = Path(files[0]['path'])
    source.unlink()
    assert client.post(base + '/analyses', json={'analysis_id': run['id'], 'assignments': [assignment]}).status_code == 403
    target = root.parent / 'outside.fastq'
    target.write_text('@x\nA\n+\nI\n')
    source.symlink_to(target)
    assert client.post(base + '/analyses', json={'analysis_id': run['id'], 'assignments': [assignment]}).status_code == 403
    assert client.post(base + '/analyses', json={'analysis_id': 'a' * 32}).status_code == 404
    assert client.get(base + '/analyses').json()['total'] == 0
    # Explicit historical link without current source associations is supported.
    assert client.post(base + '/analyses', json={'analysis_id': run['id']}).status_code == 201


@pytest.mark.parametrize('fields', [ {'display_name': None}, {'display_name': ' '}, {'display_name': 'x', 'path': '/etc/passwd'}, {'display_name': 'x', 'status': 'ready'}, {'display_name': 'x' * 201} ])
def test_invalid_fields_never_leak_or_mutate(client, fields):
    result = client.post('/api/projects', json={'fields': fields})
    assert result.status_code == 400, result.text
    assert client.get('/api/projects').json()['total'] == 0


def test_pagination_archive_conflicts_auth_and_csrf(client, setup):
    settings, _ = setup
    project, base, _, _ = domain(client)
    assert client.post(base + '/samples', json={'fields': {'display_name': 'Invalid units', 'expected_yield': {'metric': [], 'minimum': 0}}}).status_code == 400
    for index in range(105):
        create(client, base + '/samples', 'Synthetic sample ' + str(index))
    page = client.get(base + '/samples', params={'limit': 100}).json()
    next_page = client.get(base + '/samples', params={'offset': 100, 'limit': 100}).json()
    assert page['total'] == 106 and len(page['items']) == 100 and len(next_page['items']) == 6
    assert not {e['id'] for e in page['items']} & {e['id'] for e in next_page['items']}
    assert client.get(base + '/samples', params={'limit': 101}).status_code == 400
    assert client.get(base + '/samples', params={'search': 'Synthetic sample 104'}).json()['total'] == 1
    assert client.get(base + '/samples', params={'search': '%'}).json()['total'] == 0
    assert client.patch(base, json={'revision': 1, 'fields': {'status': 'archived'}}).status_code == 200
    assert client.get('/api/projects').json()['total'] == 0
    assert client.get('/api/projects', params={'status': 'archived'}).json()['total'] == 1
    assert client.post(base + '/samples', json={'fields': {'display_name': 'Cannot add'}}).status_code == 400
    assert client.delete(base).status_code == 405  # Archive instead; never delete scientific history.
    assert client.patch(base, json={'revision': 2, 'fields': {'status': 'active'}}).status_code == 200
    client.headers.pop('Authorization')
    assert client.get(base).status_code == 401
    assert client.post(base + '/analyses', json={'analysis_id': 'a' * 32}).status_code == 401
    client.headers.update(headers(settings))
    client.headers.pop('X-QualiDock-Request')
    assert client.patch(base, json={'revision': 3, 'fields': {'notes': 'CSRF'}}).status_code == 403


def test_existing_exclusive_lock_covers_project_registry(setup):
    settings, _ = setup
    first = RunManager(settings)
    first.start()
    try:
        with pytest.raises(RuntimeError, match='Another QualiDock'):
            RunManager(settings).start()
    finally:
        first.stores.close()


def test_transaction_rollback_append_only_audit_and_concurrent_records(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime
    catalog = client.app.state.manager.catalog
    original = catalog.event
    def fail(*args): raise RuntimeError('Injected atomic transaction failure')
    monkeypatch.setattr(catalog, 'event', fail)
    with pytest.raises(RuntimeError, match='Injected'):
        catalog.create('project', {'display_name': 'Must roll back'})
    assert catalog.listing()['total'] == 0
    monkeypatch.setattr(catalog, 'event', original)
    project = catalog.create('project', {'display_name': 'Concurrency fixture'})
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda index: catalog.create('sample', {'display_name': 'Same declared label'}, project['id']), range(40)))
    assert len({record['id'] for record in records}) == 40
    assert all(datetime.fromisoformat(record['created_at']).tzinfo for record in records)
    with catalog.transaction(True) as db:
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            db.execute("UPDATE events SET action='rewritten'")
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            db.execute('DELETE FROM events')
    assert catalog.listing('sample', project['id'])['total'] == 40


def test_private_catalog_backup_and_restore_at_original_store_path(setup, tmp_path):
    settings, _ = setup
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        project = create(client)
    path = settings.output / 'projects.sqlite3'
    backup = tmp_path / 'private-registry-backup.sqlite3'
    backup.touch(mode=0o600)
    with sqlite3.connect(path) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.patch('/api/projects/' + project['id'], json={'revision': 1, 'fields': {'display_name': 'After backup'}}).status_code == 200
    import shutil
    shutil.copyfile(backup, path)
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        restored = client.get('/api/projects/' + project['id']).json()
        assert restored['declared']['display_name'] == project['declared']['display_name']
        assert restored['revision'] == 1 and restored['created_at'] == project['created_at']
