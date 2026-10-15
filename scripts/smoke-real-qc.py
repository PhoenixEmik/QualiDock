#!/usr/bin/env python3
"""Real-tool acceptance smoke; never substitutes mocked QC executables."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time

from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from qualidock.metrics import parse_report

parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=('fastqc', 'both'), default='both')
parser.add_argument('--input-root', type=Path, default=Path('example-data'))
args = parser.parse_args()
fastqc = os.environ.get('QUALIDOCK_FASTQC', 'fastqc')
multiqc = os.environ.get('QUALIDOCK_MULTIQC', 'multiqc')
for tool in ([fastqc] if args.mode == 'fastqc' else [fastqc, multiqc]):
    if shutil.which(tool) is None:
        raise SystemExit(f'QC executable unavailable: {tool}. Load it on PATH or configure QUALIDOCK_FASTQC / QUALIDOCK_MULTIQC.')
root = args.input_root.resolve(strict=True)
inputs = sorted(root.glob('*.fastq.gz'))[:2]
if len(inputs) != 2:
    raise SystemExit('Provide two small FASTQ.gz inputs, or run scripts/create-example-data.py first.')
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
original = {str(p): digest(p) for p in inputs}
with tempfile.TemporaryDirectory(prefix='qualidock-smoke-') as output:
    settings = Settings(roots=[root], output=Path(output), frontend=Path('frontend/dist'), token='smoke-test-only', cpus=1, memory_mb=4096, fastqc=fastqc, multiqc=multiqc)
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization': f'Bearer {settings.token}', 'X-QualiDock-Request': '1'})
        response = client.post('/api/runs', json={'name': 'Real paired-end acceptance smoke', 'mode': args.mode, 'paths': list(original), 'threads': 1})
        assert response.status_code == 201, response.text
        run_id = response.json()['id']
        def finished(identifier):
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                run = client.get(f'/api/runs/{identifier}').json()
                if run['state'] not in {'running', 'queued'}:
                    assert run['state'] == 'completed', client.get(f'/api/runs/{identifier}/logs').json()
                    return run
                time.sleep(0.3)
            raise AssertionError('QC smoke timed out')
        run = finished(run_id)
        metrics = client.get(f'/api/runs/{run_id}/metrics').json()
        assert len(metrics['samples']) == 2
        assert run['tools']['fastqc']['version']
        for sample in metrics['samples']:
            assert sample == parse_report(Path(output) / run_id / sample['id'], sample['id'])
            assert sample['per_base_quality']
            assert all(row['mean'] is None or 0 <= row['mean'] <= 93 for row in sample['per_base_quality'])
        reports = ['metrics.json', 'manifest.json', 'analysis.log']
        if args.mode == 'both':
            reports.append('multiqc/multiqc_report.html')
            assert metrics['multiqc'].get('status') == 'available' and len(metrics['multiqc']['rows']) == 2, metrics['multiqc']
            response = client.post(f'/api/runs/{run_id}/multiqc')
            assert response.status_code == 201, response.text
            aggregated = finished(response.json()['id'])
            assert all(execution['tool'] == 'multiqc' for execution in aggregated['executions'])
            assert aggregated['sample_count'] == 2
        for report in reports:
            assert client.get(f'/api/runs/{run_id}/download', params={'path': report}).status_code == 200
    with TestClient(create_app(settings)) as restored:
        restored.headers.update({'Authorization': f'Bearer {settings.token}'})
        assert restored.get(f'/api/runs/{run_id}').json()['state'] == 'completed'
        assert restored.get(f'/api/runs/{run_id}/metrics').json() == metrics
    assert original == {str(p): digest(p) for p in inputs}
print(f'PASS: real {args.mode} execution, exact report metrics, downloads, immutable inputs, restart recovery')
