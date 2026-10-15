from pathlib import Path
import json
import zipfile

import pytest
from qualidock.metrics import parse_report, parse_text, number, parse_multiqc

FIXTURES = Path(__file__).parent / 'fixtures/fastqc-0.13.0'
MODULES = ['Basic Statistics', 'Per base sequence quality', 'Per tile sequence quality',
           'Per sequence quality scores', 'Per base sequence content', 'Per sequence GC content',
           'Per base N content', 'Sequence Length Distribution', 'Sequence Duplication Levels',
           'Overrepresented sequences', 'Adapter Content', 'Kmer Content']


@pytest.mark.parametrize('name', MODULES)
def test_each_module_preserves_real_fastqc_rows_and_status(name):
    path = FIXTURES / 'coverage_R1_fastqc'
    sample = parse_report(path, 'real')
    module = next(m for m in sample['modules'] if m['name'] == name)
    raw = (path / 'fastqc_data.txt').read_text().split(f'>>{name}\t', 1)[1].split('>>END_MODULE', 1)[0]
    lines = raw.splitlines()
    assert module['status'] == lines[0]
    assert module['summary_status'] == lines[0]
    assert module['rows'] == [line.split('\t') for line in lines[1:] if line and not line.startswith('#')]
    assert module['comments'] == [line[1:] for line in lines[1:] if line.startswith('#')]
    assert sample['fastqc_version'] == '0.13.0'
    assert sample['status'] == 'fail'  # Scientific QC failure is independent of process success.


def test_grouped_quality_is_exact_not_interpolated():
    sample = parse_report(FIXTURES / 'coverage_R1_fastqc', 'real')
    raw = next(m for m in sample['modules'] if m['name'] == 'Per base sequence quality')['rows']
    for values, reported in zip(raw, sample['per_base_quality'], strict=True):
        assert reported['base'] == values[0]
        assert list(reported.values())[1:] == [float(v) for v in values[1:]]
    assert {'10-14', '15-19', '20-24'} <= {b['base'] for b in sample['per_base_quality']}
    duplication = next(m for m in sample['modules'] if m['name'] == 'Sequence Duplication Levels')
    assert duplication['columns'] == ['Duplication Level', 'Percentage of total']
    assert duplication['metadata'][0][0] == 'Total Deduplicated Percentage'


def test_zip_extracted_and_text_are_equivalent(tmp_path):
    source = FIXTURES / 'coverage_R1_fastqc'
    archive = tmp_path / 'real_fastqc.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for file in source.iterdir():
            z.write(file, f'real_fastqc/{file.name}')
    expected = parse_report(source, 'same-id')
    assert parse_report(archive, 'same-id') == expected
    assert parse_report(source / 'fastqc_data.txt', 'same-id') == expected


@pytest.mark.parametrize(('raw', 'expected'), [('0', 0), ('9007199254740993', 9007199254740993), ('0.000000000123456789', 0.000000000123456789), ('1e-20', 1e-20), ('', None), ('NaN', None), ('Infinity', None), ('N/A', None), ('-', None)])
def test_numeric_precision_and_missing_values(raw, expected):
    assert number(raw) == expected


def test_missing_value_retains_raw_cell():
    text = (FIXTURES / 'coverage_R1_fastqc/fastqc_data.txt').read_text()
    lines = text.splitlines()
    index = lines.index('#Base\tMean\tMedian\tLower Quartile\tUpper Quartile\t10th Percentile\t90th Percentile') + 1
    values = lines[index].split('\t'); values[1] = 'NaN'; lines[index] = '\t'.join(values)
    sample = parse_text('\n'.join(lines), 'missing-value-case')
    assert sample['per_base_quality'][0]['mean'] is None
    assert next(m for m in sample['modules'] if m['name'] == 'Per base sequence quality')['rows'][0][1] == 'NaN'


def test_summary_only_module_and_disagreement():
    text = (FIXTURES / 'coverage_R1_fastqc/fastqc_data.txt').read_text()
    sample = parse_text(text, 'real', 'WARN\tBasic Statistics\tcoverage_R1.fastq.gz\nFAIL\tOptional future module\tcoverage_R1.fastq.gz\n')
    assert sample['warnings'] and sample['modules'][0]['status'] == 'pass'
    missing = next(m for m in sample['modules'] if m['name'] == 'Optional future module')
    assert missing['available'] is False and missing['summary_status'] == 'fail'


def test_report_symlink_and_size_boundaries(tmp_path, monkeypatch):
    path = tmp_path / 'link'
    path.symlink_to(FIXTURES.resolve() / 'coverage_R1_fastqc', target_is_directory=True)
    with pytest.raises(ValueError): parse_report(path, 'link')
    monkeypatch.setattr('qualidock.metrics.MAX_DATA', 8)
    with pytest.raises(ValueError): parse_report(FIXTURES / 'coverage_R1_fastqc', 'large')


