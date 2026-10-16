"""Synthetic project metadata / QC doubles; actual streaming integrity is unchanged.

Genuine FastQC/MultiQC coverage is in test_batch_real.py.
"""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import time

from fastapi.testclient import TestClient
import pytest

from qualidock.app import create_app
from test_catalog import domain, attach, create, headers
from test_workspace import start, wait


def preview(client, base, **body):
    response = client.post(base + '/batches/preview', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def queue(client, base, plan, key='request-0001', **extra):
    response = client.post(base + '/batches', json={'plan_id': plan['id'], 'idempotency_key': key, **extra})
    assert response.status_code == 202, response.text
    return response.json()


def finish(client, base, identifier, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = client.get(base + '/batches/' + identifier).json()
        if record['state'] not in {'queued', 'running'}:
            return record
        time.sleep(.03)
    raise AssertionError(record)


def cohort(client, root, *, mode='both'):
    _, base, sample, sequencing = domain(client)
    run = wait(client, start(client, root, mode=mode)['id'])
    attach(client, base, run, sample, sequencing)
    return base, sample, sequencing, run


def test_exact_scope_reuse_full_integrity_yield_restart_readonly_and_idempotency(setup):
    settings, root = setup
    before = {p: p.read_bytes() for p in root.glob('*.fastq')}
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        base, sample, sequencing, run = cohort(client, root)
        plan = preview(client, base, options={'mode': 'both', 'threads': 1})
        assert plan['units'][0]['reuse']['analysis_id'] == run['id']
        assert plan['source_bytes'] == sum(p.stat().st_size for p in before)
        assert str(root) not in json.dumps(plan) and plan['release_state'] == 'not_evaluated'
        initial = queue(client, base, plan)
        assert queue(client, base, plan)['id'] == initial['id']
        record = finish(client, base, initial['id'])
        assert record['state'] == 'completed', record
        unit = record['units'][0]
        assert unit['stages']['qc']['reused'] and unit['analysis_id'] == run['id']
        assert unit['stages']['integrity']['result'] == 'passed'
        assert unit['stages']['yield']['values'][0]['totals']['reads'] == 2
        assert unit['stages']['yield']['values'][0]['target_state'] == 'not_evaluated'
        assert unit['stages']['demultiplex']['state'] == 'skipped'
        assert client.get('/api/runs').json()[0]['id'] == run['id']
        assert queue(client, base, plan)['state'] == 'completed'
        assert client.post(base + '/batches', json={'plan_id': plan['id'], 'idempotency_key': 'another-key'}).status_code == 409
        again = finish(client, base, queue(client, base, plan, key='retry-0001', retry_of=record['id'])['id'])
        assert again['units'][0]['stages']['integrity']['reused']
        record_id = record['id']
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.get(base + '/batches/' + record_id).json() == record
        assert client.get(base + '/batch-plans/' + plan['id']).json() == plan
        assert client.get(base + '/batches', params={'limit': 1}).json()['total'] == 2
    assert all(p.read_bytes() == data for p, data in before.items())


def test_subset_is_new_analysis_with_explicit_pairing_not_old_full_scan(client, setup):
    _, root = setup
    base, sample, sequencing, run = cohort(client, root)
    second = create(client, base + '/samples', 'Second file only')
    association = client.get(base + '/associations').json()['items'][0]
    row = {'file_id': association['file_id'], 'sample_id': second['id'], 'sequencing_run_id': sequencing['id'], 'read': 'unpaired'}
    assert client.patch(base + '/associations/' + association['id'], json={'revision': 1, 'assignment': row, 'reason': 'Synthetic subset test declaration'}).status_code == 200
    plan = preview(client, base, sample_ids=[second['id']])
    assert plan['file_count'] == 1 and plan['units'][0]['reuse'] is None
    result = finish(client, base, queue(client, base, plan)['id'])
    assert result['state'] == 'completed', result
    new = client.get('/api/runs/' + result['units'][0]['analysis_id']).json()
    assert new['id'] != run['id'] and len(new['inputs']) == 1 and new['integrity']['total_files'] == 1
    assert new['batch_origin']['project_id'] == sample['project_id']
    # Generated analysis links must not invalidate a retry of its frozen source plan.
    retry = finish(client, base, queue(client, base, plan, key='retry-subset-1', retry_of=result['id'])['id'])
    assert retry['units'][0]['analysis_id'] == new['id'] and retry['units'][0]['stages']['qc']['reused']
    assert len(client.get('/api/runs').json()) == 2
    fresh = preview(client, base, sample_ids=[second['id']])
    assert fresh['units'][0]['reuse']['analysis_id'] == new['id']


@pytest.mark.parametrize('mutation', ['source', 'metadata', 'tool', 'association'])
def test_stale_preview_never_starts_new_work(client, setup, mutation):
    _, root = setup
    base, sample, sequencing, run = cohort(client, root)
    plan = preview(client, base)
    if mutation == 'source':
        (root / 'sample_R1_001.fastq').write_text('@different\nACGT\n+\nIIII\n')
    elif mutation == 'metadata':
        assert client.patch(base + '/samples/' + sample['id'], json={'revision': 1, 'fields': {'notes': 'Changed after preview'}}).status_code == 200
    elif mutation == 'tool':
        manager = client.app.state.manager
        manager.tool_info['fastqc']['version'] = '0.12.1'
    else:
        association = client.get(base + '/associations').json()['items'][0]
        assignment = {'file_id': association['file_id'], 'sample_id': sample['id'], 'sequencing_run_id': sequencing['id'], 'lane': 'L002'}
        client.patch(base + '/associations/' + association['id'], json={'revision': 1, 'assignment': assignment, 'reason': 'New lane declaration'})
    response = client.post(base + '/batches', json={'plan_id': plan['id'], 'idempotency_key': 'stale-preview-1'})
    assert response.status_code == 409, response.text
    assert client.get(base + '/batches').json()['total'] == 0
    assert len(client.get('/api/runs').json()) == 1


def test_conflicting_same_source_assignments_skipped_never_silently_merged(client, setup):
    _, root = setup
    base, sample, sequencing, run = cohort(client, root)
    second_run = create(client, base + '/sequencing-runs', 'Different declared run')
    rerun = wait(client, start(client, root)['id'])
    attach(client, base, rerun, sample, second_run)
    plan = preview(client, base)
    assert plan['file_count'] == 0 and len(plan['skipped']) == 2
    assert all('Conflicting' in row['reason'] for row in plan['skipped'])
    assert client.post(base + '/batches', json={'plan_id': plan['id'], 'idempotency_key': 'empty-plan-1'}).status_code == 400
    selected = preview(client, base, sequencing_run_ids=[sequencing['id']])
    assert selected['file_count'] == 2


def test_cancel_queued_owned_child_and_explicit_retry_preserves_previous_results(client, setup):
    _, root = setup
    base, sample, sequencing, run = cohort(client, root)
    plan = preview(client, base, options={'reuse': False})
    manager = client.app.state.manager
    client.portal.call(manager.slot.acquire)
    try:
        record = queue(client, base, plan)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            record = client.get(base + '/batches/' + record['id']).json()
            if record['units'][0]['analysis_id']:
                break
            time.sleep(.01)
        generated = record['units'][0]['analysis_id']
        assert generated
        duplicate = preview(client, base, options={'reuse': False})
        assert client.post(base + '/batches', json={'plan_id': duplicate['id'], 'idempotency_key': 'duplicate-plan-1'}).status_code == 409
        stopped = client.post(base + '/batches/' + record['id'] + '/cancel')
        assert stopped.status_code == 200, stopped.text
        assert stopped.json()['state'] == 'cancelled' and stopped.json()['release_state'] == 'not_evaluated'
        assert client.get('/api/runs/' + generated).json()['state'] == 'cancelled'
        assert client.get('/api/runs/' + run['id']).json()['state'] == 'completed'
    finally:
        client.portal.call(manager.slot.release)
    retry = finish(client, base, queue(client, base, plan, key='retry-cancelled-1', retry_of=record['id'])['id'])
    assert retry['state'] == 'completed', retry
    assert retry['units'][0]['analysis_id'] not in {generated, run['id']}


@pytest.mark.parametrize('body', [
    {'options': {'mode': 'multiqc'}}, {'options': {'threads': 999}}, {'options': {'threads': True}},
    {'options': {'integrity': 'arbitrary'}}, {'options': {'output_root': '/tmp/elsewhere'}},
    {'options': {'reuse': 'false'}}, {'options': {'shell': 'touch PWNED'}}, {'sample_ids': ['missing']},
])
def test_batch_validation_and_security_rejects_untrusted_options(client, setup, body):
    _, root = setup
    base, _, _, _ = cohort(client, root)
    assert client.post(base + '/batches/preview', json=body).status_code in {400, 403, 404, 422}
    assert client.get(base + '/batches').json()['total'] == 0


def test_cross_project_api_and_missing_dependency(client, setup):
    _, root = setup
    base, sample, _, _ = cohort(client, root)
    _, other, _, _ = domain(client, 'Other')
    assert client.post(other + '/batches/preview', json={'sample_ids': [sample['id']]}).status_code == 400
    plan = preview(client, base)
    assert client.get(other + '/batch-plans/' + plan['id']).status_code == 400
    manager = client.app.state.manager
    manager.tool_info['multiqc'].update(compatible=False, version=None)
    assert client.post(base + '/batches/preview', json={}).status_code == 400


def test_restart_marks_active_attempt_interrupted_and_preserves_completed_stage(setup):
    settings, root = setup
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        base, _, _, _ = cohort(client, root)
        plan = preview(client, base, options={'integrity': 'off'})
        record = finish(client, base, queue(client, base, plan)['id'])
    path = settings.output / 'projects.sqlite3'
    with sqlite3.connect(path) as db:
        record['state'] = 'running'; record['units'][0]['stages']['integrity'] = {'state': 'running'}
        db.execute('UPDATE batch_attempts SET record=? WHERE id=?', (json.dumps(record), record['id']))
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        restored = client.get(base + '/batches/' + record['id']).json()
        assert restored['state'] == 'interrupted'
        assert restored['units'][0]['stages']['qc']['state'] == 'completed'
        assert restored['units'][0]['stages']['integrity']['state'] == 'not_evaluated'
        assert restored['release_state'] == 'not_evaluated'


def test_multiple_runs_partial_failure_continues_to_successful_unit(client, setup):
    _, root = setup
    (root / 'broken.fastq').write_text('@read\nACGT\n+\nIIII\n')
    _, base, sample, sequencing = domain(client)
    other = create(client, base + '/sequencing-runs', 'Independent second run')
    run = wait(client, start(client, root)['id'])
    assert run['state'] == 'partial'
    files = client.get('/api/runs/' + run['id'] + '/delivery').json()['files']
    assignments = [{'file_id': f['file_id'], 'sample_id': sample['id'], 'sequencing_run_id': sequencing['id'] if f['filename'] == 'broken.fastq' else other['id'], 'read': f['read'], 'lane': 'L001'} for f in files]
    assert client.post(base + '/analyses', json={'analysis_id': run['id'], 'assignments': assignments}).status_code == 201
    plan = preview(client, base)
    result = finish(client, base, queue(client, base, plan)['id'])
    assert result['state'] == 'partial', result
    stages = [u['stages']['qc']['state'] for u in result['units']]
    assert sorted(stages) == ['completed', 'failed']
    assert result['release_state'] == 'not_evaluated'
    failed = next(u for u in result['units'] if u['stages']['qc']['state'] == 'failed')
    assert failed['input_outcomes'][0]['state'] == 'failed'
    assert client.get('/api/runs/' + failed['analysis_id']).json()['reports']


def test_hundred_file_cohort_preserves_file_ids_and_queue_has_bounded_resources(client, setup, monkeypatch):
    _, root = setup
    paths = []
    for index in range(50):
        for read in (1, 2):
            path = root / f'Synthetic{index:03}_L001_R{read}_001.fastq'
            path.write_text(f'@synthetic-{index}/{read}\nACGT\n+\nIIII\n')
            paths.append(str(path))
    _, base, sample, sequencing = domain(client)
    run = wait(client, start(client, root, paths=paths)['id'], timeout=30)
    attach(client, base, run, sample, sequencing)
    plan = preview(client, base, options={'mode': 'fastqc', 'reuse': False, 'integrity': 'full'})
    assert plan['file_count'] == 100 and len(plan['units']) == 1
    # Fifty apparent pairs mapped to one unknown lane/chunk are ambiguous metadata,
    # so no biological pair is inferred from filenames by the batch coordinator.
    assert plan['units'][0]['warnings']
    manager = client.app.state.manager
    original = manager.executor.execute
    running = maximum = 0
    async def observe(*args, **kwargs):
        nonlocal running, maximum
        running += 1; maximum = max(maximum, running)
        try:
            return await original(*args, **kwargs)
        finally:
            running -= 1
    monkeypatch.setattr(manager.executor, 'execute', observe)
    result = finish(client, base, queue(client, base, plan)['id'], timeout=40)
    assert result['state'] == 'completed', result
    assert maximum == 1
    unit = result['units'][0]
    assert len(unit['file_ids']) == len(set(unit['file_ids'])) == len(unit['input_outcomes']) == 100
    actual = client.get('/api/runs/' + unit['analysis_id']).json()
    assert all(not row['paired'] for row in actual['input_pairing'])
    assert len(actual['integrity']['files']) == 100


def test_five_batch_limit_and_cross_project_cancel_cannot_stop_another_attempt(client, setup):
    _, root = setup
    cohorts = [cohort(client, root) for _ in range(6)]
    manager = client.app.state.manager
    client.portal.call(manager.slot.acquire)
    queued = []
    try:
        for base, *_ in cohorts[:5]:
            plan = preview(client, base, options={'reuse': False})
            queued.append((base, queue(client, base, plan)))
        base = cohorts[5][0]
        plan = preview(client, base, options={'reuse': False})
        assert client.post(base + '/batches', json={'plan_id': plan['id'], 'idempotency_key': 'sixth-request'}).status_code == 409
        victim_base, victim = queued[0]
        assert client.post(base + '/batches/' + victim['id'] + '/cancel').status_code == 400
        assert victim['id'] not in manager.batches.cancelled
        assert client.get(victim_base + '/batches/' + victim['id']).json()['state'] in {'queued', 'running'}
        assert len(manager.batches.tasks) == 5
    finally:
        for base, record in queued:
            client.post(base + '/batches/' + record['id'] + '/cancel')
        client.portal.call(manager.slot.release)


def test_cancel_during_child_creation_stops_child_created_after_initial_cancel_read(client, setup, monkeypatch):
    import asyncio
    _, root = setup
    base, *_ = cohort(client, root)
    plan = preview(client, base, options={'reuse': False})
    manager = client.app.state.manager
    original = manager.create
    entered = asyncio.Event()
    release = asyncio.Event()
    async def delayed(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(manager, 'create', delayed)
    client.portal.call(manager.slot.acquire)
    try:
        record = queue(client, base, plan)
        client.portal.call(entered.wait)
        async def stop_then_release():
            task = asyncio.create_task(manager.batches.cancel(base.rsplit('/', 1)[-1], record['id']))
            await asyncio.sleep(.03)
            release.set()
            return await task
        cancelled = client.portal.call(stop_then_release)
        assert cancelled['state'] == 'cancelled'
        child = cancelled['units'][0]['analysis_id']
        assert child and manager.runs[child]['state'] == 'cancelled'
    finally:
        release.set()
        client.portal.call(manager.slot.release)


@pytest.mark.parametrize('options', [{'mode': []}, {'integrity': {}}, {'output_root': []}])
def test_malformed_nested_options_are_validation_errors_not_server_errors(client, setup, options):
    _, root = setup
    base, *_ = cohort(client, root)
    assert client.post(base + '/batches/preview', json={'options': options}).status_code == 400


def test_schema_v2_upgrade_retains_previous_project_evidence_and_qc_bytes(setup):
    settings, root = setup
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        base, _, _, run = cohort(client, root)
        link = client.get(base + '/analyses').json()['items'][0]
        evidence = client.post(base + '/analyses/' + link['id'] + '/evidence', json={}).json()
    originals = {p: p.read_bytes() for p in (settings.output / run['id']).rglob('*') if p.is_file()}
    with sqlite3.connect(settings.output / 'projects.sqlite3') as db:
        db.execute('DROP TABLE batch_attempts'); db.execute('DROP TABLE batch_plans')
        db.execute('PRAGMA user_version=2')
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.get(base + '/evidence/' + evidence['id']).json() == evidence
        assert all(p.read_bytes() == data for p, data in originals.items())
        plan = preview(client, base, options={'integrity': 'off'})
        assert plan['units'][0]['reuse']['analysis_id'] == run['id']
        result = finish(client, base, queue(client, base, plan)['id'])
        assert result['state'] == 'completed'
        with client.app.state.manager.catalog.transaction(True) as db:
            with pytest.raises(sqlite3.IntegrityError, match='immutable'):
                db.execute('UPDATE batch_plans SET fingerprint=? WHERE id=?', ('unsafe', plan['id']))
        assert all(p.read_bytes() == data for p, data in originals.items())


def test_shell_characters_in_selected_fastq_are_literal_and_sources_remain_readonly(client, setup):
    _, root = setup
    path = root / "reads ' ; $(touch PWNED) &.fastq"
    path.write_text('@literal\nACGT\n+\nIIII\n')
    original = path.read_bytes()
    _, base, sample, sequencing = domain(client)
    run = wait(client, start(client, root, paths=[str(path)])['id'])
    attach(client, base, run, sample, sequencing)
    plan = preview(client, base, options={'reuse': False})
    result = finish(client, base, queue(client, base, plan)['id'])
    assert result['state'] == 'completed', result
    assert result['units'][0]['input_outcomes'][0]['name'] == path.name
    assert path.read_bytes() == original
    assert not list(settings_path for settings_path in root.parent.rglob('PWNED'))
