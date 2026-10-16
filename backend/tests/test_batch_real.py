"""Actual FastQC 0.13.0 + MultiQC and streaming validation of genuine small fixtures."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

from qualidock.app import create_app
from test_catalog import create, domain, headers
from test_workspace import start, wait
from test_batch_jobs import preview, queue, finish


def test_genuine_multirun_batch_and_reuse_exact_data_after_restart(setup):
    settings, root = setup
    fastqc = shutil.which(os.environ.get('QUALIDOCK_FASTQC', 'fastqc'))
    multiqc = shutil.which(os.environ.get('QUALIDOCK_MULTIQC', 'multiqc'))
    if not fastqc or not multiqc:
        pytest.skip('Provisioned real-QC CI job requires actual FastQC and MultiQC')
    fixture = Path(__file__).parent / 'fixtures/fastqc-0.13.0'
    inputs = []
    # Copies of the tiny genuine public fixture ONLY, representing distinct run paths.
    # No research data or production source is copied by the application.
    for lane in ['L001', 'L002']:
        for read in [1, 2]:
            path = root / f'Genuine_S1_{lane}_R{read}_001.fastq.gz'
            shutil.copyfile(fixture / f'coverage_R{read}.fastq.gz', path)
            inputs.append(path)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    settings = replace(settings, fastqc=fastqc, multiqc=multiqc)
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        _, base, sample, sequencing = domain(client)
        other = create(client, base + '/sequencing-runs', 'Second declared acquisition')
        run = wait(client, start(client, root, paths=list(map(str, inputs)))['id'], timeout=120)
        assert run['state'] == 'completed'
        original = (settings.output / run['id'] / 'manifest.json').read_bytes()
        files = client.get('/api/runs/' + run['id'] + '/delivery').json()['files']
        assignments = [{'file_id': f['file_id'], 'sample_id': sample['id'], 'sequencing_run_id': sequencing['id'] if f['lane'] == 'L001' else other['id'],
                        'read': f['read'], 'lane': f['lane'], 'chunk': f['chunk'], 'source': 'user_confirmed'} for f in files]
        assert client.post(base + '/analyses', json={'analysis_id': run['id'], 'assignments': assignments}).status_code == 201
        plan = preview(client, base)
        assert plan['file_count'] == 4 and len(plan['units']) == 2
        assert all(unit['reuse'] is None for unit in plan['units'])  # subset of the original source analysis
        result = finish(client, base, queue(client, base, plan)['id'], timeout=180)
        assert result['state'] == 'completed', result
        for unit in result['units']:
            child = client.get('/api/runs/' + unit['analysis_id']).json()
            assert child['tools']['fastqc']['version'] == '0.13.0'
            assert child['tools']['multiqc']['version']
            assert child['integrity']['result'] == 'passed' and child['integrity']['pairs'][0]['state'] == 'passed'
            official = client.get('/api/runs/' + child['id'] + '/metrics').json()
            inventory = client.get('/api/runs/' + child['id'] + '/delivery').json()['files']
            assert len(official['samples']) == len(inventory) == 2
            for file in inventory:
                parsed = next(row for row in official['samples'] if row['id'] == file['report_id'])
                assert file['reads'] == parsed['total_sequences']
                assert file['q20_bases'] is not None and file['q30_bases'] is not None
                assert file['quality_bases'] >= file['q20_bases'] >= file['q30_bases']
            report = 'multiqc/multiqc_report.html'
            assert client.get('/api/report-preview', params={'run_id': child['id'], 'path': report}).status_code == 200
        assert (settings.output / run['id'] / 'manifest.json').read_bytes() == original
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.get(base + '/batches/' + result['id']).json() == result
        again = finish(client, base, queue(client, base, plan, key='real-retry-0001', retry_of=result['id'])['id'], timeout=60)
        assert again['state'] == 'completed'
        assert all(unit['stages']['qc']['reused'] and unit['stages']['integrity']['reused'] for unit in again['units'])
        assert {unit['analysis_id'] for unit in again['units']} == {unit['analysis_id'] for unit in result['units']}
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
