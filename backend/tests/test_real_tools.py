"""Scientific integration acceptance uses actual installed tools, never fixtures as executables."""
import hashlib
from pathlib import Path
import os
import shutil
import time

import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from qualidock.metrics import parse_report
from qualidock.preview import MEMORY_STORAGE_BOOTSTRAP
from test_workspace import wait

INPUTS = Path(__file__).parent / 'fixtures/fastqc-0.13.0'
FASTQC = shutil.which(os.environ.get('QUALIDOCK_FASTQC', 'fastqc'))
MULTIQC = shutil.which(os.environ.get('QUALIDOCK_MULTIQC', 'multiqc'))


def real_settings(tmp_path):
    return Settings(roots=[INPUTS.resolve()], output=tmp_path / 'results', frontend=tmp_path / 'frontend', token='real-tool-test-only', cpus=1, memory_mb=4096, fastqc=FASTQC or 'fastqc', multiqc=MULTIQC or 'multiqc', allow_root=True)


@pytest.mark.skipif(not FASTQC, reason='Real FastQC is not installed')
def test_real_fastqc_preserves_source_values_and_history(tmp_path):
    settings = real_settings(tmp_path)
    files = sorted(INPUTS.glob('*.fastq.gz'))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization': f'Bearer {settings.token}', 'X-QualiDock-Request': '1'})
        response = client.post('/api/runs', json={'mode': 'fastqc', 'paths': [str(p.resolve()) for p in files], 'threads': 1})
        assert response.status_code == 201, response.text
        run = wait(client, response.json()['id'])
        assert run['state'] == 'completed', client.get(f"/api/runs/{run['id']}/logs").json()
        assert run['tools']['fastqc']['version']
        assert run['executions'][0]['exit_code'] == 0
        samples = client.get(f"/api/runs/{run['id']}/metrics").json()['samples']
        assert len(samples) == 2
        for sample in samples:
            report = settings.output / run['id'] / sample['id']
            assert sample == parse_report(report, sample['id'])
            assert sample['status'] == 'fail'  # Actual QC results, not a failed process.
            assert any(b['base'] == '10-14' for b in sample['per_base_quality'])
            response = client.get(f"/api/runs/{run['id']}/download", params={'path': sample['id'].replace('.zip', '.html')})
            assert response.status_code == 200 and 'attachment' in response.headers['content-disposition']
            preview = client.get('/api/report-preview', params={'run_id': run['id'], 'path': sample['id'].replace('.zip', '.html')})
            assert preview.status_code == 200 and preview.content == response.content
            assert 'inline' in preview.headers['content-disposition']
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization': f'Bearer {settings.token}'})
        assert client.get(f"/api/runs/{run['id']}/metrics").json()['samples'] == samples
        assert client.get('/api/report-preview', params={'run_id': run['id'], 'path': samples[0]['id'].replace('.zip', '.html')}).status_code == 200
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


@pytest.mark.skipif(not FASTQC or not MULTIQC, reason='Real FastQC and MultiQC are both required')
def test_real_combined_and_existing_results_multiqc(tmp_path):
    settings = real_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization': f'Bearer {settings.token}', 'X-QualiDock-Request': '1'})
        response = client.post('/api/runs', json={'mode': 'both', 'paths': [str(p.resolve()) for p in sorted(INPUTS.glob('*.fastq.gz'))]})
        assert response.status_code == 201, response.text
        run_id = response.json()['id']
        # MultiQC can take longer to initialize than the small FastQC analysis itself.
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            run = client.get(f'/api/runs/{run_id}').json()
            if run['state'] not in {'queued', 'running'}: break
            time.sleep(0.1)
        assert run['state'] == 'completed', client.get(f'/api/runs/{run_id}/logs').json()
        assert run['executions'][-1]['exit_code'] == 0
        report = client.get(f'/api/runs/{run_id}/download', params={'path': 'multiqc/multiqc_report.html'})
        assert report.status_code == 200
        preview = client.get('/api/report-preview', params={'run_id': run_id, 'path': 'multiqc/multiqc_report.html'})
        assert preview.status_code == 200
        assert preview.content.replace(MEMORY_STORAGE_BOOTSTRAP, b'', 1) == report.content
        assert preview.content.count(MEMORY_STORAGE_BOOTSTRAP) == 1
        summary = client.get(f'/api/runs/{run_id}/metrics').json()['multiqc']
        assert len(summary['rows']) == 2 and summary['columns']
        response = client.post(f'/api/runs/{run_id}/multiqc')
        assert response.status_code == 201, response.text
        aggregate_id = response.json()['id']
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            aggregate = client.get(f'/api/runs/{aggregate_id}').json()
            if aggregate['state'] not in {'queued', 'running'}: break
            time.sleep(0.1)
        assert aggregate['state'] == 'completed', client.get(f'/api/runs/{aggregate_id}/logs').json()
        assert all(e['tool'] == 'multiqc' for e in aggregate['executions'])
        assert len(client.get(f'/api/runs/{aggregate_id}/metrics').json()['multiqc']['rows']) == 2
        imported_html = next(r['path'] for r in aggregate['reports'] if r['path'].startswith('inputs/') and r['path'].endswith('.html'))
        for path in (imported_html, 'multiqc/multiqc_report.html'):
            assert client.get('/api/report-preview', params={'run_id': aggregate_id, 'path': path}).status_code == 200
    with TestClient(create_app(settings)) as restored:
        restored.headers.update({'Authorization': f'Bearer {settings.token}'})
        response = restored.get('/api/report-preview', params={'run_id': run_id, 'path': 'multiqc/multiqc_report.html'})
        assert response.content.replace(MEMORY_STORAGE_BOOTSTRAP, b'', 1) == report.content
