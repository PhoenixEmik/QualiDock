"""Opt-in offline classification through the existing bounded execution system."""
import asyncio
from copy import deepcopy
import os
from pathlib import Path
import sys
import uuid
from .manager import ACTIVE,now,save_json
from .screening import configurations,resolve_database,public_database
from .tools import detect_tool


def interrupted(run):
    record=run.get('screening')
    if not record or record.get('state') not in ACTIVE:return False
    record.update(state='interrupted',finished_at=now(),error='Session ended before screening completed',current_file_id=None)
    return True


class ScreeningJobs:
    def __init__(self,manager):self.manager=manager;self.tasks={};self.cancelled=set()

    async def config(self):
        tool=await detect_tool('kraken2',self.manager.settings.kraken2);databases=[];error=None
        try:
            for config in configurations(self.manager.settings):
                public=public_database(config)
                try:
                    _,files=resolve_database(config);public.update(available=True,bytes=sum(entry['snapshot']['size'] for entry in files),error=None)
                except (ValueError,OSError):public.update(available=False,error='Reference directory/files are unavailable, unsafe or unsupported')
                databases.append(public)
        except ValueError as exc:error=str(exc)
        return {'tool':tool,'databases':databases,'error':error,'max_threads':self.manager.settings.max_threads,'mode':'offline only; no reference downloads or remote read uploads'}

    async def start(self,run_id,file_ids,database_id,threads=1,assay='Unspecified',expected_taxids=None):
        manager=self.manager;run=manager.delivery.writable(run_id)
        if manager.closing or run['state'] in ACTIVE or run_id in self.tasks or len(self.tasks)>=20:raise ValueError('Wait until QC/current screening finishes or a queue slot becomes available')
        if threads<1 or threads>manager.settings.max_threads:raise ValueError('Screening threads exceed this session allocation')
        expected_taxids=expected_taxids or []
        if len(assay)>120 or not assay.strip() or len(expected_taxids)>20 or any(not isinstance(value,str) or not value.isascii() or not value.isdecimal() or len(value)>20 for value in expected_taxids):raise ValueError('Use an assay label and at most 20 explicit decimal taxonomy IDs')
        config=next((entry for entry in configurations(manager.settings) if entry['id']==database_id),None)
        if config is None:raise ValueError('Choose an administrator-configured offline database identity')
        tool=await detect_tool('kraken2',manager.settings.kraken2)
        if not tool['compatible']:raise ValueError(tool['error'] or 'Kraken2 is unavailable/incompatible; no tool is installed automatically')
        root,db_files=await asyncio.to_thread(resolve_database,config)
        saved=deepcopy(run);data=await asyncio.to_thread(manager.delivery.inspect,run_id,saved)
        lookup={file['file_id']:file for file in data['files']}
        if not file_ids or len(file_ids)!=len(set(file_ids)) or set(file_ids)-set(lookup):raise ValueError('Select existing source FASTQ identities from this analysis; imported reports alone cannot be screened')
        prepared=await asyncio.to_thread(manager.validation.prepare,saved,'full')
        files=[]
        for entry in prepared['files']:
            if entry['id'] in file_ids:
                observed=lookup[entry['id']]
                files.append({**entry,'known_reads':observed['reads'],'counts_source':observed['counts_source'],'source_sha256':observed['sha256']})
        if saved['updated_at']!=run['updated_at'] or manager.closing or run_id in self.tasks or run.get('release_export',{}).get('state') in ACTIVE:raise ValueError('Analysis changed while preparing screening; refresh and retry')
        parent=manager.directory(run_id)/'screening'
        if parent.is_symlink() or parent.resolve()!=parent:raise ValueError('Screening output directory contains symlink components')
        parent.mkdir(exist_ok=True,mode=0o700);task_id='screen-'+uuid.uuid4().hex;destination=parent/task_id;destination.mkdir(mode=0o700)
        task_config={'analysis_id':run_id,'tool':tool,'database':public_database(config),'database_path':str(root),'database_files':db_files,'files':files,'threads':threads,
                     'assay':assay,'expected_taxids':expected_taxids,'administrator_reference_config':config,'run_directory':str(manager.directory(run_id))}
        save_json(destination/'config.json',task_config)
        history=run.get('screening_history',[])
        if run.get('screening'):history=[*history,run['screening']]
        record={'task_id':task_id,'state':'queued','source_tool':'Kraken2','tool':tool,'database':public_database(config),'database_files':[],
                'assay':assay,'expected_taxids':expected_taxids,'threads':threads,'parameters':{'confidence':0,'minimum_hit_groups':2,'memory_mapping':True,'paired':False,'subsampling':False},
                'total_files':len(files),'files':[],'current_file_id':None,'phase':'Queued','requested_at':now(),'started_at':None,'finished_at':None,
                'requested_by':manager.delivery.actor(),'error':None,'artifact':str((destination/'screening.json').relative_to(manager.directory(run_id)))}
        manager.update(run,screening=record,screening_history=history)
        self.tasks[run_id]=asyncio.create_task(self.execute(run,task_config,destination))
        return record

    async def execute(self,run,config,destination):
        manager=self.manager;task_id=run['screening']['task_id'];command=None;execution=None
        try:
            async with manager.slot:
                if task_id in self.cancelled:return
                manager.update(run,screening={**run['screening'],'state':'running','started_at':now()})
                argv=[sys.executable,'-m','qualidock.screening_worker','--config',str(destination/'config.json'),'--output',str(destination/'result.json')]
                execution={'argv':argv,'started_at':now(),'finished_at':None,'exit_code':None}
                command=asyncio.create_task(manager.executor.execute(task_id,argv,destination,destination/'screening.log',config['threads']))
                last=None
                while not command.done():
                    path=destination/'result.json'
                    if path.exists() and task_id not in self.cancelled:
                        stamp=path.stat().st_mtime_ns
                        if stamp!=last:
                            result=await asyncio.to_thread(manager.validation.read,path)
                            manager.update(run,screening={**run['screening'],**result,'state':'running','execution':execution});last=stamp
                    await asyncio.wait({command},timeout=.5)
                code=await command;execution.update(exit_code=code,finished_at=now(),resources=getattr(manager.executor,'observations',{}).get(task_id))
                if task_id in self.cancelled:
                    manager.update(run,screening={**run['screening'],'execution':execution});return
                result=manager.validation.read(destination/'result.json') if (destination/'result.json').exists() else {}
                complete=code==0 and len(result.get('database_files',[]))==3 and result.get('finished_at') and len(result.get('files',[]))==len(config['files'])
                files=result.get('files',[]);good=sum(file['state']=='completed' for file in files)
                state='completed' if complete and good==len(files) else 'partial' if files and any(file.get('metrics_artifact') for file in files) else 'failed'
                record={**run['screening'],**result,'execution':execution,'state':state,'current_file_id':None,'finished_at':now(),
                        'error':None if state=='completed' else f'Screening incomplete: worker exit {code}; {good} of {len(config["files"])} files have confirmed record coverage. Inspect file evidence and logs.'}
                save_json(destination/'screening.json',record);manager.update(run,screening=record)
        except Exception as exc:
            if task_id not in self.cancelled:
                record={**run['screening'],'state':'failed','error':str(exc),'execution':execution,'finished_at':now(),'current_file_id':None}
                try:save_json(destination/'screening.json',record);manager.update(run,screening=record)
                except (OSError,ValueError):run['screening']=record;manager.revision+=1
        finally:
            if command and not command.done():await manager.executor.cancel(task_id);await asyncio.gather(command,return_exceptions=True)
            try:manager.refresh_reports(run)
            except (OSError,ValueError):pass
            self.tasks.pop(run['id'],None)

    async def cancel(self,run_id,state='cancelled'):
        manager=self.manager;run=manager.runs[run_id];record=run.get('screening')
        if not record or record['state'] not in ACTIVE:return record
        self.cancelled.add(record['task_id']);await manager.executor.cancel(record['task_id'])
        stopped={**run['screening'],'state':state,'current_file_id':None,'finished_at':now(),'error':'Screening stopped; unfinished records/reference hashes are not evaluated'}
        save_json(manager.directory(run_id)/record['artifact'],stopped);manager.update(run,screening=stopped);manager.refresh_reports(run)
        return stopped

    async def close(self):
        for run_id in list(self.tasks):
            try:await self.cancel(run_id,'interrupted')
            except (OSError,ValueError):
                record=self.manager.runs[run_id]['screening'];self.cancelled.add(record['task_id']);await self.manager.executor.cancel(record['task_id']);record.update(state='interrupted',current_file_id=None)
        await asyncio.gather(*list(self.tasks.values()),return_exceptions=True)
