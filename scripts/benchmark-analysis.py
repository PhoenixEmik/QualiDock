#!/usr/bin/env python3
"""Private benchmark of authorized FASTQ paths using the existing application API."""
import argparse
import hashlib
import json
import os
import resource
import subprocess
from pathlib import Path
import sys
import time

from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings, available_cpus, available_memory_mb
from qualidock import datasets, processing


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
            counters={'cpu_ticks':int(fields[11])+int(fields[12])}
            try:
                for line in (path.parent/'io').read_text().splitlines():
                    key,value=line.split(':',1)
                    if key in {'read_bytes','write_bytes','rchar','wchar'}: counters[key]=int(value)
            except OSError: pass
            # Start ticks distinguish reused PIDs. These are observed lower bounds.
            result[path.parent.name+':'+fields[19]]=counters
        except (OSError,ValueError,IndexError): continue
    return result


def filesystem(path):
    if sys.platform != 'linux': return {'type': None, 'reason': 'Linux stat -f unavailable'}
    result=subprocess.run(['stat','-f','-c','%T',str(path)],capture_output=True,text=True,timeout=5)
    return {'type': result.stdout.strip() if result.returncode == 0 else None}


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('--input',type=Path,nargs='+',required=True)
    result.add_argument('--output',type=Path,required=True,help='New private directory; must not already exist')
    result.add_argument('--mode',choices=['fastqc','both',*sorted(processing.MODES)],default='both')
    result.add_argument('--threads',type=int,default=1)
    result.add_argument('--memory-mb',type=int)
    result.add_argument('--cancel-after',type=float)
    result.add_argument('--timeout',type=float,default=86400)
    result.add_argument('--hash-inputs',action='store_true',help='Two extra complete source reads, separately timed')
    result.add_argument('--fraction',type=float,default=0.1)
    result.add_argument('--count',type=int)
    result.add_argument('--seed',type=int,default=11)
    result.add_argument('--min-length',type=int,default=15)
    result.add_argument('--max-length',type=int)
    result.add_argument('--identifiers',type=Path,help='Private UTF-8 exact-ID list, at most 1 MiB')
    result.add_argument('--preserve-pairs',action='store_true',help='Keep both mates in length/ID selection; sampling already preserves confirmed pairs')
    result.add_argument('--plain-output',action='store_true')
    result.add_argument('--compare-qc',action='store_true',help='fastp only: include raw and processed FastQC')
    result.add_argument('--multiqc',action='store_true',help='fastp only: aggregate fastp and optional FastQC')
    return result


def processing_options(args):
    if args.count is not None and args.mode!='seqkit-sample': raise ValueError('--count requires seqkit-sample')
    if args.identifiers and args.mode!='seqkit-extract': raise ValueError('--identifiers requires seqkit-extract')
    if args.preserve_pairs and args.mode not in {'seqkit-filter','seqkit-extract'}: raise ValueError('--preserve-pairs requires length or ID selection')
    if (args.compare_qc or args.multiqc) and args.mode!='fastp': raise ValueError('--compare-qc and --multiqc require fastp')
    if args.mode not in processing.MODES: return None
    value={'gzip':not args.plain_output}
    if args.mode=='fastp':
        value.update(min_length=args.min_length,compare_qc=args.compare_qc,multiqc=args.multiqc)
    else:
        value.update(fraction=args.fraction,count=args.count,seed=args.seed,min_length=args.min_length,
                     max_length=args.max_length,preserve_pairs=args.preserve_pairs)
        if args.identifiers:
            with args.identifiers.open('rb') as stream: content=stream.read(1024*1024+1)
            if len(content)>1024*1024: raise ValueError('Identifier list exceeds 1 MiB')
            value['identifiers']=content.decode('utf-8').splitlines()
    return processing.options(args.mode,value)


