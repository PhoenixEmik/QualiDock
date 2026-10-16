"""Synthetic domain declarations; original scientific artifacts stay unchanged."""
from copy import deepcopy
import hashlib
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from qualidock.app import create_app
from qualidock.catalog import SCHEMA_VERSION
from test_catalog import create, domain, attach, headers
from test_workspace import start, wait
from test_release_review import prepare, evaluation, action


def import_preview(client, base, content, format='csv'):
    response = client.post(base + '/samples/import', json={'format': format, 'content': content})
    assert response.status_code == 200, response.text
    return response.json()


def test_sample_import_preview_atomic_commit_idempotency_and_actual_text_hash(client):
    _, base, _, _ = domain(client)
    content = 'display_name,declared_identifier,assay,expected_yield_metric,expected_yield_minimum,notes\n"Name, quoted",new-1,RNA-seq,reads,0,"line one\nline two"\nSecond,new-2,,,,\n'
    preview = import_preview(client, base, content)
    assert preview['count'] == 2
    assert preview['submitted_text_sha256'] == hashlib.sha256(content.encode()).hexdigest()
    assert preview['rows'][0]['expected_yield'] == {'metric': 'reads', 'minimum': 0}
    assert 'expected_yield' not in preview['rows'][1]
    assert client.get(base + '/samples').json()['total'] == 1
    request = {'format': 'csv', 'content': content, 'fingerprint': preview['fingerprint']}
    imported = client.post(base + '/samples/import', json=request)
    assert imported.status_code == 200, imported.text
    assert imported.json()['count'] == 2 and not imported.json()['reused']
    again = client.post(base + '/samples/import', json=request).json()
    assert again['reused'] and again['sample_ids'] == imported.json()['sample_ids']
    assert client.get(base + '/samples').json()['total'] == 3
    fields = client.get(base + '/samples/' + again['sample_ids'][0]).json()['declared']
    assert fields['notes'] == 'line one\nline two' and fields['expected_yield']['minimum'] == 0


@pytest.mark.parametrize('format,content', [
    ('csv', 'display_name,display_name\nOne,Two\n'),
    ('csv', 'display_name,path\nOne,/etc/passwd\n'),
    ('csv', 'display_name,expected_yield_metric,expected_yield_minimum\nOne,reads,1e6\n'),
    ('csv', 'display_name,declared_identifier\nOne,ID\nTwo,ID\n'),
    ('csv', 'display_name\nSame\nSame\n'),
    ('csv', 'display_name,notes\nOne,extra,column\n'),
    ('json', '[{"display_name":"One","expected_yield":{"metric":"reads","minimum":1.5}}]'),
    ('json', '[{"display_name":"One"},{"display_name":""}]'),
    ('json', '[]'),
])
def test_import_invalid_or_ambiguous_metadata_never_partially_writes(client, format, content):
    _, base, _, _ = domain(client)
    response = client.post(base + '/samples/import', json={'format': format, 'content': content})
    assert response.status_code == 400, response.text
    assert client.get(base + '/samples').json()['total'] == 1


def test_large_import_stale_preview_and_cross_project_labels(client):
    _, base, _, _ = domain(client)
    rows = [{'display_name': f'Synthetic sample {i:03}', 'declared_identifier': f'S{i:03}'} for i in range(120)]
    content = json.dumps(rows)
    preview = import_preview(client, base, content, 'json')
    create(client, base + '/samples', 'Concurrent metadata edit')
    assert client.post(base + '/samples/import', json={'format': 'json', 'content': content, 'fingerprint': preview['fingerprint']}).status_code == 409
    assert client.get(base + '/samples').json()['total'] == 2
    preview = import_preview(client, base, content, 'json')
    assert client.post(base + '/samples/import', json={'format': 'json', 'content': content, 'fingerprint': preview['fingerprint']}).status_code == 200
    assert client.get(base + '/samples', params={'limit': 25}).json()['total'] == 122
    assert len(client.get(base + '/samples', params={'offset': 100, 'limit': 25}).json()['items']) == 22
    assert client.get(base + '/samples', params={'search': 'Synthetic sample 119'}).json()['total'] == 1
    identity = client.get(base + '/samples', params={'search': 'Synthetic sample 119'}).json()['items'][0]['id']
    assert client.get(base + '/samples', params={'search': identity}).json()['items'][0]['id'] == identity
    assert client.post(base + '/samples/import', json={'format': 'json', 'content': json.dumps([rows[0]])}).status_code == 409
    _, other, _, _ = domain(client, 'Other project')
    second_preview = import_preview(client, other, json.dumps([rows[0]]), 'json')
    created = client.post(other + '/samples/import', json={'format': 'json', 'content': json.dumps([rows[0]]), 'fingerprint': second_preview['fingerprint']}).json()
    assert client.get(other + '/samples/' + created['sample_ids'][0]).json()['project_id'] != client.get(base).json()['id']


