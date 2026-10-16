"""Optional QC parsers use original tool output, including rejection mutations."""
import asyncio
import json
from pathlib import Path
import pytest
from qualidock.optional_qc import parse_nanoq
from qualidock.tools import detect_tool

FIXTURE = Path(__file__).parent / 'fixtures/nanoq-0.10.0'


def test_original_nanoq_json_preserves_exact_values():
    original = json.loads((FIXTURE / 'nanoq.json').read_text())
    assert parse_nanoq(FIXTURE / 'nanoq.json') == original
    assert original['n50'] == 1475 and original['mean_quality'] == 19.090294
    assert original['length_thresholds']['1000'] == 17


@pytest.mark.parametrize('changes', [
    {'reads': 0}, {'bases': 0}, {'filtered': 1}, {'mean_quality': None},
    {'mean_quality': float('nan')}, {'reads': True}, {'n50': 0},
    {'quality_thresholds': {'10': 21}}, {'length_thresholds': None},
])
def test_nanoq_invalid_statistics_are_not_evidence(tmp_path, changes):
    data = json.loads((FIXTURE / 'nanoq.json').read_text())
    data.update(changes)
    report = tmp_path / 'report.json'; report.write_text(json.dumps(data))
    with pytest.raises(ValueError): parse_nanoq(report)


@pytest.mark.parametrize('text', ['{', '[]', '{"reads":20,"reads":0}', 'x' * (1024 * 1024 + 1)])
def test_nanoq_malformed_or_oversized(tmp_path, text):
    report = tmp_path / 'report.json'; report.write_text(text)
    with pytest.raises(ValueError): parse_nanoq(report)


def test_missing_nanoq_is_optional():
    info = asyncio.run(detect_tool('nanoq', '/missing/nanoq'))
    assert not info['compatible'] and not info['available']


def test_nanoq_report_symlink(tmp_path):
    report = tmp_path / 'linked.json'; report.symlink_to((FIXTURE / 'nanoq.json').resolve())
    with pytest.raises(ValueError): parse_nanoq(report)


def test_optional_tool_absence_and_invalid_settings(client, setup):
    _, root=setup
    path=str(next(root.glob('*.fastq')))
    client.app.state.manager.settings.nanoq='/missing/nanoq'
    assert not client.get('/api/config').json()['tools']['nanoq']
    assert client.post('/api/runs',json={'mode':'nanoq','paths':[path]}).status_code==400
    assert client.post('/api/runs',json={'mode':'nanoq','paths':[path], 'processing_options':{'fast':True}}).status_code==400
    response=client.post('/api/runs',json={'mode':'fastqc','paths':[path]})
    assert response.status_code==201,response.text
