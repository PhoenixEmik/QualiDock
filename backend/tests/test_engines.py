import asyncio
import json
from pathlib import Path
import shutil
import sys
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.files import FileAccess, PathViolation
from qualidock.reports import discover
from qualidock.tools import detect_tool
from test_workspace import start, wait

FIXTURES = Path(__file__).parent / 'fixtures/fastqc-0.13.0'


def executable(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(f'#!{sys.executable}\n{body}\n')
    path.chmod(0o700)
    return str(path)


@pytest.mark.parametrize(('name', 'response', 'compatible'), [('fastqc', 'FastQC v0.13.0', True), ('fastqc', 'FastQC v0.12.1', True), ('multiqc', 'multiqc, version 1.35', True), ('multiqc', 'multiqc, version 1.24', False), ('multiqc', 'multiqc, version 2.0', False), ('multiqc', 'not a version', False)])
def test_version_detection(tmp_path, name, response, compatible):
    path = executable(tmp_path, name, f'print({response!r})')
    info = asyncio.run(detect_tool(name, path))
    assert info['available'] and info['compatible'] is compatible
    assert bool(info['error']) is not compatible


def test_detection_path_missing_and_failure(tmp_path, monkeypatch):
    assert not asyncio.run(detect_tool('multiqc', str(tmp_path / 'missing')))['available']
    path = executable(tmp_path, 'multiqc', 'import sys; print("multiqc, version 1.35"); sys.exit(2)')
    monkeypatch.setenv('PATH', str(tmp_path))
    info = asyncio.run(detect_tool('multiqc', 'multiqc'))
    assert info['available'] and not info['compatible'] and 'exit 2' in info['error']


def test_version_probe_never_receives_session_secret(tmp_path, monkeypatch):
    monkeypatch.setenv('QUALIDOCK_TOKEN', 'secret')
    monkeypatch.setenv('password', 'also-secret')
    path = executable(tmp_path, 'multiqc', 'import os; assert "QUALIDOCK_TOKEN" not in os.environ and "password" not in os.environ; print("multiqc, version 1.35")')
    assert asyncio.run(detect_tool('multiqc', path))['compatible']


def test_tool_config_and_incompatible_preflight(client, setup):
    settings, root = setup
    config = client.get('/api/config').json()
    assert config['tools'] == {'fastqc': True, 'multiqc': True}
    assert config['tool_details']['fastqc']['version'] == '0.13.0'
    Path(settings.multiqc).write_text(f'#!{sys.executable}\nprint("multiqc, version 1.0")\n')
    response = client.post('/api/runs', json={'mode': 'both', 'paths': [str(next(root.glob('*.fastq')))]})
    assert response.status_code == 400 and 'Unsupported multiqc' in response.text
    assert client.get('/api/config').json()['tools']['multiqc'] is False
    assert wait(client, start(client, root, mode='fastqc')['id'])['state'] == 'completed'


def copy_report(root):
    destination = root / 'saved_results' / 'coverage_R1_fastqc'
    shutil.copytree(FIXTURES / 'coverage_R1_fastqc', destination)
    (destination / 'fastqc_report.html').write_text('<html>attachment safety test only</html>')
    return destination


def test_multiqc_directory_import_snapshots_reports_not_fastq(client, setup):
    settings, root = setup
    report = copy_report(root)
    (report.parent / 'huge.fastq.gz').write_bytes(b'not a report; do not copy')
    before = {str(p): p.read_bytes() for p in report.iterdir()}
    run = wait(client, start(client, root, mode='multiqc', paths=[str(report.parent)])['id'])
    assert run['state'] == 'completed' and run['sample_count'] == 1, run
    assert run['tools']['multiqc']['version'] == '1.35'
    assert [execution['tool'] for execution in run['executions']] == ['multiqc']
    assert run['executions'][0]['exit_code'] == 0
    assert '--file-list' in run['executions'][0]['argv']
    directory = settings.output / run['id']
    assert (directory / 'inputs/0/summary.txt').is_file()
    assert not list(directory.rglob('*.fastq.gz'))
    assert before == {str(p): p.read_bytes() for p in report.iterdir()}
    shutil.rmtree(report.parent)
    assert client.get(f"/api/runs/{run['id']}/metrics").json()['samples'][0]['fastqc_version'] == '0.13.0'
    assert client.get(f"/api/runs/{run['id']}/download", params={'path': 'inputs/0/fastqc_data.txt'}).status_code == 200


def test_duplicate_zip_and_extracted_report_import_once(tmp_path):
    folder = tmp_path / 'coverage_R1_fastqc'
    shutil.copytree(FIXTURES / folder.name, folder)
    with zipfile.ZipFile(tmp_path / 'coverage_R1_fastqc.zip', 'w') as z:
        for path in folder.iterdir(): z.write(path, f'{folder.name}/{path.name}')
    records = discover([tmp_path], FileAccess([tmp_path]))
    assert len(records) == 1 and records[0]['path'].endswith('.zip')


def test_import_rejects_escaped_symlink_and_unsupported_directory(client, setup):
    _, root = setup
    directory = root / 'reports'; directory.mkdir()
    outside = root.parent / 'private'; outside.mkdir()
    (directory / 'escape').symlink_to(outside, target_is_directory=True)
    response = client.post('/api/runs', json={'mode': 'multiqc', 'paths': [str(directory)]})
    assert response.status_code == 403
    (directory / 'escape').unlink()
    response = client.post('/api/runs', json={'mode': 'multiqc', 'paths': [str(directory)]})
    assert response.status_code == 400 and 'No supported FastQC' in response.text


def test_generate_multiqc_from_saved_run_outside_input_roots(client, setup):
    _, root = setup
    source = wait(client, start(client, root, mode='fastqc')['id'])
    response = client.post(f"/api/runs/{source['id']}/multiqc")
    assert response.status_code == 201, response.text
    aggregate = wait(client, response.json()['id'])
    assert aggregate['state'] == 'completed', aggregate
    assert aggregate['source_run_id'] == source['id'] and aggregate['sample_count'] == 2
    assert all(e['tool'] == 'multiqc' for e in aggregate['executions'])
    assert client.get(f"/api/runs/{source['id']}").json()['state'] == 'completed'


def test_partial_fastqc_passes_only_successful_reports(client, setup):
    settings, root = setup
    (root / 'broken.fastq').write_text('bad input')
    run = wait(client, start(client, root)['id'])
    assert run['state'] == 'partial' and run['sample_count'] == 2
    assert [entry['exit_code'] for entry in run['executions']] == [1, 0]
    listed = (settings.output / run['id'] / 'multiqc-inputs.txt').read_text().splitlines()
    assert len(listed) == 2 and not any('broken' in path for path in listed)


def test_multiqc_cancel_keeps_fastqc_and_exit_record(client, setup):
    settings, root = setup
    Path(settings.multiqc).write_text(f'#!{sys.executable}\nimport sys,time\nif "--version" in sys.argv: print("multiqc, version 1.35"); sys.exit(0)\nprint("MultiQC slow execution fixture", flush=True)\ntime.sleep(30)\n')
    run = start(client, root)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current = client.get(f"/api/runs/{run['id']}").json()
        if current['stage'] == 'MultiQC': break
        time.sleep(0.02)
    assert current['stage'] == 'MultiQC'
    client.post(f"/api/runs/{run['id']}/cancel")
    deadline = time.monotonic() + 5
    while run['id'] in client.app.state.manager.tasks and time.monotonic() < deadline: time.sleep(0.02)
    current = client.get(f"/api/runs/{run['id']}").json()
    assert current['state'] == 'cancelled' and current['sample_count'] == 2
    assert current['executions'][-1]['finished_at']
    assert current['executions'][-1]['exit_code'] != 0
    assert any(report['path'].endswith('_fastqc.zip') for report in current['reports'])


def test_import_history_survives_restart_without_source(setup):
    settings, root = setup
    report = copy_report(root)
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization': f'Bearer {settings.token}', 'X-QualiDock-Request': '1'})
        run = wait(client, start(client, root, mode='multiqc', paths=[str(report)])['id'])
    shutil.rmtree(report.parent)
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization': f'Bearer {settings.token}'})
        assert client.get(f"/api/runs/{run['id']}").json()['state'] == 'completed'
        assert client.get(f"/api/runs/{run['id']}/metrics").json()['samples'][0]['summary']
        assert client.get(f"/api/runs/{run['id']}/download", params={'path': 'multiqc/multiqc_report.html'}).status_code == 200


def test_version_probe_timeout_and_output_limit(tmp_path, monkeypatch):
    monkeypatch.setattr('qualidock.tools.PROBE_TIMEOUT', 0.1)
    slow = executable(tmp_path, 'slow-multiqc', 'import time; time.sleep(30)')
    started = time.monotonic()
    assert 'timed out' in asyncio.run(detect_tool('multiqc', slow))['error']
    assert time.monotonic() - started < 3
    noisy = executable(tmp_path, 'noisy-multiqc', 'import sys; sys.stdout.write("x" * 20000); sys.stdout.flush()')
    assert not asyncio.run(detect_tool('multiqc', noisy))['compatible']


def test_saved_result_directory_symlink_is_rejected(client, setup):
    settings, root = setup
    source = wait(client, start(client, root, mode='fastqc')['id'])
    directory = settings.output / source['id'] / 'fastqc'
    shutil.rmtree(directory)
    directory.symlink_to(root, target_is_directory=True)
    assert client.post(f"/api/runs/{source['id']}/multiqc").status_code == 403


def test_import_size_limits(tmp_path, monkeypatch):
    destination = tmp_path / 'test_fastqc'
    shutil.copytree(FIXTURES / 'coverage_R1_fastqc', destination)
    monkeypatch.setattr('qualidock.reports.MAX_IMPORT', 8)
    with pytest.raises(ValueError, match='512 MiB'):
        discover([tmp_path], FileAccess([tmp_path]))


def test_import_path_shell_characters_are_literal(client, setup):
    settings, root = setup
    destination = root / 'saved;touch PWNED'
    shutil.copytree(FIXTURES / 'coverage_R1_fastqc', destination)
    run = wait(client, start(client, root, mode='multiqc', paths=[str(destination)])['id'])
    assert run['state'] == 'completed'
    assert not (settings.output / run['id'] / 'PWNED').exists()


def test_duplicate_sample_names_use_isolated_multiqc_directory_prefixes(client, setup):
    settings, root = setup
    first = copy_report(root)
    second = root / 'other' / 'coverage_R1_fastqc'
    shutil.copytree(first, second)
    run = wait(client, start(client, root, mode='multiqc', paths=[str(first), str(second)])['id'])
    assert run['state'] == 'completed'
    assert '--dirs' in run['executions'][0]['argv']
    assert len((settings.output / run['id'] / 'multiqc-inputs.txt').read_text().splitlines()) == 2
    assert run['sample_count'] == 2


def test_completed_legacy_manifest_and_metrics_are_not_rewritten(setup):
    from qualidock.metrics import parse_report
    settings, root = setup
    run_id = 'b' * 32
    directory = settings.output / run_id
    directory.mkdir(parents=True)
    sample = parse_report(FIXTURES / 'coverage_R1_fastqc', 'legacy')
    for key in ('basic_statistics', 'summary', 'warnings'):
        sample.pop(key)
    for module in sample['modules']:
        for key in ('available', 'metadata', 'comments', 'summary_status'):
            module.pop(key, None)
    metrics = {'schema_version': 1, 'samples': [sample]}
    manifest = {'schema_version': 1, 'id': run_id, 'name': 'Legacy completed run', 'mode': 'fastqc', 'state': 'completed', 'stage': 'Finished', 'created_at': '2026-01-01', 'updated_at': '2026-01-01', 'inputs': [], 'threads': 1, 'reports': [{'path': 'metrics.json', 'size': 0}], 'sample_count': 1}
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    (directory / 'metrics.json').write_text(json.dumps(metrics))
    original = (directory / 'manifest.json').read_bytes()
    settings.fastqc = str(root / 'now-unavailable-fastqc')
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization': f'Bearer {settings.token}'})
        assert client.get(f'/api/runs/{run_id}').json() == manifest
        assert client.get(f'/api/runs/{run_id}/metrics').json() == metrics
        assert client.get(f'/api/runs/{run_id}/download', params={'path': 'metrics.json'}).status_code == 200
    assert (directory / 'manifest.json').read_bytes() == original


@pytest.mark.parametrize('companion', ['summary.txt', 'fastqc_report.html'])
def test_import_companion_cannot_escape_roots(client, setup, companion):
    _, root = setup
    destination = copy_report(root)
    outside = root.parent / 'outside-report'; outside.write_text('private')
    (destination / companion).unlink()
    (destination / companion).symlink_to(outside)
    response = client.post('/api/runs', json={'mode':'multiqc', 'paths':[str(destination)]})
    assert response.status_code == 403


def test_version_probe_reads_fragmented_response(tmp_path):
    path = executable(tmp_path, 'multiqc', 'import sys,time; print("startup diagnostic", flush=True); time.sleep(0.03); print("multiqc, version 1.35")')
    info = asyncio.run(detect_tool('multiqc', path))
    assert info['compatible'] and info['version'] == '1.35'
