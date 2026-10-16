"""Internal offline screening worker; external tool uses safe argument arrays."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from .integrity import snapshot
from .manager import now,save_json
from .screening import parse_report


def database_hash(entry):
    path=Path(entry['source'])
    if path.is_symlink() or path.resolve()!=path:raise ValueError('Reference database contains symlinks')
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or snapshot(os.fstat(stream.fileno()))!=entry['snapshot']:raise ValueError('Reference changed before hashing')
        sha=hashlib.sha256()
        while chunk:=stream.read(1024*1024):sha.update(chunk)
        if snapshot(os.fstat(stream.fileno()))!=entry['snapshot'] or snapshot(path.stat())!=entry['snapshot']:raise ValueError('Reference changed during hashing')
    return {'name':entry['name'],'bytes':entry['snapshot']['size'],'sha256':sha.hexdigest()}


def unchanged_database(entries):
    for entry in entries:
        path=Path(entry['source'])
        if path.is_symlink() or path.resolve()!=path or snapshot(path.stat())!=entry['snapshot']:raise ValueError('Reference database changed during screening')


def run(config,directory,output):
    directory=Path(directory);output=Path(output)
    result={'phase':'Hashing offline reference','files':[],'current_file_id':None,'database':config['database'],'database_files':[],'finished_at':None}
    save_json(output,result)
    for entry in config['database_files']:
        result['database_files'].append(database_hash(entry));save_json(output,result)
    for entry in config['files']:
        result.update(phase='Classifying individual FASTQ',current_file_id=entry['id']);save_json(output,result)
        row={'id':entry['id'],'path':entry['path'],'name':entry['name'],'source_snapshot':entry.get('snapshot'),'source_sha256':entry.get('source_sha256'),
             'state':'running','coverage':'not_evaluated','records_processed':None,'classified_records':None,'unclassified_records':None,
             'known_input_records':entry.get('known_reads'),'denominator_source':entry.get('counts_source'),'screened_fraction':None,'error':None,'execution':None,
             'report_artifact':None,'metrics_artifact':None,'started_at':now(),'finished_at':None}
        report=directory/(entry['id']+'.report.tsv');metrics=directory/(entry['id']+'.metrics.json');log=directory/(entry['id']+'.log')
        try:
            if entry.get('preflight_error'):raise ValueError(entry['preflight_error'])
            source=Path(entry['path'])
            if source.is_symlink() or source.resolve()!=source or snapshot(source.stat())!=entry['snapshot']:raise ValueError('Source FASTQ changed before screening')
            if '\n' in str(source) or '\r' in str(source):raise ValueError('Kraken2 decompression does not support newline path names safely')
            with source.open('rb') as stream:compressed=stream.read(2)==b'\x1f\x8b'
            argv=[config['tool']['executable'],'--db',config['database_path'],'--threads',str(config['threads']),'--memory-mapping','--confidence','0','--minimum-hit-groups','2','--report',str(report),'--output','/dev/null',*(['--gzip-compressed'] if compressed else []),'--',str(source)]
            execution={'argv':argv,'started_at':now(),'finished_at':None,'exit_code':None};row['execution']=execution
            with log.open('ab',buffering=0) as sink:
                sink.write((repr(argv)+'\n').encode());code=subprocess.run(argv,stdout=sink,stderr=subprocess.STDOUT,check=False).returncode
            execution.update(exit_code=code,finished_at=now())
            if code:raise ValueError(f'Kraken2 exited {code}; inspect its per-file log')
            if snapshot(source.stat())!=entry['snapshot'] or source.resolve()!=source:raise ValueError('Source FASTQ changed during screening')
            unchanged_database(config['database_files'])
            data=parse_report(report)
            if data['records_processed'] is None and entry.get('known_reads')==0:
                data.update(records_processed=0,classified_records=0,unclassified_records=0)
            row.update({key:data[key] for key in ('records_processed','classified_records','unclassified_records')})
            known=entry.get('known_reads');processed=data['records_processed']
            row['screened_fraction']=processed/known if known and processed is not None and 0<=processed<=known else None
            row['coverage']='full' if known is not None and processed==known else 'partial' if known is not None and processed is not None else 'not_evaluated'
            row['state']='completed' if row['coverage']=='full' else 'partial'
            if row['state']=='partial':row['error']='Tool counts differ from the current input denominator, or that denominator is unavailable; complete coverage is not asserted'
            row['report_artifact']=str(report.relative_to(Path(config['run_directory'])))
            row['metrics_artifact']=str(metrics.relative_to(Path(config['run_directory'])))
            data.update(source_analysis_id=config['analysis_id'],source_task_id=directory.name,file_id=entry['id'],source_tool='Kraken2',source_version=config['tool']['version'],database=config['database'],database_files=result['database_files'],assay=config['assay'],expected_taxids=config['expected_taxids'],coverage=row['coverage'],screened_fraction=row['screened_fraction'])
            save_json(metrics,data)
        except (ValueError,OSError,UnicodeError) as exc:
            row.update(state='failed',error=str(exc),coverage='not_evaluated')
            if report.is_file() and not report.is_symlink():row['report_artifact']=str(report.relative_to(Path(config['run_directory'])))
        row['finished_at']=now();result['files'].append(row);result['current_file_id']=None;save_json(output,result)
    unchanged_database(config['database_files'])
    result.update(phase='Finished',finished_at=now());save_json(output,result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    path=Path(args.config);run(json.loads(path.read_text()),path.parent,args.output)

if __name__=='__main__':main()
