"""Actual FastQC outputs plus project evidence; never replaces scientific results."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import shutil
import time

from fastapi.testclient import TestClient
import pytest

from qualidock.app import create_app
from test_catalog import headers, domain, attach
from test_workspace import wait


def test_actual_fastqc_project_provenance_and_restart(setup):
    fastqc = shutil.which(os.environ.get('QUALIDOCK_FASTQC', 'fastqc'))
    if not fastqc:
        pytest.skip('Actual FastQC is exercised by the explicit real-QC CI job')
    settings, _ = setup
    fixture = Path(__file__).parent / 'fixtures' / 'fastqc-0.13.0'
    settings = replace(settings, roots=[fixture], fastqc=fastqc)
    inputs = sorted(fixture.glob('coverage_R*.fastq.gz'))
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        response = client.post('/api/runs', json={'mode': 'fastqc', 'paths': list(map(str, inputs)), 'threads': 1})
        assert response.status_code == 201, response.text
        run = wait(client, response.json()['id'], timeout=90)
        assert run['state'] == 'completed'
        _, base, sample, sequencing = domain(client)
        link, _ = attach(client, base, run, sample, sequencing)
        evidence = client.post(base + '/analyses/' + link['id'] + '/evidence', json={}).json()
        assert evidence['snapshot']['tools']['fastqc'] == '0.13.0'
        official_metrics = settings.output / run['id'] / 'metrics.json'
        assert evidence['snapshot']['qc_artifacts'][0]['sha256'] == hashlib.sha256(official_metrics.read_bytes()).hexdigest()
        html = next(report for report in run['reports'] if report['path'].endswith('.html'))
        original = client.get('/api/runs/' + run['id'] + '/download', params={'path': html['path']}).content
        assert b'FastQC' in original
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        assert client.get(base + '/evidence/' + evidence['id']).json() == evidence
        assert client.get('/api/runs/' + run['id'] + '/download', params={'path': html['path']}).content == original
    assert hashes == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