def main(args):
    if os.geteuid()==0:
        raise SystemExit('Run under an ordinary Unix account inside the intended allocation.')
    args.output=args.output.expanduser().absolute()
    if args.timeout<=0 or args.cancel_after is not None and args.cancel_after<0:
        raise SystemExit('Timeout must be positive and cancel-after must be nonnegative.')
    files=[path.expanduser().resolve(strict=True) for path in args.input]
    capacity, memory=available_cpus(), available_memory_mb()
    budget=args.memory_mb if args.memory_mb is not None else memory
    if not 1<=args.threads<=capacity or not 1024<=budget<=memory:
        raise SystemExit(f'Request is outside detected allocation: {capacity} CPUs, {memory} MiB. Set allocation variables correctly before launch.')
    os.umask(0o077)
    options=processing_options(args)
    args.output.mkdir(parents=True,mode=0o700)  # Refuse to overwrite any previous evidence/results.
    fingerprint_started=time.monotonic()
    before=[fingerprint(path,args.hash_inputs) for path in files]
    settings=Settings(roots=list(dict.fromkeys(path.parent for path in files)),output=args.output/'results',frontend=args.output/'frontend',cpus=capacity,memory_mb=budget,fastqc=os.environ.get('QUALIDOCK_FASTQC','fastqc'),multiqc=os.environ.get('QUALIDOCK_MULTIQC','multiqc'),fastp=os.environ.get('QUALIDOCK_FASTP','fastp'),seqkit=os.environ.get('QUALIDOCK_SEQKIT','seqkit'))
    evidence={'scope':'actual tools; in-process HTTP latency, not browser/SSE/network acceptance','platform':sys.platform,
              'filesystems':[filesystem(path) for path in files], 'output_filesystem':filesystem(args.output), 'inputs':before,'input_bytes':sum(row['size'] for row in before),
              'input_integrity_evidence':'sha256_before_after' if args.hash_inputs else 'metadata_only_not_content_proof',
              'fingerprint_before_seconds':time.monotonic()-fingerprint_started,'hash_only_source_passes':2 if args.hash_inputs else 0,
              'mode':args.mode,'processing_options':options,'threads':args.threads,'memory_mb':budget,'api_requests':[],'stages':[],'process_counters':{},'cancellation_requested':False,
              'measurement_limits':'CPU samples miss short processes; RSS is sampled, not exact peak. Per-process I/O includes waited children, so counters are not summed into a workload total or NFS/Lustre throughput. Non-Linux kernel I/O is unavailable.'}
    started=time.monotonic()
    child_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        with TestClient(create_app(settings),raise_server_exceptions=False) as client:
            client.headers.update({'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'})
            response=client.post('/api/runs',json={'name':'Authorized filesystem benchmark','mode':args.mode,'paths':list(map(str,files)),'threads':args.threads,'processing_options':options})
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
            run=evidence['run']
            evidence['terminal_state']=run['state']
            output_audit_started=time.monotonic()
            references=[{'run_id':run_id,'dataset_id':row['id']} for row in run.get('derived_datasets',[])]
            published=datasets.registered(client.app.state.manager,references)
            evidence['derived_outputs']=[]
            for path, row in published.items():
                measured=fingerprint(Path(path),True)
                if measured['sha256']!=row['sha256']: raise AssertionError('Published output checksum differs from full validation')
                evidence['derived_outputs'].append({'dataset_id':row['id'],'path':row['path'],'records':row['records'],'bases':row['bases'],**measured})
            evidence['derived_bytes']=sum(row['size'] for row in evidence['derived_outputs'])
            actual={str(path) for path in settings.output.rglob('*') if path.is_file() and path.name.endswith(('.fastq','.fq','.fastq.gz','.fq.gz'))}
            evidence['unpublished_fastqs']=sorted(actual-set(published))
            if run['state']=='completed' and evidence['unpublished_fastqs']: raise AssertionError('Completed run contains unregistered FASTQs')
            evidence['output_hash_only_bytes']=evidence['derived_bytes']
            evidence['output_audit_seconds']=time.monotonic()-output_audit_started
            validation=run.get('processing',{}).get('input_validation',{})
            checks=[('source',validation), *[(unit['id'],unit.get('output_validation',{})) for unit in run.get('processing',{}).get('units',[])]]
            evidence['validation_scans']=[{'stage':stage,'path':row['path'],'bytes_read':row['compressed_bytes_read'],'coverage':row['coverage'],'state':row['state'],'sha256':row['sha256']} for stage,check in checks for row in check.get('files',[])]
            evidence['execution_stages']=[{'tool':row['tool'],'started_at':row['started_at'],'finished_at':row['finished_at'],'exit_code':row['exit_code'],'resources':row.get('resources')} for row in run.get('executions',[])]
            if sys.platform!='linux':
                for stage in evidence['execution_stages']:
                    if stage['resources']:
                        stage['resources']={**stage['resources'],'peak_sampled_rss_bytes':None,'rss_scope':'Portable benchmark does not assert Linux process-tree RSS'}
            evidence['analysis_wall_seconds']=time.monotonic()-started
            for index, stage in enumerate(evidence['stages']):
                end=evidence['stages'][index+1]['elapsed_seconds'] if index+1<len(evidence['stages']) else evidence['analysis_wall_seconds']
                stage['observed_wall_seconds']=end-stage['elapsed_seconds']
        fingerprint_started=time.monotonic()
        evidence['input_integrity_unchanged']=before==[fingerprint(path,args.hash_inputs) for path in files]
        evidence['fingerprint_after_seconds']=time.monotonic()-fingerprint_started
        assert evidence['input_integrity_unchanged'], 'Input metadata/hash changed during benchmark'
        evidence['status']='measured'
    except Exception as exc:
        evidence['status']='failed'; evidence['error']=repr(exc)
        raise
    finally:
        evidence['wall_seconds']=time.monotonic()-started
        observed=list(evidence['process_counters'].values())
        evidence['sampled_cpu_seconds']=sum(value['cpu_ticks'] for value in observed)/os.sysconf('SC_CLK_TCK') if observed else None
        evidence['sampled_cpu_percent_one_core']=100*evidence['sampled_cpu_seconds']/evidence['wall_seconds'] if observed else None
        for key in ('read_bytes','write_bytes','rchar','wchar'):
            # /proc/PID/io includes waited-for children: summing sampled parents
            # and children can double count. Preserve observations, not a false total.
            evidence['sampled_'+key]=None
        child_after=resource.getrusage(resource.RUSAGE_CHILDREN)
        evidence['waited_child_cpu_seconds']=child_after.ru_utime+child_after.ru_stime-child_before.ru_utime-child_before.ru_stime
        evidence['child_cpu_scope']='Waited children of this benchmark, including tool probes and guardians; not parent API CPU or per-stage utilization'
        evidence['child_high_water_rss_bytes']=child_after.ru_maxrss*(1 if sys.platform=='darwin' else 1024)
        evidence['child_rss_scope']='Cumulative RUSAGE_CHILDREN high-water mark, not aggregate process-tree peak'
        (args.output/'benchmark.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n')
    print(f"Benchmark saved: {args.output/'benchmark.json'}; state={evidence['run']['state']}")
    if evidence['run']['state'] not in {'completed','cancelled'}: raise SystemExit(1)


if __name__=='__main__': main(parser().parse_args())
