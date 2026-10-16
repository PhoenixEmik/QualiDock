"""Browse-first metadata registration; QC doubles, real read-only file references."""
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from qualidock.app import create_app
from test_catalog import create, headers
from test_workspace import wait


def selection(client, root, paths=None):
    paths = paths or list(map(str, sorted(root.glob('*.fastq'))))
    response = client.post('/api/sample-configuration', json={'paths': paths})
    assert response.status_code == 200, response.text
    config = response.json()
    return {'request_key': 'browse-request-1', 'name': 'User selected FASTQs', 'mode': 'both', 'paths': paths, 'threads': 1,
            'input_pairing': config['input_pairing'], 'sample_groups': config['sample_groups']}


def test_project_name_then_browse_bulk_selection_creates_all_relationships_atomically_and_restores(setup):
    settings, root = setup
    original = {p: p.read_bytes() for p in root.glob('*.fastq')}
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        project = create(client, name='Name-only project')
        base = '/api/projects/' + project['id']
        body = selection(client, root)
        response = client.post(base + '/start-analysis', json=body)
        assert response.status_code == 201, response.text
        run = wait(client, response.json()['id'])
        assert run['state'] == 'completed'
        counts = client.get(base).json()['counts']
        assert counts == {'sample': 1, 'sequencing_run': 1, 'analyses': 1, 'associations': 2}
        assert run['project_intake']['state'] == 'registered'
        assert all(row['paired'] for row in run['input_pairing'])
        declared = client.get(base + '/samples').json()['items'][0]['declared']
        assert set(declared) == {'display_name', 'status'}  # No invented assay/yield.
        seq = client.get(base + '/sequencing-runs').json()['items'][0]['declared']
        assert seq['input_stage'] == 'unknown' and 'sequenced_at' not in seq
        retry = client.post(base + '/start-analysis', json=body)
        assert retry.status_code == 201 and retry.json()['id'] == run['id']
        assert client.get(base).json()['counts'] == counts
        assert client.post(base + '/start-analysis', json={**body, 'name': 'Changed request'}).status_code == 409
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.post(base + '/start-analysis', json=body).json()['id'] == run['id']
        assert client.get(base).json()['counts'] == counts
    assert all(p.read_bytes() == contents for p, contents in original.items())


def test_same_labels_in_different_directories_are_new_distinct_groups_not_biological_matches(client, setup):
    _, root = setup
    paths = []
    for directory in ['first facility', 'second facility']:
        folder = root / directory; folder.mkdir()
        for read in [1, 2]:
            path = folder / f'Same_R{read}.fastq'; path.write_text(f'@test/{read}\nACGT\n+\nIIII\n'); paths.append(str(path))
    project = create(client)
    base = '/api/projects/' + project['id']
    create(client, base + '/samples', 'Same')
    body = selection(client, root, paths)
    assert len(body['sample_groups']) == 2
    response = client.post(base + '/start-analysis', json=body)
    assert response.status_code == 201, response.text
    assert wait(client, response.json()['id'])['state'] == 'completed'
    samples = client.get(base + '/samples').json()['items']
    assert len(samples) == len({row['id'] for row in samples}) == 3
    assert all(row['declared']['display_name'] == 'Same' for row in samples)
    associations = client.get(base + '/associations').json()['items']
    assert len({row['sample_id'] for row in associations}) == 2


def test_intake_registration_failure_rolls_back_metadata_and_preserves_inspectable_analysis(client, setup, monkeypatch):
    _, root = setup
    project = create(client); base = '/api/projects/' + project['id']
    body = selection(client, root)
    catalog = client.app.state.manager.catalog
    original = catalog.event
    def fail(db, project_id, entity_id, action, data):
        if action == 'browse_intake_confirmed':
            raise RuntimeError('Injected atomic registration failure')
        return original(db, project_id, entity_id, action, data)
    monkeypatch.setattr(catalog, 'event', fail)
    manager = client.app.state.manager
    client.portal.call(manager.slot.acquire)
    try:
        response = client.post(base + '/start-analysis', json=body)
    finally:
        client.portal.call(manager.slot.release)
    assert response.status_code == 400 and 'remains in Analyses' in response.text
    assert client.get(base).json()['counts'] == {'analyses': 0, 'associations': 0}
    record = client.get('/api/runs').json()[0]
    run = client.get('/api/runs/' + record['id']).json()
    assert run['state'] == 'cancelled' and run['project_intake']['state'] == 'registration_failed'
    assert client.post(base + '/start-analysis', json=body).status_code == 409
    with catalog.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM events WHERE action='browse_intake_confirmed'").fetchone()[0] == 0


def test_invalid_scope_or_unreviewed_groups_do_not_start_qc(client, setup):
    _, root = setup
    project = create(client); base = '/api/projects/' + project['id']
    body = selection(client, root)
    assert client.post(base + '/start-analysis', json={key: value for key, value in body.items() if key != 'sample_groups'}).status_code == 422
    assert client.post(base + '/start-analysis', json={**body, 'mode': 'multiqc'}).status_code == 422
    assert client.post(base + '/start-analysis', json={**body, 'sample_groups': []}).status_code == 400
    assert client.post(base + '/start-analysis', json={**body, 'paths': ['/etc/passwd']}).status_code == 403
    assert not client.get('/api/runs').json()
