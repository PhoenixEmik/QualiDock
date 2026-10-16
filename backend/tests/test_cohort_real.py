"""Genuine FastQC output/full validation over baseline and low-Q30 synthetic reads."""
from dataclasses import replace
import csv
import gzip
import hashlib
import io
import os
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

from qualidock.app import create_app
from test_catalog import create, domain, attach, headers
from test_workspace import start, wait
from test_validation_jobs import finish
from test_cohort import query


def test_actual_low_q30_rule_exact_source_values_reports_and_restart(setup):
    settings, root = setup
    fastqc = shutil.which(os.environ.get('QUALIDOCK_FASTQC', 'fastqc'))
    if not fastqc:
        pytest.skip('Provisioned real-QC CI job requires actual FastQC')
    settings = replace(settings, fastqc=fastqc)
    fixture = Path(__file__).parent / 'fixtures/fastqc-0.13.0'
    baseline, low = [], []
    for label, target in [('baseline', baseline), ('intentional-low-q30-synthetic', low)]:
        directory = root / label; directory.mkdir()
        for read in [1, 2]:
            source = fixture / f'coverage_R{read}.fastq.gz'
            path = directory / source.name
            if label == 'baseline':
                shutil.copyfile(source, path)
            else:
                # Explicitly synthetic quality-only variant, never an application
                # preprocessing feature and never a modification of original fixtures.
                with gzip.open(source, 'rb') as incoming, gzip.open(path, 'wb') as outgoing:
                    for index, line in enumerate(incoming):
                        outgoing.write(b'5' * len(line.rstrip(b'\r\n')) + b'\n' if index % 4 == 3 else line)
            target.append(str(path))
    original = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.glob('*.fastq.gz')}
    selected_hashes = {Path(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in [*baseline, *low]}
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        _, base, sample, high_run = domain(client)
        low_run = create(client, base + '/sequencing-runs', 'Intentionally low Q30 synthetic run', input_stage='raw_fastq', platform='Declared Illumina', sequenced_at='2026-10-16')
        for paths, acquisition in [(baseline, high_run), (low, low_run)]:
            analysis = wait(client, start(client, root, mode='fastqc', paths=paths)['id'], timeout=120)
            assert analysis['state'] == 'completed' and analysis['tools']['fastqc']['version'] == '0.13.0'
            attach(client, base, analysis, sample, acquisition)
            assert client.post('/api/runs/' + analysis['id'] + '/integrity', json={'mode': 'full'}).status_code == 202
            scan = finish(client, analysis['id'])
            assert scan['result'] == 'passed' and all(f['quality_bases'] for f in scan['files'])
        body = {'metric': 'q30_percent', 'rule': {'minimum_percent': '50'}}  # Declared test reference, not a production cutoff.
        result = query(client, base, **body)
        assert result['total'] == 4 and len(result['groups']) == 1
        low_points = [p for p in result['points'] if p['context']['sequencing_run_id'] == low_run['id']]
        high_points = [p for p in result['points'] if p['context']['sequencing_run_id'] == high_run['id']]
        assert len(low_points) == len(high_points) == 2
        assert all(p['value'] == 0 and p['numerator'] == 0 and p['denominator'] > 0 and p['rule_result'] == 'review' for p in low_points)
        assert all(p['value'] > 50 and p['rule_result'] == 'within_declared_reference' for p in high_points)
        assert 'not FastQC status' in result['rule']['meaning']
        for point in result['points']:
            source = point['sources'][0]
            run = client.get('/api/runs/' + source['analysis_id']).json()
            file = next(f for f in run['integrity']['files'] if f['id'] == point['file_id'])
            assert point['numerator'] == file['q30_bases'] and point['denominator'] == file['quality_bases']
            assert point['value'] == 100 * file['q30_bases'] / file['quality_bases']
            html = next(r for r in run['reports'] if r['path'].endswith('_fastqc.html'))
            preview = client.get('/api/report-preview', params={'run_id': run['id'], 'path': html['path']})
            assert preview.status_code == 200 and 'sandbox allow-scripts' in preview.headers['content-security-policy']
        exported = client.post(base + '/comparisons/export', json={**body, 'fingerprint': result['fingerprint'], 'mode': 'verbatim'})
        assert exported.status_code == 200
        rows = list(csv.DictReader(io.StringIO(exported.text)))
        assert {int(row['denominator']) for row in rows} == {point['denominator'] for point in result['points']}
        gc = query(client, base, metric='gc_percent')
        assert gc['total'] == 4
        for point in gc['points']:
            source = point['sources'][0]
            metrics = client.get('/api/runs/' + source['analysis_id'] + '/metrics').json()
            sample_report = next(row for row in metrics['samples'] if row['id'] == source['report_id'])
            assert point['raw_value'] == sample_report['basic_statistics']['%GC']
            assert point['value'] == sample_report['gc_percent']
    with TestClient(create_app(settings), headers=headers(settings)) as client:
        restored = query(client, base, **body)
        assert restored['fingerprint'] == result['fingerprint'] and restored['points'] == result['points']
    assert original == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in original}
    assert selected_hashes == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in selected_hashes}
