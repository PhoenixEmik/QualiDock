"""Test-only CollectRnaSeqMetrics contracts, not a production adapter."""
from decimal import Decimal
import importlib.util
import json
from pathlib import Path

import pytest
from qualidock.files import approved_file

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('picard_rna_qualification',ROOT/'scripts/qualify-picard-rna.py')
STUDY=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(STUDY)
FIX=ROOT/'backend/tests/fixtures/picard-3.5.0/rna'


def test_original_upstream_outputs_and_geometry_are_unchanged():
    for name,sha in json.loads((FIX/'sha256.json').read_text()).items():
        assert STUDY.digest(FIX/name)==sha
    row=STUDY.metrics(FIX/'categories-NONE.rna_metrics.txt')['rows'][0]
    assert {key:int(row[key]) for key in ['PF_BASES','PF_ALIGNED_BASES','CODING_BASES','UTR_BASES','INTRONIC_BASES','INTERGENIC_BASES']}=={
        'PF_BASES':350,'PF_ALIGNED_BASES':300,'CODING_BASES':100,'UTR_BASES':50,'INTRONIC_BASES':50,'INTERGENIC_BASES':100}
    assert row['RIBOSOMAL_BASES']==row['PCT_RIBOSOMAL_BASES']==''
    assert row['PCT_CODING_BASES']=='0.333333'
    assert STUDY.metrics(FIX/'with-rrna.rna_metrics.txt')['rows'][0]['RIBOSOMAL_BASES']=='50'


@pytest.mark.parametrize('strand,counts',zip(STUDY.STRANDS,[(0,0),(2,1),(1,2)]))
def test_unpaired_strand_choices_preserve_original_counts(strand,counts):
    row=STUDY.metrics(FIX/f'categories-{strand}.rna_metrics.txt')['rows'][0]
    assert (int(row['CORRECT_STRAND_READS']),int(row['INCORRECT_STRAND_READS']))==counts


@pytest.mark.parametrize('direction',['plus','minus'])
def test_uniform_and_biased_profiles_preserve_original_coverage(direction):
    for kind,expected in [('flat',('1','1','1')),('bias',('1.5','0.75','2'))]:
        report=STUDY.metrics(FIX/f'{kind}-{direction}-NONE.rna_metrics.txt')
        row=report['rows'][0]
        assert tuple(Decimal(row[key]) for key in ['MEDIAN_5PRIME_BIAS','MEDIAN_3PRIME_BIAS','MEDIAN_5PRIME_TO_3PRIME_BIAS'])==tuple(map(Decimal,expected))
        assert [int(v[0]) for v in report['histogram']]==list(range(101))
        if kind=='flat':assert all(Decimal(v[1])==1 for v in report['histogram'])


def test_no_eligible_transcript_does_not_mean_zero_biological_bias():
    for name in ['empty','boundary-spliced']:
        report=STUDY.metrics(FIX/f'{name}-NONE.rna_metrics.txt')
        assert report['rows'][0]['MEDIAN_5PRIME_BIAS']=='0' # genuine upstream default
        assert report['histogram']==[]
    assert len(STUDY.metrics(FIX/'by-library.rna_metrics.txt')['rows'])==2


@pytest.mark.parametrize('fault',['class','truncated','nonfinite','oversize'])
def test_incomplete_or_unsupported_report_is_not_qualified(tmp_path,fault):
    payload=(FIX/'categories-NONE.rna_metrics.txt').read_text()
    if fault=='class':payload=payload.replace('picard.analysis.RnaSeqMetrics','picard.analysis.InsertSizeMetrics')
    elif fault=='truncated':payload=payload[:payload.index('\n350\t')]
    elif fault=='nonfinite':payload=payload.replace('350\t300\t','NaN\t300\t')
    else:payload+='x'*1024*1024
    path=tmp_path/'report.txt';path.write_text(payload)
    with pytest.raises(ValueError):STUDY.metrics(path)


def test_reused_operator_file_contract_rejects_symlinks_and_unsafe_permissions(tmp_path):
    annotation=tmp_path/'genes.refFlat';annotation.write_text(STUDY.REF);annotation.chmod(0o600)
    assert approved_file(annotation)==annotation
    link=tmp_path/'alias.refFlat';link.symlink_to(annotation)
    with pytest.raises(ValueError):approved_file(link)
    annotation.chmod(0o666)
    with pytest.raises(ValueError):approved_file(annotation)


def test_fixture_generation_stays_test_only_and_preserves_gene_identity(tmp_path):
    path=STUDY.fixture(tmp_path/'fixture','categories')
    assert not path.exists() # Actual BAM creation is exclusively upstream samtools.
    fields=(path.parent/'genes.refFlat').read_text().strip().split('\t')
    assert fields==['geneA','txA','chrRNA','+','100','900','200','800','2','100,500,','300,900,']
    assert 'CollectRnaSeqMetrics' not in (ROOT/'backend/qualidock/optional_qc.py').read_text()