def test_multiqc_general_stats_preserve_raw_values(tmp_path):
    # Unit-level schema example, not a scientific or execution acceptance fixture.
    path = tmp_path / 'multiqc_data.json'
    path.write_text(json.dumps({'report_general_stats_headers': [{'total': {'title': 'Reads', 'suffix': ' M', 'modify': None}}], 'report_general_stats_data': [{'sample': {'total': 1234567, 'gc': 48.125}}]}))
    summary = parse_multiqc(path)
    assert summary['rows'] == [{'sample': 'sample', 'values': {'0:total': 1234567, '0:gc': 48.125}}]
    assert summary['columns'][0]['unit'] == ' M'  # Stored metadata; never apply display scaling.


@pytest.mark.parametrize('shape', ['list', 'sections'])
def test_general_stats_supported_shapes_and_absent_values(tmp_path, shape):
    headers = {'count': {'title': 'Reads'}, 'absent': {'title': 'Not reported'}}
    values = {'R1': {'count': 400}, 'R2': {'count': 401, 'absent': None}}
    data = {'report_general_stats_headers': [headers] if shape == 'list' else {'fastqc': headers}, 'report_general_stats_data': [values] if shape == 'list' else {'fastqc': values}}
    path = tmp_path / 'stats.json'; path.write_text(json.dumps(data))
    result = parse_multiqc(path)
    assert result['status'] == 'available' and len(result['rows']) == 2
    assert len(result['columns']) == 2
    assert not any(key.endswith(':absent') for row in result['rows'] for key in row['values'])


@pytest.mark.parametrize(('data', 'status'), [({}, 'missing'), ({'report_general_stats_headers': [], 'report_general_stats_data': []}, 'empty'), ({'report_general_stats_headers': {}, 'report_general_stats_data': {}}, 'empty'), ({'report_general_stats_headers': [], 'report_general_stats_data': {}}, 'unsupported')])
def test_general_stats_missing_empty_and_unsupported_are_distinct(tmp_path, data, status):
    path = tmp_path / 'stats.json'; path.write_text(json.dumps(data))
    result = parse_multiqc(path)
    assert result['status'] == status and result['message'] and result['rows'] == []


@pytest.mark.parametrize('data', [[], {'report_general_stats_headers': {}, 'report_general_stats_data': {'fastqc': []}}, {'report_general_stats_headers': [{}], 'report_general_stats_data': [{'sample': 'not a row'}]}])
def test_general_stats_malformed_is_not_a_valid_empty_table(tmp_path, data):
    path = tmp_path / 'stats.json'; path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Malformed'): parse_multiqc(path)


@pytest.mark.parametrize('version', ['1.25.1', '1.35'])
def test_genuine_versioned_multiqc_regression(version):
    import hashlib
    folder = Path(__file__).parent/'fixtures/multiqc'/version
    path = folder/'general-stats.json'
    original = json.loads(path.read_text())
    provenance = json.loads((folder/'provenance.json').read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == provenance['fixture_sha256']
    for name, digest in provenance['inputs'].items():
        assert hashlib.sha256((Path(__file__).resolve().parents[2]/name).read_bytes()).hexdigest() == digest
    assert original['config_version'] == version
    tables = original['report_general_stats_data']
    assert isinstance(tables, dict if version == '1.35' else list)
    sections = tables.items() if isinstance(tables, dict) else ((str(i), value) for i, value in enumerate(tables))
    parsed = parse_multiqc(path)
    assert parsed['status'] == 'available'
    assert {row['sample'] for row in parsed['rows']} == {'coverage_R1', 'coverage_R2'}
    rows = {row['sample']: row['values'] for row in parsed['rows']}
    columns = {column['key']: column for column in parsed['columns']}
    headers = original['report_general_stats_headers']
    for section, table in sections:
        metadata = headers[section] if isinstance(headers, dict) else headers[int(section)]
        for key, value in metadata.items():
            column = columns[f'{section}:{key}']
            assert column['raw_key'] == key
            assert column['title'] == value.get('title', key)
            assert column['unit'] == value.get('suffix', '')
        for sample, values in table.items():
            for key, value in values.items():
                if value is not None:
                    assert rows[sample][f'{section}:{key}'] == value
            assert values['total_sequences'] == 400  # Raw read count, never rescale to millions.

@pytest.mark.parametrize('version', ['1.25.1', '1.35'])
def test_multiqc_raw_units_and_version_are_not_display_scaling(version):
    path = Path(__file__).parent / 'fixtures/multiqc' / version / 'general-stats.json'
    parsed = parse_multiqc(path)
    assert parsed['version'] == version
    assert parsed['tool'] == 'MultiQC'
    total = next(c for c in parsed['columns'] if c['raw_key'] == 'total_sequences')
    assert total['unit'].strip() == 'M'
    assert total['raw_unit'] == 'reads'
    assert parsed['rows'][0]['values'][total['key']] == 400
    assert next(c for c in parsed['columns'] if c['raw_key'] == 'percent_gc')['raw_unit'] == '%'
