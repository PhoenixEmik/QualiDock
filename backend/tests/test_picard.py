"""Runtime/configuration units; scientific fidelity uses genuine Picard tests."""
import asyncio
from pathlib import Path
import sys

import pytest
from qualidock.tools import detect_tool, locate_tool
from qualidock import picard

FIXTURE=Path(__file__).parent/'fixtures/picard-3.5.0'


@pytest.mark.parametrize('version,exit_code,compatible',[('3.5.0',1,True),('3.5.0',0,False),('3.5.0',2,False),('3.5.0rc1',1,False),('3.4.0',1,False)])
def test_exact_picard_probe_contract_is_not_an_analysis_exit_exception(tmp_path,version,exit_code,compatible):
    jar=tmp_path/'picard.jar';jar.write_bytes(b'probe unit only; not scientific tool output');jar.chmod(0o600)
    runtime=tmp_path/'java'
    runtime.write_text(f'#!{sys.executable}\nimport sys\nassert "-Xmx128m" in sys.argv and "-XX:-UsePerfData" in sys.argv\nprint({("Version:"+version)!r})\nraise SystemExit({exit_code})\n');runtime.chmod(0o700)
    result=asyncio.run(detect_tool('picard',str(jar),java=str(runtime)))
    assert result['compatible'] is compatible
    assert locate_tool('picard',str(jar))==str(jar)
    if compatible:assert result['version_probe_exit_code']==1 and result['version']=='3.5.0'


@pytest.mark.parametrize('fault',['missing-java','symlink','shared-writable','launcher'])
def test_jar_and_runtime_authorization(tmp_path,fault):
    jar=tmp_path/'picard.jar';jar.write_bytes(b'unit placeholder');jar.chmod(0o600)
    if fault=='symlink':
        other=tmp_path/'target.jar';jar.rename(other);jar.symlink_to(other)
    if fault=='shared-writable':jar.chmod(0o666)
    if fault=='launcher':jar=jar.rename(tmp_path/'launcher')
    result=asyncio.run(detect_tool('picard',str(jar),java='/missing/java' if fault=='missing-java' else 'java'))
    assert not result['compatible'] and result['error']


@pytest.mark.parametrize('version,compatible',[('17.0.20.1',True),('16.0.2',False),('21.0.1',False),('17.0.20.1rc1',False)])
def test_qualified_java17_runtime(tmp_path,version,compatible):
    runtime=tmp_path/'java'
    runtime.write_text(f'#!{sys.executable}\nprint({("openjdk "+version+" 2026-08-18")!r})\n');runtime.chmod(0o700)
    assert asyncio.run(detect_tool('java',str(runtime)))['compatible'] is compatible


def test_genuine_metrics_histogram_precision_and_missing_standard_deviation():
    data=picard.parse(FIXTURE/'paired.insert_size_metrics.txt')
    rows=data['metrics']['rows']
    assert [r[8] for r in rows]==['FR','RF','TANDEM']
    assert rows[0][:9]==['250','150','100','150','350','250','100','3','FR']
    assert rows[1][6]=='70.710678' and rows[2][6]=='?'
    assert rows[2][7]=='1' and rows[2][-3:]==['','','']
    assert data['histogram']['rows']==[['150','1','0','0'],['200','0','1','0'],['250','1','0','0'],['300','0','1','0'],['350','1','0','0'],['400','0','0','1']]
    picard.pdf(FIXTURE/'paired.histogram.pdf')


@pytest.mark.parametrize('fault',['class','columns','duplicate-population','nonfinite','negative','fractional-count','reordered','missing-histogram','duplicate-column','incomplete'])
def test_incomplete_or_malformed_reports_are_not_native_metrics(tmp_path,fault):
    text=(FIXTURE/'paired.insert_size_metrics.txt').read_text()
    if fault=='class':text=text.replace('picard.analysis.InsertSizeMetrics','different.Class')
    elif fault=='columns':text=text.replace('MEAN_INSERT_SIZE','Q30')
    elif fault=='duplicate-population':text=text.replace('\n## HISTOGRAM','\n'+next(l for l in text.splitlines() if '\tFR\t' in l)+'\n\n## HISTOGRAM')
    elif fault=='nonfinite':text=text.replace('70.710678','NaN')
    elif fault=='negative':text=text.replace('70.710678','-1')
    elif fault=='fractional-count':text=text.replace('150\t1\t0\t0','150\t0.5\t0\t0')
    elif fault=='reordered':text=text.replace('200\t0\t1\t0','149\t0\t1\t0')
    elif fault=='missing-histogram':text=text.split('## HISTOGRAM')[0]
    elif fault=='duplicate-column':text=text.replace('All_Reads.rf_count','All_Reads.fr_count')
    else:text='## METRICS CLASS\tpicard.analysis.InsertSizeMetrics\n'
    path=tmp_path/'metrics.txt';path.write_text(text)
    with pytest.raises(ValueError):picard.parse(path)


@pytest.mark.parametrize('options',[{'by_library':'yes'},{'include_duplicates':1},{'histogram_pdf':'true'},{'extra_args':'-Xmx999g'},{'reference':'http://remote'}])
def test_only_explicit_validated_parameters(options):
    with pytest.raises(ValueError):picard.Options.model_validate(options)


def test_pdf_must_be_complete_and_library_names_unambiguous(tmp_path):
    path=tmp_path/'fake.pdf';path.write_bytes(b'<html>not a plot</html>')
    with pytest.raises(ValueError):picard.pdf(path)
    path.write_bytes(b'%PDF-1.7\nincomplete')
    with pytest.raises(ValueError):picard.pdf(path)
    header=tmp_path/'header.txt';header.write_text('@RG\tID:one\tSM:A\tLB:shared\n@RG\tID:two\tSM:B\tLB:shared\n')
    with pytest.raises(ValueError):picard.libraries(header)
    header.write_text('@RG\tID:one\tSM:A\tLB:library\n')
    picard.libraries(header)


def test_long_failed_stderr_keeps_the_actual_error_tail(tmp_path):
    from qualidock.executor import LocalExecutor
    executor=LocalExecutor(1024);log=tmp_path/'analysis.log';stderr=tmp_path/'tool.log'
    code=asyncio.run(executor.execute('diagnostic',[sys.executable,'-c','import sys;sys.stderr.write("x"*70000+"actual failure at the end\\n");sys.exit(2)'],tmp_path,log,1,stderr=stderr))
    assert code==2 and len(stderr.read_bytes())>70000
    assert 'actual failure at the end' in log.read_text() and 'Last 64 KiB' in log.read_text()
    assert log.stat().st_size<66000


def test_report_counts_cannot_exceed_the_actual_source_population():
    with pytest.raises(ValueError,match='exceed source'):
        picard.parse(FIXTURE/'paired.insert_size_metrics.txt',maximum_pairs=2)
