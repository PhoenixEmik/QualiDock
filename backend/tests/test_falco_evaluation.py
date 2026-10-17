"""Conditional-engine gate: genuine tools, including known invalid-input behavior."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from qualidock.executor import LocalExecutor
from qualidock.integrity import scan_file, snapshot

spec=importlib.util.spec_from_file_location('benchmark_falco',Path(__file__).resolve().parents[2]/'scripts/benchmark-analysis.py')
benchmark=importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)
FALCO=shutil.which(os.environ.get('QUALIDOCK_FALCO','falco'))
FASTQC=shutil.which(os.environ.get('QUALIDOCK_FASTQC','fastqc'))
if os.environ.get('QUALIDOCK_REQUIRE_FALCO_EVALUATION')=='1' and not (FALCO and FASTQC):
    raise RuntimeError('Actual Falco and FastQC required for engine evaluation')
FIXTURE=Path(__file__).parent/'fixtures/fastqc-0.13.0'


@pytest.mark.skipif(not (FALCO and FASTQC),reason='Actual evaluation tools required')
@pytest.mark.parametrize('million',[False,True])
def test_actual_engine_evaluation(tmp_path,monkeypatch,million):
    source=Path(os.environ.get('QUALIDOCK_FALCO_BENCH_INPUT','/tmp/qualidock-million-reads.fastq.gz')) if million else FIXTURE/'coverage_R1.fastq.gz'
    if million and not source.exists():
        if os.environ.get('QUALIDOCK_REQUIRE_FALCO_EVALUATION')=='1': pytest.fail('Pinned million-read fixture missing')
        pytest.skip('CI provides the pinned million-read input; not a large-file acceptance skip')
    monkeypatch.setenv('QUALIDOCK_FASTQC',FASTQC)
    output=tmp_path/'evaluation'
    args=benchmark.parser().parse_args(['--input',str(source),'--output',str(output),'--mode','fastqc','--evaluate-falco',FALCO,'--repeats','3' if million else '1','--hash-inputs'])
    benchmark.main(args)
    evidence=json.loads((output/'falco-evaluation.json').read_text())
    assert evidence['status']=='measured' and evidence['source_unchanged']
    assert {r['engine'] for r in evidence['measurements']}=={'validation','fastqc','falco'}
    for row in evidence['measurements']:
        assert row['exit_code']==0 and row['waited_high_water_rss_bytes']>0 and row['wall_seconds']>0
        assert int(row['basic_statistics']['Total Sequences'])==(1000000 if million else 400)
        assert row['cpu_user_seconds']+row['cpu_system_seconds']>0
        assert row['block_input_operations']>=0 and row['block_output_operations']>=0
        if row['engine']=='validation':
            assert row['validation_scan']['coverage']=='full'
            assert row['validation_scan']['compressed_bytes_read']==source.stat().st_size
            assert row['validation_scan']['sha256']==evidence['inputs'][0]['sha256']
    falco=next(r for r in evidence['measurements'] if r['engine']=='falco')
    assert falco['reported_header']=='##Falco 2.0.3'
    assert '--groups' in falco['argv']
    if million: assert any(r.get('validated_falco_serial_wall_seconds',0)>0 for r in evidence['measurements'])
    multiqc=shutil.which(os.environ.get('QUALIDOCK_MULTIQC','multiqc'))
    if not million and multiqc:
        report=next(output.glob('input-*/0-falco/*/fastqc_data.txt'))
        files=output/'multiqc-inputs.txt';files.write_text(str(report.resolve())+'\n')
        subprocess.run([multiqc,'--file-list',str(files),'--outdir',str(output/'multiqc'),
                        '--data-format','json','--no-version-check'],check=True,capture_output=True)
        data=json.loads((output/'multiqc/multiqc_data/multiqc_data.json').read_text())
        sources=data['report_data_sources']['FastQC']['all_sections']
        assert list(sources.values())==[str(report.resolve())]
        (output/'multiqc-version.txt').write_text(subprocess.check_output([multiqc,'--version'],text=True))
    retained=Path('validation/falco-evaluation')/('million' if million else 'small')
    shutil.copytree(output,retained,dirs_exist_ok=True)


@pytest.mark.skipif(not (FALCO and FASTQC),reason='Actual evaluation tools required')
def test_actual_invalid_separator_requires_independent_validation(tmp_path):
    source=tmp_path/'missing_plus.fastq';source.write_bytes(b'@invalid\nACGT\n?\nIIII\n')
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    async def evaluate():
        executor=LocalExecutor(1024)
        for name,argv in [('falco',[FALCO,'--groups','--threads','1','--output',str(tmp_path/'falco'),str(source)]),
                          ('fastqc',[FASTQC,'--threads','1','--memory','512','--outdir',str(tmp_path/'fastqc'),'--format','fastq',str(source)])]:
            (tmp_path/name).mkdir()
            code=await executor.execute(name,argv,tmp_path,tmp_path/(name+'.log'),1)
            if name=='falco': assert code==0  # Genuine 2.0.3 accepts this malformed input.
    asyncio.run(evaluate())
    assert list((tmp_path/'falco').rglob('fastqc_data.txt'))
    assert not list((tmp_path/'fastqc').glob('*_fastqc.zip'))
    validated=scan_file({'id':'invalid','path':str(source),'snapshot':snapshot(source.stat())})
    assert validated['state']=='failed' and 'IUPAC' in validated['error']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    retained=Path('validation/falco-evaluation/invalid');retained.mkdir(parents=True,exist_ok=True)
    (retained/'evidence.json').write_text(json.dumps({'input':'explicitly malformed synthetic 4-line record with ? instead of +',
        'input_sha256':original,'falco_version':'2.0.3','falco_exit_code':0,'falco_generated_report':True,
        'fastqc_generated_report':False,'independent_validation':validated['state'],'validator_error':validated['error']},indent=2)+'\n')


def test_no_falco_application_mode_or_default_probe(client,setup):
    _,root=setup
    assert 'falco' not in client.get('/api/config').json()['tools']
    assert client.post('/api/runs',json={'mode':'falco','paths':[str(next(root.glob('*.fastq')))]}).status_code==422


@pytest.mark.parametrize('mode,repeats',[('both',3),('fastp',3),('fastqc',0),('fastqc',6)])
def test_invalid_evaluation_does_not_execute(tmp_path,mode,repeats):
    output=tmp_path/'untouched'
    args=benchmark.parser().parse_args(['--input',str(FIXTURE/'coverage_R1.fastq.gz'),'--output',str(output),
                                      '--mode',mode,'--evaluate-falco','/not-used/falco','--repeats',str(repeats)])
    with pytest.raises(ValueError,match='requires --mode fastqc'):
        asyncio.run(benchmark.evaluate_falco(args,[FIXTURE/'coverage_R1.fastq.gz'],2048))
    assert not output.exists()