def test_bulk_import_failure_rolls_back_all_rows_and_audit_events(client, monkeypatch):
    _, base, _, _ = domain(client)
    content = json.dumps([{'display_name': 'First imported row'}, {'display_name': 'Second imported row'}])
    preview = import_preview(client, base, content, 'json')
    catalog = client.app.state.manager.catalog
    original = catalog.event
    calls = 0
    def fail_mid_import(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('Injected import persistence failure')
        return original(*args)
    monkeypatch.setattr(catalog, 'event', fail_mid_import)
    with pytest.raises(RuntimeError, match='Injected import'):
        client.post(base + '/samples/import', json={'format': 'json', 'content': content, 'fingerprint': preview['fingerprint']})
    assert client.get(base + '/samples').json()['total'] == 1
    with catalog.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM events WHERE action='samples_imported'").fetchone()[0] == 0


def test_fill_unresolved_and_reasoned_correction_preserve_approved_evidence(setup):
    settings, root = setup
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        run, run_base, scopes = prepare(client, root)
        decision = action(client, run_base, evaluation(client, run_base, scopes)).json()
        original_manifest = (settings.output / run['id'] / 'manifest.json').read_bytes()
        _, base, sample, sequencing = domain(client)
        other = create(client, base + '/samples', 'Corrected sample declaration')
        link = client.post(base + '/analyses', json={'analysis_id': run['id']}).json()
        inventory = client.get(base + '/analyses/' + link['id'] + '/inventory').json()
        assert len(inventory['files']) == 2 and not inventory['associations']
        assert str(root) not in json.dumps(inventory)
        assignments = [{'file_id': file['file_id'], 'sample_id': sample['id'], 'sequencing_run_id': sequencing['id'], 'read': file['read'], 'lane': 'L001'} for file in inventory['files']]
        assert client.post(base + '/analyses/' + link['id'] + '/assignments', json={'assignments': assignments}).status_code == 200
        assert client.post(base + '/analyses/' + link['id'] + '/assignments', json={'assignments': assignments}).status_code == 409
        old = client.post(base + '/analyses/' + link['id'] + '/evidence', json={'sample_ids': scopes}).json()
        association = client.get(base + '/associations').json()['items'][0]
        assignment = next(row for row in assignments if row['file_id'] == association['file_id'])
        corrected = {**assignment, 'sample_id': other['id'], 'source': 'user_assigned'}
        endpoint = base + '/associations/' + association['id']
        assert client.patch(endpoint, json={'revision': 1, 'assignment': corrected, 'reason': ' '}).status_code == 400
        response = client.patch(endpoint, json={'revision': 1, 'assignment': corrected, 'reason': 'Source manifest metadata correction'})
        assert response.status_code == 200, response.text
        assert response.json()['revision'] == 2
        assert client.patch(endpoint, json={'revision': 1, 'assignment': corrected, 'reason': 'Stale'}).status_code == 409
        current = client.post(base + '/analyses/' + link['id'] + '/evidence', json={'sample_ids': scopes}).json()
        assert current['id'] != old['id']
        assert client.get(base + '/evidence/' + old['id']).json() == old
        assert evaluation(client, run_base, scopes)['decision'] == decision
        assert (settings.output / run['id'] / 'manifest.json').read_bytes() == original_manifest
        assert client.get(base + '/associations', params={'sample_id': other['id']}).json()['total'] == 1
        assert client.get(base + '/associations', params={'sequencing_run_id': sequencing['id']}).json()['total'] == 2
        db_path = settings.output / 'projects.sqlite3'
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.get(base + '/associations', params={'sample_id': other['id']}).json()['items'][0]['revision'] == 2
        assert client.get(base + '/evidence/' + old['id']).json() == old
    with sqlite3.connect(db_path) as db:
        events = [json.loads(row[0]) for row in db.execute("SELECT data FROM events WHERE action='association_corrected'")]
    assert events[0]['previous']['sample_id'] == sample['id'] and events[0]['current']['sample_id'] == other['id']
    assert events[0]['reason'] == 'Source manifest metadata correction'


def test_schema_v1_to_v2_preserves_ids_snapshots_and_official_reports(setup):
    settings, root = setup
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        run = wait(client, start(client, root, mode='fastqc')['id'])
        _, base, sample, sequencing = domain(client)
        link, _ = attach(client, base, run, sample, sequencing)
        evidence = client.post(base + '/analyses/' + link['id'] + '/evidence', json={}).json()
    # Explicitly synthetic v1 schema shape: remove only v2's metadata column and indexes.
    with sqlite3.connect(settings.output / 'projects.sqlite3') as db:
        db.execute('ALTER TABLE associations DROP COLUMN revision')
        db.execute('DROP INDEX events_project'); db.execute('DROP INDEX events_entity')
        db.execute('DROP TABLE batch_attempts'); db.execute('DROP TABLE batch_plans')
        db.execute('PRAGMA user_version=1')
    manifests = {path: path.read_bytes() for path in (settings.output / run['id']).rglob('*') if path.is_file()}
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.get(base + '/evidence/' + evidence['id']).json() == evidence
        assert all(row['revision'] == 1 for row in client.get(base + '/associations').json()['items'])
        assert client.get(base + '/samples').json()['items'][0]['id'] == sample['id']
    with sqlite3.connect(settings.output / 'projects.sqlite3') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
    assert all(path.read_bytes() == data for path, data in manifests.items())


def test_interleaved_corrections_record_actual_previous_revision(client, setup, monkeypatch):
    from qualidock.project_management import ProjectManagement
    _, root = setup
    _, base, sample, sequencing = domain(client)
    second = create(client, base + '/samples', 'Second declaration')
    third = create(client, base + '/samples', 'Third declaration')
    run = wait(client, start(client, root, mode='fastqc')['id'])
    _, assignments = attach(client, base, run, sample, sequencing)
    catalog = client.app.state.manager.catalog
    association = client.get(base + '/associations').json()['items'][0]
    assignment = next(row for row in assignments if row['file_id'] == association['file_id'])
    original = catalog.prepare_assignments
    injected = False
    def interleave(analysis_id, rows):
        nonlocal injected
        prepared = original(analysis_id, rows)
        if not injected:
            injected = True
            ProjectManagement(catalog).revise_assignment(sample['project_id'], association['id'], 1, {**assignment, 'sample_id': second['id']}, 'First interleaved update')
        return prepared
    monkeypatch.setattr(catalog, 'prepare_assignments', interleave)
    response = client.patch(base + '/associations/' + association['id'], json={'revision': 2, 'assignment': {**assignment, 'sample_id': third['id']}, 'reason': 'Second interleaved update'})
    assert response.status_code == 200, response.text
    assert response.json()['revision'] == 3
    with catalog.transaction() as db:
        history = [json.loads(row[0]) for row in db.execute("SELECT data FROM events WHERE action='association_corrected' ORDER BY sequence")]
    assert history[0]['previous']['revision'] == 1 and history[0]['current']['sample_id'] == second['id']
    assert history[1]['previous']['revision'] == 2 and history[1]['previous']['sample_id'] == second['id']
    assert history[1]['current']['sample_id'] == third['id']


def test_corrections_and_filtered_inventory_reject_cross_project_or_arbitrary_files(client, setup):
    _, root = setup
    _, base, sample, sequencing = domain(client)
    _, other, other_sample, _ = domain(client, 'Other')
    run = wait(client, start(client, root, mode='fastqc')['id'])
    link, assignments = attach(client, base, run, sample, sequencing)
    association = client.get(base + '/associations').json()['items'][0]
    assignment = next(row for row in assignments if row['file_id'] == association['file_id'])
    assert client.get(other + '/analyses/' + link['id'] + '/inventory').status_code == 400
    assert client.get(base + '/associations', params={'sample_id': other_sample['id']}).status_code == 400
    for correction in [{**assignment, 'file_id': 'unknown'}, {**assignment, 'sample_id': other_sample['id']}, {**assignment, 'path': '/etc/passwd'}]:
        assert client.patch(base + '/associations/' + association['id'], json={'revision': 1, 'assignment': correction, 'reason': 'Invalid test'}).status_code == 400
    assert client.get(base + '/associations').json()['items'][0]['revision'] == 1
