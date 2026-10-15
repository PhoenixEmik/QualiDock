#!/usr/bin/env python3
"""Private benchmark of authorized FASTQ paths using the existing application API."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings, available_cpus, available_memory_mb


def fingerprint(path, full_hash):
    info=path.stat()
    result={'name':path.name,'size':info.st_size,'mtime_ns':info.st_mtime_ns,'inode':info.st_ino,'device':info.st_dev}
    if full_hash:
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(1024*1024): digest.update(chunk)
        result['sha256']=digest.hexdigest()
    return result


def usage(group):
    result={}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields=path.read_text().rsplit(')',1)[1].split()
            if int(fields[2])!=group: continue
            counters={}
            for line in (path.parent/'io').read_text().splitlines():
                key,value=line.split(':',1); counters[key]=int(value)
            result[path.parent.name]={'cpu_ticks':int(fields[11])+int(fields[12]),'read_bytes':counters.get('read_bytes',0),'write_bytes':counters.get('write_bytes',0)}
        except (OSError,ValueError,IndexError): continue
    return result


def main(args):
    if sys.platform!='linux' or os.geteuid()==0:
        raise SystemExit('Run under an ordinary Linux account inside the intended allocation.')
    args.output=args.output.expanduser().absolute()
    if args.timeout<=0 or args.cancel_after is not None and args.cancel_after<0:
        raise SystemExit('Timeout must be positive and cancel-after must be nonnegative.')
    files=[path.expanduser().resolve(strict=True) for path in args.input]
    capacity, memory=available_cpus(), available_memory_mb()
    budget=args.memory_mb if args.memory_mb is not None else memory
    if not 1<=args.threads<=capacity or not 1024<=budget<=memory:
        raise SystemExit(f'Request is outside detected allocation: {capacity} CPUs, {memory} MiB. Set allocation variables correctly before launch.')
    os.umask(0o077)
    args.output.mkdir(parents=True,mode=0o700)  # Refuse to overwrite any previous evidence/results.
    before=[fingerprint(path,args.hash_inputs) for path in files]
    settings=Settings(roots=list(dict.fromkeys(path.parent for path in files)),output=args.output/'results',frontend=args.output/'frontend',cpus=capacity,memory_mb=budget,fastqc=os.environ.get('QUALIDOCK_FASTQC','fastqc'),multiqc=os.environ.get('QUALIDOCK_MULTIQC','multiqc'))
    evidence={'scope':'actual external QC tools and in-process HTTP API latency; no network/SSE proxy acceptance claim','inputs':before,'mode':args.mode,'threads':args.threads,'memory_mb':budget,'api_requests':[],'stages':[],'process_counters':{},'cancellation_requested':False}
    started=time.monotonic()
    try:
        with TestClient(create_app(settings),raise_server_exceptions=False) as client:
            client.headers.update({'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'})
            response=client.post('/api/runs',json={'name':'Authorized filesystem benchmark','mode':args.mode,'paths':list(map(str,files)),'threads':args.threads})
            if response.status_code!=201: raise RuntimeError(f'Cannot start benchmark ({response.status_code}): {response.text}')
            run_id=response.json()['id']
            log_offset=0; snapshot=None
            while True:
                tick=time.monotonic()
                response=client.get(f'/api/runs/{run_id}')
                evidence['api_requests'].append({'endpoint':'run','seconds':time.monotonic()-tick,'status':response.status_code})
                response.raise_for_status(); run=response.json()
                if not evidence['stages'] or evidence['stages'][-1]['stage']!=run['stage']:
                    evidence['stages'].append({'stage':run['stage'],'elapsed_seconds':time.monotonic()-started})
                process=client.app.state.manager.executor.processes.get(run_id)
                if process:
                    for pid,counters in usage(process.pid).items():
                        previous=evidence['process_counters'].setdefault(pid,{key:0 for key in counters})
                        for key,value in counters.items(): previous[key]=max(previous[key],value)
                if run['state'] not in {'queued','running'}: break
                for name,endpoint,params in [('logs',f'/api/runs/{run_id}/logs',{'offset':log_offset}),('files','/api/files',{'path':str(files[0].parent),'limit':10,**({'snapshot':snapshot} if snapshot else {})})]:
                    tick=time.monotonic(); response=client.get(endpoint,params=params)
                    evidence['api_requests'].append({'endpoint':name,'seconds':time.monotonic()-tick,'status':response.status_code})
                    if response.status_code==200:
                        value=response.json()
                        if name=='logs': log_offset=value['offset']
                        else: snapshot=value.get('snapshot')
                    elif name=='files' and response.status_code==409: snapshot=None
                elapsed=time.monotonic()-started
                if args.cancel_after is not None and elapsed>=args.cancel_after and not evidence['cancellation_requested']:
                    client.post(f'/api/runs/{run_id}/cancel').raise_for_status(); evidence['cancellation_requested']=True
                if elapsed>args.timeout:
                    client.post(f'/api/runs/{run_id}/cancel').raise_for_status()
                    raise TimeoutError('Benchmark timeout reached; cancellation requested')
                time.sleep(0.5)
            # Allow the cancellation task to persist its final exit record and artifact registry.
            deadline=time.monotonic()+15
            while run_id in client.app.state.manager.tasks and time.monotonic()<deadline: time.sleep(0.05)
            evidence['run']=client.get(f'/api/runs/{run_id}').json()
            evidence['metrics']=client.get(f'/api/runs/{run_id}/metrics').json()
        evidence['input_integrity_unchanged']=before==[fingerprint(path,args.hash_inputs) for path in files]
        assert evidence['input_integrity_unchanged'], 'Input metadata/hash changed during benchmark'
        assert not any(path.name.endswith(('.fastq','.fq','.fastq.gz','.fq.gz')) for path in settings.output.rglob('*') if path.is_file()), 'Source FASTQ was copied into results'
        evidence['status']='measured'
    except Exception as exc:
        evidence['status']='failed'; evidence['error']=repr(exc)
        raise
    finally:
        evidence['wall_seconds']=time.monotonic()-started
        evidence['sampled_cpu_seconds']=sum(value['cpu_ticks'] for value in evidence['process_counters'].values())/os.sysconf('SC_CLK_TCK')
        evidence['sampled_read_bytes']=sum(value['read_bytes'] for value in evidence['process_counters'].values())
        evidence['sampled_write_bytes']=sum(value['write_bytes'] for value in evidence['process_counters'].values())
        (args.output/'benchmark.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n')
    print(f"Benchmark saved: {args.output/'benchmark.json'}; state={evidence['run']['state']}")
    if evidence['run']['state'] not in {'completed','cancelled'}: raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True,help='New private directory; must not already exist')
    parser.add_argument('--mode',choices=['fastqc','both'],default='both')
    parser.add_argument('--threads',type=int,default=1)
    parser.add_argument('--memory-mb',type=int)
    parser.add_argument('--cancel-after',type=float)
    parser.add_argument('--timeout',type=float,default=86400)
    parser.add_argument('--hash-inputs',action='store_true',help='Stream full input hashes before and after; adds two complete input reads')
    main(parser.parse_args())
