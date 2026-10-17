#!/usr/bin/env python3
"""Private benchmark of authorized FASTQ paths using the existing application API."""
import argparse
import asyncio
import hashlib
import json
import math
import os
import resource
import re
import subprocess
from pathlib import Path
import sys
import time
import zipfile

from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings, available_cpus, available_memory_mb
from qualidock import datasets, processing
from qualidock.executor import LocalExecutor
from qualidock.metrics import bounded_text, parse_summary
from qualidock.tools import detect_tool
from qualidock.integrity import snapshot


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


def latency(evidence, endpoint, started, status):
    seconds=time.monotonic()-started
    summary=evidence.setdefault('api_summary',{}).setdefault(endpoint,{'count':0,'total_seconds':0,'max_seconds':0,'errors':0})
    summary.update(count=summary['count']+1,total_seconds=summary['total_seconds']+seconds,
                   max_seconds=max(summary['max_seconds'],seconds),errors=summary['errors']+int(status>=400))
    evidence['api_requests'].append({'endpoint':endpoint,'seconds':seconds,'status':status})
    # Long private benchmarks retain bounded recent detail and complete aggregates.
    if len(evidence['api_requests'])>2000: evidence['api_requests'].pop(0)


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('--input',type=Path,nargs='+',required=True)
    result.add_argument('--output',type=Path,required=True,help='New private directory; must not already exist')
    result.add_argument('--mode',choices=['fastqc','both','nanoplot',*sorted(processing.MODES)],default='both')
    result.add_argument('--nanoplot-loglength',action='store_true')
    result.add_argument('--nanoplot-individual-plots',action='store_true')
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
    result.add_argument('--evaluate-falco', metavar='EXECUTABLE', help='Benchmark actual Falco against FastQC before enabling another engine; requires --mode fastqc')
    result.add_argument('--repeats', type=int, default=3, help='Alternating engine evaluation repetitions, 1–5')
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
    if not math.isfinite(args.timeout) or args.timeout<=0 or args.cancel_after is not None and (not math.isfinite(args.cancel_after) or args.cancel_after<0):
        raise SystemExit('Timeout must be positive and cancel-after must be nonnegative.')
    files=[path.expanduser().resolve(strict=True) for path in args.input]
    capacity, memory=available_cpus(), available_memory_mb()
    budget=args.memory_mb if args.memory_mb is not None else memory
    if not 1<=args.threads<=capacity or not 1024<=budget<=memory:
        raise SystemExit(f'Request is outside detected allocation: {capacity} CPUs, {memory} MiB. Set allocation variables correctly before launch.')
    if args.evaluate_falco:
        return asyncio.run(evaluate_falco(args, files, budget))
    os.umask(0o077)
    options=processing_options(args)
    if (args.nanoplot_loglength or args.nanoplot_individual_plots) and args.mode != 'nanoplot':
        raise ValueError('NanoPlot plotting options require --mode nanoplot')
    qc_options={'loglength':args.nanoplot_loglength,'individual_plots':args.nanoplot_individual_plots} if args.mode=='nanoplot' else None
    args.output.mkdir(parents=True,mode=0o700)  # Refuse to overwrite any previous evidence/results.
    fingerprint_started=time.monotonic()
    before=[fingerprint(path,args.hash_inputs) for path in files]
    settings=Settings(roots=list(dict.fromkeys(path.parent for path in files)),output=args.output/'results',frontend=args.output/'frontend',cpus=capacity,memory_mb=budget,fastqc=os.environ.get('QUALIDOCK_FASTQC','fastqc'),multiqc=os.environ.get('QUALIDOCK_MULTIQC','multiqc'),fastp=os.environ.get('QUALIDOCK_FASTP','fastp'),seqkit=os.environ.get('QUALIDOCK_SEQKIT','seqkit'),nanoplot=os.environ.get('QUALIDOCK_NANOPLOT','NanoPlot'))
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
            response=client.post('/api/runs',json={'name':'Authorized filesystem benchmark','mode':args.mode,'paths':list(map(str,files)),'threads':args.threads,'processing_options':options,'qc_options':qc_options})
            if response.status_code!=201: raise RuntimeError(f'Cannot start benchmark ({response.status_code}): {response.text}')
            run_id=response.json()['id']
            log_offset=0; snapshot=None
            while True:
                tick=time.monotonic()
                response=client.get(f'/api/runs/{run_id}')
                latency(evidence,'run',tick,response.status_code)
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
                    latency(evidence,name,tick,response.status_code)
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
                    evidence.update(cancellation_requested=True,timeout_reached=True)
                    break  # Persist the actual terminal state after cancellation cleanup.
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
            if args.mode=='nanoplot':
                validation_file=settings.output/run_id/'qc/private/source-validation.json'
                validation=json.loads(bounded_text(validation_file)) if validation_file.exists() else {}
                evidence['qc_options']=qc_options
                evidence['registered_report_bytes']=sum(r['size'] for r in run['reports'])
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
        evidence['status']='timed_out' if evidence.get('timeout_reached') else 'measured'
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
    if evidence.get('timeout_reached') or evidence['run']['state'] not in {'completed','cancelled'}: raise SystemExit(1)


