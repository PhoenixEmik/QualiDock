#!/usr/bin/env python3
"""Independent genuine-tool comparison; originals are never rewritten."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

from qualidock.tools import detect_tool


def qualify(executable, output):
    root=Path(__file__).resolve().parents[1]
    output.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('fixture',root/'scripts/prepare-alignment-test.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    tool=asyncio.run(detect_tool('samtools',executable))
    assert tool['compatible'] and tool['version']==tool['htslib_version']=='1.24',tool
    bam,cram,reference=fixture.prepare(output/'inputs',tool['executable'])
    original={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in bam.parent.iterdir()}
    evidence={'tool':tool,'commands':[], 'comparisons':{}}
    for kind,source in [('bam',bam),('cram',cram)]:
        for operation in ['head','quickcheck','flagstat','stats']:
            args=['head','-n','0'] if operation=='head' else [operation]
            if kind=='cram' and operation in {'stats','flagstat'}:args+=['--input-fmt-option','reference='+str(reference)]
            argv=[tool['executable'],*args,str(source)]
            result=subprocess.run(argv,capture_output=True,timeout=30,env={**os.environ,'REF_PATH':'/dev/null','REF_CACHE':'/dev/null','HTS_PATH':''})
            (output/f'{kind}.{operation}.stdout.txt').write_bytes(result.stdout)
            (output/f'{kind}.{operation}.stderr.txt').write_bytes(result.stderr)
            evidence['commands'].append({'argv':argv,'exit_code':result.returncode})
            assert result.returncode==0,(argv,result.stderr)
            if operation=='flagstat':
                baseline=(root/'backend/tests/fixtures/samtools-1.22.1/flagstat.txt').read_bytes()
                assert result.stdout==baseline,'Upstream flagstat change needs independent scientific review'
                evidence['comparisons'][kind+'.flagstat']='byte-identical to genuine 1.22.1 baseline'
            if operation=='stats':
                def summary(text):return {v.split('\t')[1]:v.split('\t')[2:] for v in text.splitlines() if v.startswith('SN\t')}
                baseline=summary((root/'backend/tests/fixtures/samtools-1.22.1/stats.txt').read_text())
                current=summary(result.stdout.decode())
                assert current==baseline,'Upstream SN change needs independent scientific review'
                assert len(current)==39 and current['raw total sequences:'][0]=='6' and current['reads mapped:'][0]=='5' and current['total length:'][0]=='40'
                evidence['comparisons'][kind+'.stats']='all 39 original summary values and notes unchanged; original version/argv comments retained'
    assert original=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in bam.parent.iterdir()}
    evidence.update(source_sha256=original,source_unchanged=True,status='passed',scope='Explicit small synthetic geometry; not population accuracy or large-file performance')
    (output/'qualification.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samtools',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    qualify(args.samtools,args.output)
