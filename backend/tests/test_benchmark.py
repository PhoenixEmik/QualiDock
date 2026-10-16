"""Benchmark acceptance uses real tools/FASTQ contents, not fabricated QC results."""
import importlib.util
import json
import shutil
from pathlib import Path
import pytest
from test_processing_real import FASTP, SEQKIT, FASTQC, MULTIQC, FIXTURE

spec = importlib.util.spec_from_file_location('benchmark', Path(__file__).resolve().parents[2]/'scripts/benchmark-analysis.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.mark.skipif(not all((FASTP,SEQKIT,FASTQC,MULTIQC)), reason='All genuine processing/QC tools required')
@pytest.mark.parametrize('mode,flags',[
    ('fastqc',[]),('both',[]),('fastp',[]),('fastp',['--compare-qc','--multiqc']),
    ('seqkit-stats',[]),('seqkit-sample',['--fraction','0.25']),
    ('seqkit-sample',['--count','7','--seed','73']),
    ('seqkit-filter',['--min-length','151']),
    ('seqkit-filter',['--min-length','151','--preserve-pairs']),
    ('seqkit-extract',[]),('seqkit-extract',['--preserve-pairs']),
])
def test_real_benchmark(tmp_path, monkeypatch, mode, flags):
    for name, executable in [('FASTP',FASTP),('SEQKIT',SEQKIT),('FASTQC',FASTQC),('MULTIQC',MULTIQC)]:
        monkeypatch.setenv('QUALIDOCK_'+name, executable)
    ids=tmp_path/'ids.txt'
    # An exact genuine fixture ID, shared by the real mates.
    import gzip
    with gzip.open(FIXTURE/'coverage_R1.fastq.gz','rb') as stream:
        identifier=stream.readline()[1:].split()[0].decode()
    ids.write_text(identifier+'\n')
    if mode=='seqkit-extract': flags=[*flags,'--identifiers',str(ids)]
    output=tmp_path/'evidence'
    args=benchmark.parser().parse_args(['--input',*[str(FIXTURE/f'coverage_R{r}.fastq.gz') for r in (1,2)],'--output',str(output),'--mode',mode,'--threads','1','--hash-inputs',*flags])
    benchmark.main(args)
    evidence=json.loads((output/'benchmark.json').read_text())
    retained=Path('validation/benchmarks'); retained.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(output/'benchmark.json',retained/(mode+'-'+str(len(flags))+'-'+str('--preserve-pairs' in flags)+'.json'))
    assert evidence['status']=='measured' and evidence['run']['state']=='completed'
    assert evidence['input_integrity_unchanged'] and evidence['hash_only_source_passes']==2
    assert evidence['execution_stages'] and not evidence['unpublished_fastqs']
    assert evidence['waited_child_cpu_seconds']>0
    assert evidence['sampled_read_bytes'] is None and evidence['sampled_write_bytes'] is None
    assert all(s['exit_code']==0 for s in evidence['execution_stages'])
    if mode.startswith('seqkit-') or mode=='fastp':
        assert len(evidence['validation_scans'])>=2
    if mode in {'fastqc','both','seqkit-stats'}:
        assert not evidence['derived_outputs']
    else:
        assert len(evidence['derived_outputs'])==2
        assert all(row['sha256'] for row in evidence['derived_outputs'])
        if '--count' in flags: assert all(row['records']==7 for row in evidence['derived_outputs'])


@pytest.mark.skipif(not SEQKIT, reason='Genuine SeqKit required')
def test_failed_benchmark_not_success(tmp_path,monkeypatch):
    monkeypatch.setenv('QUALIDOCK_SEQKIT',SEQKIT)
    args=benchmark.parser().parse_args(['--input',str(FIXTURE/'coverage_R1.fastq.gz'),'--output',str(tmp_path/'evidence'),'--mode','seqkit-sample','--count','99999'])
    with pytest.raises(SystemExit): benchmark.main(args)
    evidence=json.loads((tmp_path/'evidence/benchmark.json').read_text())
    assert evidence['run']['state']=='failed' and not evidence['derived_outputs']


@pytest.mark.skipif(not FASTQC, reason='Genuine FastQC required')
def test_real_benchmark_cancellation(tmp_path,monkeypatch):
    monkeypatch.setenv('QUALIDOCK_FASTQC',FASTQC)
    args=benchmark.parser().parse_args(['--input',str(FIXTURE/'coverage_R1.fastq.gz'),'--output',str(tmp_path/'evidence'),'--mode','fastqc','--cancel-after','0'])
    benchmark.main(args)
    evidence=json.loads((tmp_path/'evidence/benchmark.json').read_text())
    assert evidence['cancellation_requested'] and evidence['run']['state']=='cancelled'
    assert not evidence['derived_outputs'] and evidence['input_integrity_unchanged']


@pytest.mark.skipif(not SEQKIT, reason='Genuine SeqKit required')
def test_partial_benchmark_only_counts_verified_outputs(tmp_path,monkeypatch):
    monkeypatch.setenv('QUALIDOCK_SEQKIT',SEQKIT)
    broken=tmp_path/'broken.fastq';broken.write_text('@broken\nACGT\n+\nI\n')
    args=benchmark.parser().parse_args(['--input',str(FIXTURE/'coverage_R1.fastq.gz'),str(broken),'--output',str(tmp_path/'evidence'),'--mode','seqkit-filter'])
    with pytest.raises(SystemExit): benchmark.main(args)
    evidence=json.loads((tmp_path/'evidence/benchmark.json').read_text())
    assert evidence['run']['state']=='partial' and len(evidence['derived_outputs'])==1
    assert evidence['derived_outputs'][0]['records']==400
    assert any(row['state']=='failed' for row in evidence['validation_scans'])
    assert evidence['input_integrity_unchanged']


def test_benchmark_rejects_misplaced_parameters(tmp_path):
    args=benchmark.parser().parse_args(['--input','/not/read','--output',str(tmp_path/'evidence'),'--mode','fastqc','--count','5'])
    with pytest.raises(ValueError,match='count'): benchmark.processing_options(args)
    assert not args.output.exists()


def test_latency_retention_is_bounded_without_losing_aggregates():
    import time
    evidence={'api_requests':[]}
    for index in range(2100): benchmark.latency(evidence,'run',time.monotonic(),500 if index==0 else 200)
    assert len(evidence['api_requests'])==2000
    assert evidence['api_summary']['run']['count']==2100 and evidence['api_summary']['run']['errors']==1
