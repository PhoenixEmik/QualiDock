"""Version-policy tests; scientific evidence comes from the genuine-tool tests."""
import asyncio
import json
from pathlib import Path
import sys

import pytest
from qualidock.tools import detect_tool, rseqc_dependencies


def executable(tmp_path, response):
    path = tmp_path/'native-reader'
    path.write_text(f'#!{sys.executable}\nprint({response!r})\n')
    path.chmod(0o700)
    return path


@pytest.mark.parametrize('library', ['1.22.1', '1.22.2', '1.23.1', '1.22.3', '1.23.2', '1.24rc1', '1.24.1', '1.25', 'unknown'])
def test_new_samtools_does_not_authorize_old_or_unqualified_library(tmp_path, library):
    result = asyncio.run(detect_tool('samtools', str(executable(tmp_path, 'samtools 1.24\nUsing htslib '+library))))
    assert result['available'] and not result['compatible'] and result['error']


@pytest.mark.parametrize('response', ['samtools 1.24', 'samtools 1.24\nUsing htslib 1.24\nUsing htslib 1.22.1', 'samtools 1.24\nUsing htslib 1.24\nUsing htslib 1.24'])
def test_missing_or_conflicting_samtools_library_evidence_is_rejected(tmp_path,response):
    assert not asyncio.run(detect_tool('samtools',str(executable(tmp_path,response))))['compatible']


@pytest.mark.parametrize('response,expected', [('mosdepth 0.3.14',False), ('mosdepth 0.3.14\nUsing htslib 1.22.1',False), ('mosdepth 0.3.14\nUsing htslib 1.24',True)])
def test_mosdepth_requires_its_own_library_version_not_samtools(tmp_path,response,expected):
    result=asyncio.run(detect_tool('mosdepth',str(executable(tmp_path,response))))
    assert result['compatible'] is expected
    if expected:assert result['htslib_version']=='1.24'


@pytest.mark.parametrize('pysam,library,status,expected', [('0.24.1','1.24',0,True),('0.24.0','1.23.1',0,False),('0.24.1','1.22.1',0,False),('0.24.1','1.23.2',0,False),('0.24.1','1.24rc1',0,False),('0.24.2','1.24',0,False),('0.24.1','1.24',1,False)])
def test_rseqc_checks_its_own_interpreter_and_exact_dependencies(tmp_path,monkeypatch,pysam,library,status,expected):
    path=executable(tmp_path,'unused')
    async def metadata(argv,env):
        assert Path(argv[0]).absolute()==Path(sys.executable).absolute()
        assert argv[1:3]==['-I','-c'] and 'pysam.__htslib_version__' in argv[3]
        return json.dumps({'rseqc':'5.0.5','pysam':pysam,'htslib':library}),status
    monkeypatch.setattr('qualidock.tools.version_response',metadata)
    if expected:
        result=asyncio.run(rseqc_dependencies(path,{}))
        assert result['htslib_version']=='1.24' and result['pysam_version']=='0.24.1'
    else:
        with pytest.raises(ValueError):asyncio.run(rseqc_dependencies(path,{}))


def test_dependency_failure_cannot_leave_tool_marked_compatible(tmp_path,monkeypatch):
    async def fail(path,env):raise ValueError('Unverified HTSlib')
    monkeypatch.setattr('qualidock.tools.rseqc_dependencies',fail)
    result=asyncio.run(detect_tool('rseqc_infer',str(executable(tmp_path,'infer_experiment.py 5.05'))))
    assert result['available'] and not result['compatible'] and result['error']=='Unverified HTSlib'


def test_rseqc_probe_does_not_qualify_a_different_python_environment(tmp_path,monkeypatch):
    from qualidock.tools import RSEQC_ENV
    for name in RSEQC_ENV:monkeypatch.setenv(name,'untrusted-inherited-setting')
    async def response(argv,env):
        assert all(env[key]==value for key,value in RSEQC_ENV.items())
        return 'infer_experiment.py 5.05',0
    async def dependencies(path,env):
        assert all(env[key]==value for key,value in RSEQC_ENV.items())
        return {'pysam_version':'0.24.1','htslib_version':'1.24'}
    monkeypatch.setattr('qualidock.tools.version_response',response)
    monkeypatch.setattr('qualidock.tools.rseqc_dependencies',dependencies)
    assert asyncio.run(detect_tool('rseqc_infer',str(executable(tmp_path,'unused'))))['compatible']
