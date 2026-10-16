"""Saved genuine module values plus explicitly synthetic domain/QC-double records."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import time

import pytest

from qualidock.cohort import METRICS, reported_metric, length_range, declared_rule, flag
from qualidock.metrics import parse_report
from test_catalog import domain, create, attach
from test_workspace import start, wait
from test_validation_jobs import finish


def ready(client, root, *, project_name='Project A'):
    _, base, sample, sequencing = domain(client, project_name)
    run = wait(client, start(client, root)['id'])
    attach(client, base, run, sample, sequencing)
    assert client.post('/api/runs/' + run['id'] + '/integrity', json={'mode': 'full'}).status_code == 202
    assert finish(client, run['id'])['result'] == 'passed'
    return base, sample, sequencing, run


def query(client, base, **body):
    response = client.post(base + '/comparisons/query', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_exact_q30_denominators_rule_file_run_and_source_export_fidelity(client, setup):
    _, root = setup
    base, sample, sequencing, run = ready(client, root)
    result = query(client, base, rule={'minimum_percent': '99.999999999999999999'})
    assert result['total'] == 2 and not result['excluded_total']
    assert all((p['value'], p['numerator'], p['denominator'], p['raw_value']) == (100, 4, 4, '4/4') for p in result['points'])
    assert all(p['rule_result'] == 'within_declared_reference' for p in result['points'])
    assert all(p['sources'][0]['analysis_id'] == run['id'] and p['sources'][0]['source_sha256'] for p in result['points'])
    assert all(p['context']['sample_id'] == sample['id'] and p['context']['sequencing_run_id'] == sequencing['id'] for p in result['points'])
    assert {p['context']['read'] for p in result['points']} == {'R1', 'R2'}
    assert str(root) not in json.dumps(result)
    rolled = query(client, base, group_by='run', rule={'minimum_percent': 90})
    assert rolled['total'] == 1
    assert (rolled['points'][0]['value'], rolled['points'][0]['numerator'], rolled['points'][0]['denominator']) == (100, 8, 8)
    assert rolled['points'][0]['file_count'] == len(rolled['points'][0]['sources']) == 2
    body = {'rule': {'minimum_percent': '99.999999999999999999'}, 'fingerprint': result['fingerprint'], 'definition_id': result['selected_group'], 'format': 'csv', 'mode': 'verbatim'}
    response = client.post(base + '/comparisons/export', json=body)
    assert response.status_code == 200 and response.headers['content-disposition'].startswith('attachment;')
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 2
    assert all(row['numerator'] == row['denominator'] == '4' and row['unit'] == '%' and row['value'] == '100.0' for row in rows)
    assert all(json.loads(row['source_provenance'])[0]['analysis_id'] == run['id'] for row in rows)
    tsv = client.post(base + '/comparisons/export', json={**body, 'format': 'tsv'})
    assert list(csv.DictReader(io.StringIO(tsv.text), delimiter='\t')) == rows
    assert all(row['comparison_fingerprint'] == result['fingerprint'] for row in rows)


def test_unknown_and_conflicting_stages_excluded_bulk_context_atomic_and_sources_unchanged(client, setup):
    settings, root = setup
    base, sample, sequencing, run = ready(client, root)
    client.patch(base + '/sequencing-runs/' + sequencing['id'], json={'revision': 1, 'fields': {'input_stage': 'unknown'}})
    original = (settings.output / run['id'] / 'manifest.json').read_bytes()
    original_inputs = {p: p.read_bytes() for p in root.glob('*.fastq')}
    unknown = query(client, base)
    assert unknown['total'] == 0 and unknown['excluded_total'] == 2
    assert all(p['value'] == 100 and 'stage is unknown' in p['reason'] for p in unknown['excluded'])
    assert unknown['unknown_stage_run_total'] == 1
    record = unknown['unknown_stage_runs'][0]
    project_id = sample['project_id']
    body = {'project_ids': [project_id], 'records': [{'id': record['id'], 'revision': record['revision']}], 'fields': {'input_stage': 'raw_fastq'}}
    assert client.patch(base + '/comparisons/run-context', json=body).status_code == 200
    assert client.patch(base + '/comparisons/run-context', json=body).status_code == 409
    assert query(client, base)['total'] == 2
    assert (settings.output / run['id'] / 'manifest.json').read_bytes() == original
    assert all(path.read_bytes() == contents for path, contents in original_inputs.items())
    assert client.post('/api/runs/' + run['id'] + '/yield-targets', json={'targets': [], 'input_stage': 'upstream_processed'}).status_code == 200
    conflict = query(client, base)
    assert conflict['total'] == 0 and all('declarations conflict' in p['reason'] for p in conflict['excluded'])
    second = create(client, base + '/sequencing-runs', 'Second run')
    invalid = {**body, 'records': [{'id': sequencing['id'], 'revision': 3}, {'id': second['id'], 'revision': 999}], 'fields': {'platform': 'Do not partially write'}}
    assert client.patch(base + '/comparisons/run-context', json=invalid).status_code == 409
    assert client.get(base + '/sequencing-runs/' + sequencing['id']).json()['declared']['platform'] == 'Declared Illumina'


def test_missing_numeric_values_and_stale_input_never_become_zero_or_run_totals(client, setup):
    _, root = setup
    _, base, sample, sequencing = domain(client)
    run = wait(client, start(client, root)['id'])
    attach(client, base, run, sample, sequencing)
    missing = query(client, base)
    assert missing['total'] == 0 and len(missing['excluded']) == 2
    assert all(p['value'] is None and 'known quality encoding' in p['reason'] for p in missing['excluded'])
    assert query(client, base, metric='reads')['total'] == 2
    assert client.post('/api/runs/' + run['id'] + '/integrity', json={'mode': 'full'}).status_code == 202
    finish(client, run['id'])
    fresh = query(client, base)
    assert fresh['total'] == 2
    (root / 'sample_R2_001.fastq').write_text('@changed\nACGT\n+\nIIII\n')
    changed = query(client, base)
    assert changed['total'] == changed['excluded_total'] == 1
    rolled = query(client, base, group_by='run')
    assert rolled['total'] == 0 and 'no partial' in rolled['excluded'][0]['reason']
    assert client.post(base + '/comparisons/export', json={'fingerprint': fresh['fingerprint']}).status_code == 409


def test_context_filters_dates_lengths_and_compatible_definitions(client, setup):
    _, root = setup
    base, sample, sequencing, _ = ready(client, root)
    assert query(client, base, filters={'platform': 'not the declared platform'})['excluded_total'] == 2
    assert query(client, base, filters={'date_from': '2026-10-17'})['total'] == 0
    assert query(client, base, filters={'date_from': '20261016', 'date_to': '2026-10-16'})['total'] == 2
    assert query(client, base, filters={'length_min': 4, 'length_max': 4})['total'] == 2
    assert query(client, base, filters={'length_min': 5})['total'] == 0
    assert query(client, base, metric='length_min')['points'][0]['value'] == 4
    assert query(client, base, metric='length_max')['points'][0]['raw_value'] == '4'
    second = create(client, base + '/samples', 'Different assay', assay='Amplicon')
    association = client.get(base + '/associations').json()['items'][0]
    assignment = {'file_id': association['file_id'], 'sample_id': second['id'], 'sequencing_run_id': sequencing['id'], **association['declared']}
    assert client.patch(base + '/associations/' + association['id'], json={'revision': 1, 'assignment': assignment, 'reason': 'Explicit differing experimental context'}).status_code == 200
    split = query(client, base)
    assert len(split['groups']) == 2 and split['total'] == split['excluded_total'] == 1
    assert 'Different metric definition' in split['excluded'][0]['reason']
    group = next(g for g in split['groups'] if g['id'] != split['selected_group'])
    other = query(client, base, definition_id=group['id'])
    assert other['points'][0]['context']['assay'] != split['points'][0]['context']['assay']
    assert query(client, base, group_by='run')['total'] == 0  # Never sum across incompatible assay definitions.


def test_genuine_report_raw_precision_grouped_adapter_bins_and_missing_theory():
    fixture = Path(__file__).parent / 'fixtures/fastqc-0.13.0/coverage_R1_fastqc'
    sample = parse_report(fixture, 'actual-report')
    file = {'qc_snapshot_matches': True, 'sequence_length': sample['sequence_length']}
    run = {'id': 'actual-source-analysis', 'tools': {'fastqc': {'version': '0.13.0'}}}
    duplicate = reported_metric(file, run, sample, 'deduplicated_percent')
    assert duplicate['raw_value'] == '75.25' and duplicate['value'] == 75.25
    gc = reported_metric(file, run, sample, 'gc_percent')
    assert gc['raw_value'] == '47' and gc['value'] == 47
    adapter = reported_metric(file, run, sample, 'adapter_bin_percent', 'Illumina Universal Adapter', '10-14')
    assert adapter['raw_value'] == '0.0' and adapter['value'] == 0
    assert adapter['definition']['position'] == '10-14'
    assert 'unverified-across-analyses:' in adapter['definition']['adapter_definition']
    missing = reported_metric(file, run, sample, 'adapter_bin_percent', 'Illumina Universal Adapter', '10-19')
    assert missing['value'] is None and 'missing' in missing['reason']
    assert reported_metric(file, run, sample, 'adapter_bin_percent')['value'] is None
    assert length_range('150-151') == (150, 151)
    assert length_range('NA') is None
    assert length_range('151-150') is None
    sample['basic_statistics']['%GC'] = 'NaN'
    assert reported_metric(file, run, sample, 'gc_percent')['value'] is None


@pytest.mark.parametrize('rule', [{'minimum_percent': 'NaN'}, {'minimum_percent': 101}, {'minimum_percent': -1}, {'threshold': 80}, {'minimum_percent': True}])
def test_declared_rule_validation_and_no_universal_fastqc_classification(rule):
    with pytest.raises(ValueError):
        declared_rule(rule, 'q30_percent')
    assert flag({'reason': None, 'value': 0, 'numerator': 0, 'denominator': 4}, declared_rule({'minimum_percent': '80'}, 'q30_percent')) == 'review'
    assert flag({'reason': 'Missing context', 'value': 0}, declared_rule({'minimum_percent': 80}, 'q30_percent')) is None


@pytest.mark.parametrize('body', [
    {'metric': 'inferred_q30'}, {'group_by': 'merged_biology'}, {'metric': 'gc_percent', 'group_by': 'run'},
    {'filters': {'platform': []}}, {'filters': {'date_from': 'invalid'}}, {'filters': {'length_min': True}},
    {'filters': {'length_min': 5, 'length_max': 1}}, {'filters': {'date_from': '2026-10-17', 'date_to': '2026-10-16'}},
    {'limit': 101}, {'offset': -1}, {'sample_ids': []}, {'project_ids': []}, {'rule': {'minimum_percent': {}}},
])
def test_bad_queries_are_validation_errors_not_unbounded_or_shell_work(client, setup, body):
    _, root = setup
    base, *_ = ready(client, root)
    assert client.post(base + '/comparisons/query', json=body).status_code in {400, 404, 422}


def test_cross_project_duplicates_and_metadata_do_not_name_match(client, setup):
    _, root = setup
    base, sample, _, _ = ready(client, root)
    other, other_sample, _, _ = ready(client, root, project_name='Independent project')
    assert sample['id'] != other_sample['id']
    assert client.post(base + '/comparisons/query', json={'sample_ids': [other_sample['id']]}).status_code == 400
    combined = query(client, base, project_ids=[sample['project_id'], other_sample['project_id']])
    assert combined['total'] == 0
    assert all('conflicting project/sample/run' in p['reason'] for p in combined['excluded'])


def test_100_synthetic_metadata_records_paged_exports_and_no_unbounded_response(client, setup):
    """Synthetic 100-file QC-double cohort exercises size limits, not scientific validity."""
    _, root = setup
    for index in range(100):
        (root / f'synthetic-ui-{index:03}.fastq').write_text('@synthetic\nACGT\n+\nIIII\n')
    paths = [str(p) for p in sorted(root.glob('synthetic-ui-*.fastq'))]
    _, base, sample, sequencing = domain(client)
    run = wait(client, start(client, root, mode='fastqc', paths=paths)['id'], timeout=30)
    attach(client, base, run, sample, sequencing)
    first = query(client, base, metric='reads', limit=25)
    assert first['total'] == 100 and len(first['points']) == 25
    second = query(client, base, metric='reads', offset=25, limit=25)
    assert not {p['id'] for p in first['points']} & {p['id'] for p in second['points']}
    assert first['fingerprint'] == second['fingerprint']
    exported = client.post(base + '/comparisons/export', json={'metric': 'reads', 'fingerprint': first['fingerprint'], 'limit': 25, 'mode': 'verbatim'})
    assert exported.status_code == 200 and len(list(csv.DictReader(io.StringIO(exported.text)))) == 100
    assert client.post(base + '/comparisons/query', json={'limit': 101}).status_code == 422


def test_comparison_auth_csrf_project_scope_and_export_formula_protection(client, setup):
    _, root = setup
    base, sample, sequencing, _ = ready(client, root)
    # Share the running ASGI app without starting a second results-store owner.
    stranger = client.__class__(client.app, headers={'X-QualiDock-Request': '1'})
    try:
        for suffix in ['/comparisons/query', '/comparisons/export', '/comparisons/run-context']:
            assert stranger.post(base + suffix, json={}).status_code == 401
    finally:
        stranger.close()
    assert client.post(base + '/comparisons/query', json={}, headers={'Origin': 'https://evil.example'}).status_code == 403
    _, other, _, _ = domain(client, 'Unselected')
    assert client.post(base + '/comparisons/query', json={'project_ids': [other.rsplit('/', 1)[1]]}).status_code == 400
    assert client.patch(base + '/samples/' + sample['id'], json={'revision': sample['revision'], 'fields': {'display_name': '=UNTRUSTED()'}}).status_code == 200
    value = query(client, base)
    response = client.post(base + '/comparisons/export', json={'fingerprint': value['fingerprint']})
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert all(row['sample_name'] == "\t=UNTRUSTED()" for row in rows)