async def evaluate_falco(args, files, budget):
    """Qualification only: one existing executor, sequential commands, no new runs/API."""
    if args.mode != 'fastqc' or args.cancel_after is not None or not 1 <= args.repeats <= 5:
        raise ValueError('Engine evaluation requires --mode fastqc, 1–5 repeats and no cancellation request')
    os.umask(0o077)
    args.output.mkdir(parents=True, mode=0o700)
    tools = {name: await detect_tool(name, executable) for name, executable in
             [('fastqc', os.environ.get('QUALIDOCK_FASTQC', 'fastqc')), ('falco', args.evaluate_falco)]}
    if any(not value['compatible'] for value in tools.values()):
        raise ValueError(str(tools))
    evidence = {'scope': 'Local engine qualification; uncontrolled cache, no shared-storage acceptance',
                'platform': sys.platform, 'tools': tools, 'threads': args.threads, 'memory_mb': budget,
                'input_bytes': sum(path.stat().st_size for path in files),
                'inputs': [dict(path=str(path), **fingerprint(path, args.hash_inputs)) for path in files],
                'source_evidence': 'sha256_before_after' if args.hash_inputs else 'metadata_only',
                'measurements': [], 'status': 'running'}
    # wait4 observes only this actual command, excluding version probes and other
    # repetitions. It does not claim simultaneous process-tree peak RSS or byte I/O.
    measure = '''import json, os, resource, sys, time
command=json.loads(sys.argv[1]); started=time.monotonic(); pid=os.fork()
if pid==0:
 os.execv(command[0],command)
_,status,r=os.wait4(pid,0);code=os.waitstatus_to_exitcode(status)
json.dump({'wall_seconds':time.monotonic()-started,'cpu_user_seconds':r.ru_utime,'cpu_system_seconds':r.ru_stime,
 'waited_high_water_rss_bytes':r.ru_maxrss*(1 if sys.platform=='darwin' else 1024),
 'block_input_operations':r.ru_inblock,'block_output_operations':r.ru_oublock,'exit_code':code},open(sys.argv[2],'w'))
sys.exit(code if 0<=code<=255 else 1)
'''
    executor = LocalExecutor(max(256, budget-256))
    try:
        for index, source in enumerate(files):
            stem = re.sub(r'\.(fastq|fq)(\.gz)?$', '', source.name, flags=re.I)
            if stem in {'', '.', '..'}:
                raise ValueError('Unsafe output basename for engine evaluation')
            for trial in range(args.repeats):
                for name in (('validation','fastqc','falco') if trial % 2 == 0 else ('validation','falco','fastqc')):
                    directory = args.output/f'input-{index}'/f'{trial}-{name}'
                    directory.mkdir(parents=True)
                    resource_file = directory/'resources.json'
                    if name == 'validation':
                        configuration = directory/'validation-input.json'
                        configuration.write_text(json.dumps({'mode':'full','quick_reads':10000,'pairs':[],
                            'files':[{'id':str(index),'path':str(source),'snapshot':snapshot(source.stat())}]}))
                        argv = [sys.executable,'-m','qualidock.integrity_worker','--config',str(configuration),'--output',str(directory/'validation.json')]
                    else:
                        executable = tools[name]['executable']
                        argv = ([executable,'--outdir',str(directory),'--threads',str(args.threads),'--memory','512','--format','fastq',str(source)]
                                if name == 'fastqc' else [executable,'--output',str(directory),'--threads',str(args.threads),'--mem','256M','--groups',str(source)])
                    identity = f'{index}-{trial}-{name}'
                    started = time.monotonic()
                    if name == 'validation': validation_started = started
                    task = asyncio.create_task(executor.execute(identity,[sys.executable,'-c',measure,json.dumps(argv),str(resource_file)],directory,directory/'tool.log',args.threads))
                    counters = {}
                    while not task.done():
                        process = executor.processes.get(identity)
                        if process: counters.update(usage(process.pid))
                        if time.monotonic()-started > args.timeout:
                            await executor.cancel(identity)
                        await asyncio.sleep(.05)
                    code = await task
                    if code: raise ValueError(f'{name} command failed ({code}); inspect {directory}/tool.log')
                    measured = json.loads(resource_file.read_text())
                    if name == 'falco' and evidence['measurements'][-1]['engine'] == 'validation':
                        measured['validated_falco_serial_wall_seconds'] = time.monotonic()-validation_started
                    if name == 'validation':
                        validation = json.loads((directory/'validation.json').read_text())
                        if validation['result'] != 'passed': raise ValueError('Input failed actual full validation')
                        counts = validation['files'][0]
                        text, summary = 'QualiDock full structural validation', ''
                        stats = {'Filename':source.name, 'Total Sequences':str(counts['records_scanned']), 'Total Bases':str(counts['bases_scanned'])}
                    elif name == 'fastqc':
                        with zipfile.ZipFile(directory/(stem+'_fastqc.zip')) as archive:
                            text = archive.read(stem+'_fastqc/fastqc_data.txt').decode()
                            summary = archive.read(stem+'_fastqc/summary.txt').decode()
                    else:
                        text = bounded_text(directory/stem/'fastqc_data.txt')
                        summary = bounded_text(directory/stem/'summary.txt')
                    if name != 'validation':
                        basic = text.split('>>Basic Statistics\t',1)[1].split('>>END_MODULE',1)[0]
                        stats = dict(line.split('\t',1) for line in basic.splitlines() if '\t' in line and not line.startswith('#'))
                    if stats.get('Filename') != source.name or int(stats.get('Total Sequences','0')) <= 0:
                        raise ValueError('Engine output does not identify a nonempty original input')
                    observation = dict(executor.observations[identity])
                    if sys.platform != 'linux':
                        observation.update(peak_sampled_rss_bytes=None, rss_scope='Portable evaluation does not assert Linux process-tree RSS')
                    evidence['measurements'].append({'input': str(source), 'engine': name, 'trial': trial, 'argv': argv,
                        **measured, 'cpu_percent_one_core': 100*(measured['cpu_user_seconds']+measured['cpu_system_seconds'])/measured['wall_seconds'],
                        'process_counters_not_summable': counters, 'executor_observation': observation,
                        **({'validation_scan': counts} if name == 'validation' else {}),
                        'reported_header': text.splitlines()[0], 'basic_statistics': stats, 'modules': parse_summary(summary)})
                    print(f'{name} trial {trial+1}: {source.name}, {measured["wall_seconds"]:.3f}s',flush=True)
        evidence['status'] = 'measured'
    except BaseException as exc:
        evidence.update(status='failed', error=repr(exc))
        raise
    finally:
        unchanged = all(before == dict(path=str(path), **fingerprint(path,args.hash_inputs)) for before,path in zip(evidence['inputs'],files))
        evidence['source_fingerprint_unchanged'] = unchanged
        evidence['source_unchanged'] = unchanged if args.hash_inputs else None
        if not unchanged: evidence['status'] = 'failed_source_changed'
        evidence['memory_scope'] = 'wait4 kernel high-water RSS of each command and waited descendants, not simultaneous tree peak; executor RSS is sampled'
        evidence['io_scope'] = 'Kernel block operation counts and non-additive Linux per-process observations, not bytes or NFS/Lustre throughput'
        (args.output/'falco-evaluation.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n')
    if evidence['status'] != 'measured': raise ValueError(evidence['status'])


if __name__=='__main__': main(parser().parse_args())
