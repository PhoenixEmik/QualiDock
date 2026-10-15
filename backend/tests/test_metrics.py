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
