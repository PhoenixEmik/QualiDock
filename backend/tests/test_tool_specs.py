"""Probe contracts only; processing correctness is tested with actual tools."""
import asyncio
import sys
import pytest
from qualidock.tools import detect_tool


@pytest.mark.parametrize('name,version,argument', [('fastp','1.4.0','--version'),('fastp','0.23.4','--version'),('seqkit','2.12.0','version')])
def test_explicit_probe(tmp_path,name,version,argument):
    executable=tmp_path/name
    executable.write_text(f'#!{sys.executable}\nimport sys\nassert sys.argv[1:]==[{argument!r}]\nprint({name + " v" + version!r})\n')
    executable.chmod(0o700)
    info=asyncio.run(detect_tool(name,str(executable)))
    assert info['compatible'] and info['version']==version


def test_missing_and_incompatible(tmp_path):
    assert not asyncio.run(detect_tool('seqkit',str(tmp_path/'absent')))['available']
    executable=tmp_path/'fastp'
    executable.write_text(f'#!{sys.executable}\nprint("fastp 0.20.0")\n');executable.chmod(0o700)
    assert not asyncio.run(detect_tool('fastp',str(executable)))['compatible']
