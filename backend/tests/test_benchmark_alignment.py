"""Small genuine execution evidence, explicitly not large/shared-storage acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import shutil

import pytest
from qualidock.tools import locate_tool

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('alignment_benchmark',ROOT/'scripts/benchmark-analysis.py')
benchmark=importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)
SAMTOOLS=shutil.which(os.environ.get('QUALIDOCK_SAMTOOLS','samtools'))
JAR=locate_tool('picard',os.environ.get('QUALIDOCK_PICARD','picard.jar'))
NANOQ=shutil.which(os.environ.get('QUALIDOCK_NANOQ','nanoq'))
INFER=shutil.which(os.environ.get('QUALIDOCK_RSEQC_INFER','infer_experiment.py'))
DIST=shutil.which(os.environ.get('QUALIDOCK_RSEQC_DISTRIBUTION','read_distribution.py'))
if os.environ.get('QUALIDOCK_REQUIRE_BENCHMARK_ALIGNMENT_TESTS')=='1' and not all([SAMTOOLS,JAR,NANOQ,INFER,DIST,shutil.which('Rscript')]):
    raise RuntimeError('All genuine optional/alignment benchmark tools are required in this CI job')


def fixture(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/f'scripts/prepare-{name}-test.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


@pytest.mark.parametrize('mode,advanced',[
    ('samtools',False),('samtools',True),('nanoq',False),
    ('rseqc-infer',False),('rseqc-distribution',False),
    ('picard',False),('picard',True),
])
def test_actual_optional_and_alignment_benchmarks(tmp_path,monkeypatch,mode,advanced):
    required=[NANOQ] if mode=='nanoq' else [SAMTOOLS,JAR] if mode=='picard' else [SAMTOOLS,INFER,DIST] if mode.startswith('rseqc') else [SAMTOOLS]
    if not all(required) or advanced and mode=='picard' and not shutil.which('Rscript'):pytest.skip('Provisioned genuine tools required')
    flags=[]
    for name,executable in [('SAMTOOLS',SAMTOOLS),('PICARD',JAR),('NANOQ',NANOQ),('RSEQC_INFER',INFER),('RSEQC_DISTRIBUTION',DIST)]:
        if executable:monkeypatch.setenv('QUALIDOCK_'+name,executable)
    if mode=='nanoq':source=ROOT/'backend/tests/fixtures/fastqc-0.13.0/coverage_R1.fastq.gz'
    elif mode=='samtools':
        bam,cram,reference=fixture('alignment').prepare(tmp_path/'inputs',SAMTOOLS)
        source=cram if advanced else bam
        if advanced:
            monkeypatch.setenv('QUALIDOCK_ALIGNMENT_REFERENCES',json.dumps({'local':str(reference)}));flags+=['--alignment-reference','local']
    elif mode=='picard':
        source=fixture('insert').prepare(tmp_path/'inputs',SAMTOOLS)
        if advanced:flags+=['--picard-histogram-pdf','--picard-include-duplicates']
    else:
        source,annotation=fixture('rna').prepare(tmp_path/'inputs',SAMTOOLS)
        monkeypatch.setenv('QUALIDOCK_RNA_ANNOTATIONS',json.dumps({'genes':str(annotation)}));flags+=['--rna-annotation','genes']
        if mode=='rseqc-infer':flags+=['--rna-sample-size','1000','--rna-mapq','30']
    output=tmp_path/'evidence'
    args=benchmark.parser().parse_args(['--input',str(source),'--output',str(output),'--mode',mode,'--threads','1','--memory-mb','1024','--hash-inputs',*flags])
    benchmark.main(args)
    data=json.loads((output/'benchmark.json').read_text())
    assert data['status']=='measured' and data['terminal_state']=='completed'
    assert data['input_integrity_unchanged'] and data['hash_only_source_passes']==2
    assert data['input_bytes']==source.stat().st_size and not data['derived_outputs'] and not data['unpublished_fastqs']
    assert data['registered_report_bytes']>0 and data['waited_child_cpu_seconds']>0 and data['submission_seconds']>0
    assert data['execution_stages'] and all(s['resources']['elapsed_seconds']>0 for s in data['execution_stages'])
    assert data['sampled_read_bytes'] is None and data['sampled_write_bytes'] is None
    if mode=='nanoq':
        assert data['validation_scans'][0]['bytes_read']==source.stat().st_size
        assert data['validation_scans'][0]['coverage']=='full'
    else:
        assert not data['validation_scans'] and data['alignment_validation']
        assert data['validation_observed_seconds']>0
        assert data['execution_stages'][0]['role']=='alignment_preflight'
        if mode=='samtools':assert data['execution_stages'][-1]['role']=='tool_execution'
    if mode.startswith('rseqc'):assert data['annotation']['sha256'] and data['qc_options']['annotation']=='genes'
    if mode=='picard':
        assert data['jvm_observation']['picard_version']=='3.5.0' and data['jvm_observation']['heaps_mb']==[576]
        assert 'not measured' in data['jvm_observation']['scope']
    destination=Path('validation/benchmarks/alignment-rna');destination.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(output/'benchmark.json',destination/(mode+('-advanced' if advanced else '')+'.json'))


@pytest.mark.skipif(not SAMTOOLS or not JAR,reason='Genuine Picard required')
def test_picard_benchmark_cancellation_records_actual_terminal_state(tmp_path,monkeypatch):
    monkeypatch.setenv('QUALIDOCK_SAMTOOLS',SAMTOOLS);monkeypatch.setenv('QUALIDOCK_PICARD',JAR)
    bam=fixture('insert').prepare(tmp_path/'inputs',SAMTOOLS);output=tmp_path/'evidence'
    args=benchmark.parser().parse_args(['--input',str(bam),'--output',str(output),'--mode','picard','--cancel-after','0','--hash-inputs','--memory-mb','1024'])
    benchmark.main(args);data=json.loads((output/'benchmark.json').read_text())
    assert data['terminal_state']=='cancelled' and data['cancellation_requested']
    assert data['input_integrity_unchanged'] and not data['derived_outputs']


@pytest.mark.parametrize('flags',[['--rna-annotation','genes'],['--rna-mapq','20'],['--picard-by-library']])
def test_benchmark_rejects_unrelated_tool_options_without_creating_output(tmp_path,flags):
    source=ROOT/'backend/tests/fixtures/fastqc-0.13.0/coverage_R1.fastq.gz'
    args=benchmark.parser().parse_args(['--input',str(source),'--output',str(tmp_path/'unused'),'--mode','fastqc',*flags])
    with pytest.raises(ValueError):benchmark.main(args)
    assert not args.output.exists()



def test_unqualified_rna_benchmark_is_not_advertised_without_native_annotation_settings():
    # Production RNA mode is available through the app. The benchmark's BED12
    # arguments are not a native refFlat/explicit-strand contract (pending #5).
    with pytest.raises(SystemExit):
        benchmark.parser().parse_args(['--input','input.bam','--output','new-output','--mode','picard-rna'])
