#!/usr/bin/env python3
"""Capture genuine upstream variant reports, versions, argv and source hashes."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

from qualidock.tools import detect_tool
from qualidock.variant import readable


def qualify(executable, output):
    output.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('variants',Path(__file__).with_name('prepare-variant-test.py'))
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    tool=asyncio.run(detect_tool('bcftools',executable));assert tool['compatible'],tool
    exe=tool['executable']
    paths=fixture.prepare(output/'inputs',exe)
    before={key:hashlib.sha256(p.read_bytes()).hexdigest() for key,p in paths.items()}
    commands=[];summaries={};semantics={}
    version=subprocess.run([exe,'--version'],check=True,capture_output=True)
    (output/'version.stdout.txt').write_bytes(version.stdout)
    for name,path in paths.items():
        info=readable(path);semantics[name]={k:info[k] for k in ['format','compression','samples','tags']}
        for samples in [False,True]:
            argv=[exe,'stats',*(['-s','-'] if samples else []),str(path.resolve())]
            result=subprocess.run(argv,capture_output=True,timeout=30)
            label=name+('-samples' if samples else '')
            (output/(label+'.stats.txt')).write_bytes(result.stdout)
            (output/(label+'.stderr.txt')).write_bytes(result.stderr)
            expected=255 if samples and not info['samples'] else 0
            assert result.returncode==expected,(argv,result.stderr)
            commands.append({'case':name,'per_sample':samples,'argv':argv,'exit_code':result.returncode,'report':label+'.stats.txt','sha256':hashlib.sha256(result.stdout).hexdigest()})
            if not samples:
                summaries[name]=[line for line in result.stdout.decode().splitlines() if line and not line.startswith('#') and not line.startswith('ID\t')]
    assert all(summaries[name]==summaries['mixed'] for name in ['gzip','bgzf','bcf','uncompressed-bcf','raw-bcf'])
    assert summaries['snps']==summaries['vcf42']
    assert summaries['multisample']==summaries['multisample-bcf']==summaries['multisample-bgzf']
    assert before=={key:hashlib.sha256(p.read_bytes()).hexdigest() for key,p in paths.items()}
    assert not any(p.suffix in {'.tbi','.csi'} for p in (output/'inputs').iterdir())
    data={'tool':tool,'commands':commands,'inputs':semantics,'input_sha256':before,'source_unchanged':True,'equivalent_statistics_verified':True,'indexes_required':False,'scope':'Explicit synthetic records/alleles, not real population accuracy or representative performance','status':'passed'}
    (output/'provenance.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'status':'passed','cases':len(paths),'executions':len(commands),'tool':tool}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bcftools',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();qualify(args.bcftools,args.output)
