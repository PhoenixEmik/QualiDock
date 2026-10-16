"""Cancellable release bundles share the existing LocalExecutor and run lock."""
import asyncio
from copy import deepcopy
import hashlib
from importlib.metadata import version,PackageNotFoundError
import platform
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid
from .delivery import export_data,csv_export
from .integrity import snapshot
from .manager import ACTIVE,now,save_json


def interrupted(run):
    record=run.get('release_export')
    if not record or record.get('state') not in ACTIVE:return False
    record.update(state='interrupted',finished_at=now(),error='Previous session ended before the bundle was committed')
    return True


def portable(name):return re.sub(r'[^A-Za-z0-9._-]','_',name)[:160] or 'report'


class ReleaseExports:
    def __init__(self,manager):self.manager=manager;self.tasks={};self.cancelled=set()

    def plan(self,run,evaluation,include_reports,include_paths,mode):
        check=next(check for check in evaluation['checks'] if check['id']=='integrity')
        if check['state']!='pass':raise ValueError('Complete current source hashing and mate validation before exporting any release/reference bundle')
        selected=evaluation['files'];ids=set(evaluation['sample_ids']);selected_paths={file['path'] for file in selected}
        directory=self.manager.directory(run['id']);artifacts=[]
        selected_ids={file['file_id'] for file in selected}
        screening_artifacts={entry[key] for entry in (run.get('screening') or {}).get('files',[]) if entry['id'] in selected_ids for key in ('report_artifact','metrics_artifact') if entry.get(key)}
        if include_reports:
            for registered in run['reports']:
                name=registered['path'];path=Path(name)
                if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe registered report path')
                if not name.startswith(('fastqc/','multiqc/','inputs/')) and name not in screening_artifacts:continue
                if name.startswith('fastqc/'):
                    mapping=run.get('report_input_map',{}).get(name.replace('_fastqc.html','_fastqc.zip'))
                    if not mapping or mapping.get('path') not in selected_paths:continue
                target=self.manager.artifact(run['id'],name)
                if target.resolve()!=target:raise ValueError('Report source contains symlink components')
                artifacts.append({'source':str(target),'source_artifact':name,'snapshot':snapshot(target.stat()),
                                  'archive_path':'reports/'+hashlib.sha256(name.encode()).hexdigest()[:24]+'/'+portable(target.name)})
        total=sum(entry['snapshot']['size'] for entry in artifacts)
        if total>2*1024**3:raise ValueError('Original report artifacts exceed the 2 GiB bundle limit; export references without originals')
        data=deepcopy(evaluation['delivery']);data['files']=selected;data['yields']=[row for row in data['yields'] if row['sample_id'] in ids]
        data['reconciliation']=next(check for check in evaluation['checks'] if check['id']=='expected_delivery')['evidence']
        manifest=export_data(data,include_paths)
        status='approved' if evaluation['readiness']=='ready' and evaluation['review_state']=='approved' else 'review_required'
        manifest.update(release_status=status,source_checksums='computed on source; receiving system must independently verify after transfer',
                        selected_sample_ids=evaluation['sample_ids'],excluded_sample_ids=sorted({file['sample_id'] for file in evaluation['delivery']['files']}-ids))
        checks=deepcopy(evaluation['checks'])
        next(check for check in checks if check['id']=='expected_delivery')['evidence']=manifest['reconciliation']
        review={key:evaluation[key] for key in ('evaluator_version','fingerprint','sample_ids','file_ids','policy','readiness','review_state','decision','active_waivers')}
        review.update(checks=checks,history=[event for event in evaluation['history'] if set(event['sample_ids'])==ids])
        metrics={};path=directory/'metrics.json'
        if path.exists():
            from .metrics import bounded_text
            raw=json.loads(bounded_text(path));report_ids={file['report_id'] for file in selected}
            metrics={'source_analysis_id':run['id'],'samples':[sample for sample in raw.get('samples',[]) if sample['id'] in report_ids]}
        provenance={'schema_version':1,'source_analysis_id':run['id'],'analysis_name':run['name'],'analysis_mode':run['mode'],'created_at':run['created_at'],
                    'completed_at':run.get('finished_at'),'tool_versions':manifest['tool_versions'],'execution_parameters':{key:value for key,value in run.get('parameters',{}).items() if key in {'threads','memory_mb','executor'}},
                    'input_stage':data['input_stage'],'processing_notes':data['processing_notes'],'integrity_task_id':run['integrity']['task_id'],
                    'integrity_validator_version':run['integrity']['version'],'official_reports_included':include_reports,'absolute_input_paths_included':include_paths}
        try:qualidock_version = version('qualidock')
        except PackageNotFoundError:qualidock_version = None
        provenance.update(exporter={'name':'QualiDock','version':qualidock_version,'python':platform.python_version()},
                          qc_executions=[{key:entry.get(key) for key in ('tool','started_at','finished_at','exit_code')} for entry in run.get('executions',[])],
                          integrity_execution={key:run['integrity'].get('execution',{}).get(key) for key in ('started_at','finished_at','exit_code','resources')},
                          screening_execution={key:(run.get('screening') or {}).get('execution',{}).get(key) for key in ('started_at','finished_at','exit_code','resources')} if run.get('screening') else None)
        readme=f'''# QualiDock {status} reference bundle

Analysis: {run['id']}
Release review fingerprint: {evaluation['fingerprint']}

FASTQs are NOT copied into this ZIP. Place independently transferred source files
at the logical relative locations listed in manifest.json before running
`sha256sum -c checksums.sha256`. The checksum file also covers bundled metadata
and reports, excluding itself. A missing referenced FASTQ is expected until the
receiving system has transferred it. Source hash computation is not verification
after transfer, and is not biological sample identity verification.

A review_required bundle is diagnostic evidence, not an approved release.
Review explicit quantity contracts, exceptions, unavailable checks and the
recorded reviewer action. Informational FastQC WARN/FAIL is module-specific.
Raw versus processed FASTQ and upstream adapter/UMI operations are declarations,
not processing performed by this exporter. Unknown processing remains unknown.

Original reports included: {include_reports}. Originals are byte-preserved and
may include private filesystem paths and samples excluded from this handoff.
FASTQ references/selected quantities remain scoped to selected complete groups.
Private input paths explicitly included: {include_paths}. Review free-text names,
notes and reviewer reasons before sharing. CSV export mode: {mode}.

Checksums and the ZIP checksum record outside the bundle are plain SHA-256, not
digital signatures. The Unix actor identifies the current application user;
self-declared reviewer labels are not separate authenticated identities.
'''
        return {'artifact_root':str(directory),'source_files':selected,'artifacts':artifacts,'estimated_bytes':total+8*1024**2+3*len(json.dumps({'manifest':manifest,'qc_metrics':metrics,'review':review}).encode()),
                'payload':{'manifest':manifest,'csv':csv_export(data,mode,include_paths),'qc_metrics':metrics,'provenance':provenance,'review':review,'release_status':status,'readme':readme}}

    async def start(self,run_id,sample_ids,include_reports=False,acknowledge_report_paths=False,include_paths=False,mode='spreadsheet',fingerprint=None):
        manager=self.manager;run=manager.delivery.writable(run_id)
        if manager.closing or run['state'] in ACTIVE or run_id in self.tasks or len(self.tasks)>=20 or run_id in manager.validation.tasks or run_id in manager.screening.tasks:raise ValueError('Wait until active QC, integrity or export tasks finish')
        if include_reports and not acknowledge_report_paths:raise ValueError('Including original reports requires acknowledgment of embedded private paths and excluded samples')
        if mode not in {'spreadsheet','verbatim'}:raise ValueError('Select a known CSV export safety mode')
        saved=deepcopy(run);evaluation=await asyncio.to_thread(manager.release.inspect,run_id,sample_ids,saved)
        if fingerprint is not None and fingerprint!=evaluation['fingerprint']:raise ValueError('Release evidence changed; refresh the review before exporting')
        config=await asyncio.to_thread(self.plan,saved,evaluation,include_reports,include_paths,mode)
        if saved['updated_at']!=run['updated_at'] or run_id in self.tasks or run_id in manager.validation.tasks or run_id in manager.screening.tasks or manager.closing:raise ValueError('Evidence changed while preparing export; refresh before exporting')
        parent=manager.directory(run_id)/'release-exports'
        if parent.is_symlink() or parent.resolve()!=parent:raise ValueError('Export directory has symlink components')
        parent.mkdir(exist_ok=True,mode=0o700)
        if shutil.disk_usage(parent).free < config['estimated_bytes']+64*1024**2:raise ValueError('Insufficient available space for the reference bundle')
        task_id='release-'+uuid.uuid4().hex;destination=parent/task_id;destination.mkdir(mode=0o700)
        save_json(destination/'config.json',config)
        previous=run.get('release_export_history',[])
        if run.get('release_export'):previous=[*previous,run['release_export']]
        record={'task_id':task_id,'state':'queued','release_status':config['payload']['release_status'],'fingerprint':evaluation['fingerprint'],'sample_ids':evaluation['sample_ids'],
                'requested_at':now(),'started_at':None,'finished_at':None,'requested_by':manager.delivery.actor(),'error':None,'artifact':None,'sha256':None,
                'include_reports':include_reports,'include_paths':include_paths,'csv_mode':mode}
        manager.update(run,release_export=record,release_export_history=previous)
        self.tasks[run_id]=asyncio.create_task(self.execute(run,record,config,destination))
        return record

    async def execute(self,run,record,config,destination):
        manager=self.manager;task_id=record['task_id'];command=None;execution=None
        try:
            async with manager.slot:
                if task_id in self.cancelled:return
                # Recheck queued evidence before consuming output resources.
                current=await asyncio.to_thread(manager.release.inspect,run['id'],record['sample_ids'],deepcopy(run))
                if current['fingerprint']!=record['fingerprint']:raise ValueError('Release evidence changed while export was queued')
                manager.update(run,release_export={**record,'state':'running','started_at':now()})
                candidate=destination/'bundle.zip.pending'
                argv=[sys.executable,'-m','qualidock.release_worker','--config',str(destination/'config.json'),'--output',str(candidate),'--result',str(destination/'result.json')]
                execution={'argv':argv,'started_at':now(),'exit_code':None,'finished_at':None}
                command=asyncio.create_task(manager.executor.execute(task_id,argv,destination,destination/'export.log',1));code=await command
                execution.update(exit_code=code,finished_at=now(),resources=getattr(manager.executor,'observations',{}).get(task_id))
                if task_id in self.cancelled:
                    manager.update(run,release_export={**run['release_export'],'execution':execution});return
                if code:raise ValueError(f'Release worker exited {code}; incomplete bundle is not downloadable')
                result=manager.validation.read(destination/'result.json')
                if candidate.is_symlink() or candidate.resolve()!=candidate or candidate.stat().st_size!=result['bytes'] or not re.fullmatch('[a-f0-9]{64}',result.get('sha256','')):raise ValueError('Release worker did not produce a bounded valid bundle record')
                current=await asyncio.to_thread(manager.release.inspect,run['id'],record['sample_ids'],deepcopy(run))
                if current['fingerprint']!=record['fingerprint'] or (record['release_status']=='approved' and current['review_state']!='approved'):raise ValueError('Inputs, policy or review changed during export; bundle withheld')
                name='qualidock-'+run['id']+'-'+record['release_status']+'-reference.zip';final=destination/name
                os.link(candidate,final);candidate.unlink()
                completed={**run['release_export'],**result,'state':'completed','finished_at':now(),'execution':execution,'artifact':str(final.relative_to(manager.directory(run['id'])))}
                save_json(destination/'export.json',completed);manager.update(run,release_export=completed)
        except Exception as exc:
            if task_id not in self.cancelled:
                try:manager.update(run,release_export={**run['release_export'],'state':'failed','finished_at':now(),'error':str(exc),'artifact':None,'execution':execution})
                except (OSError,ValueError):run['release_export'].update(state='failed',error=str(exc),artifact=None);manager.revision+=1
        finally:
            if command and not command.done():await manager.executor.cancel(task_id);await asyncio.gather(command,return_exceptions=True)
            try:manager.refresh_reports(run)
            except (OSError,ValueError):pass
            self.tasks.pop(run['id'],None)

    async def cancel(self,run_id,state='cancelled'):
        manager=self.manager;run=manager.runs[run_id];record=run.get('release_export')
        if not record or record['state'] not in ACTIVE:return record
        self.cancelled.add(record['task_id']);await manager.executor.cancel(record['task_id'])
        manager.update(run,release_export={**record,'state':state,'finished_at':now(),'error':'Incomplete export withheld','artifact':None})
        return run['release_export']

    async def close(self):
        for run_id in list(self.tasks):
            try:await self.cancel(run_id,'interrupted')
            except (OSError,ValueError):
                record=self.manager.runs[run_id]['release_export'];self.cancelled.add(record['task_id']);await self.manager.executor.cancel(record['task_id']);record.update(state='interrupted',artifact=None)
        await asyncio.gather(*list(self.tasks.values()),return_exceptions=True)
