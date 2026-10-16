"""Stream a reference-only release ZIP; original FASTQs are never copied."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path,PurePosixPath
import stat
import zipfile
from .integrity import snapshot
from .manager import save_json


def safe_name(value):
    path=PurePosixPath(value)
    if path.is_absolute() or path.as_posix()!=value or '..' in path.parts or ':' in value or '\\' in value or not value or any(ord(c)<32 for c in value):
        raise ValueError('Unsafe archive member path')
    return value


def source_file(entry,root):
    path=Path(entry['source'])
    if path.is_symlink() or path.resolve()!=path or not path.is_relative_to(root):raise ValueError('Report source escaped its owned run directory')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    stream=os.fdopen(fd,'rb')
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or snapshot(os.fstat(stream.fileno()))!=entry['snapshot']:
        stream.close();raise ValueError('Report changed before export')
    return stream


def build(config,output):
    root=Path(config['artifact_root']);output=Path(output)
    for file in config['source_files']:
        path=Path(file['path'])
        if path.is_symlink() or path.resolve()!=path or snapshot(path.stat())!=file['source_snapshot']:
            raise ValueError('Source FASTQ changed since full checksum validation')
    metadata=[];names=set()
    def info(name):
        safe_name(name)
        if name.casefold() in names:raise ValueError('Archive filename collision')
        names.add(name.casefold());value=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));value.create_system=3
        value.external_attr=0o100600<<16;value.compress_type=zipfile.ZIP_DEFLATED
        return value
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,allowZip64=True) as archive:
        os.fchmod(archive.fp.fileno(),0o600)
        def write(name,raw):
            archive.writestr(info(name),raw)
            metadata.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
        def document(name,value):write(name,(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+'\n').encode())
        report_entries=[]
        for index,entry in enumerate(config['artifacts']):
            sha=hashlib.sha256();size=0
            with source_file(entry,root) as source,archive.open(info(entry['archive_path']),'w',force_zip64=True) as target:
                while chunk:=source.read(1024*1024):
                    target.write(chunk);sha.update(chunk);size+=len(chunk)
                if snapshot(os.fstat(source.fileno()))!=entry['snapshot'] or snapshot(Path(entry['source']).stat())!=entry['snapshot']:
                    raise ValueError('Report changed during streaming export')
            record={'path':entry['archive_path'],'sha256':sha.hexdigest(),'bytes':size}
            metadata.append(record);report_entries.append({**record,'source_artifact':entry['source_artifact']})
            print(f'Bundled {index+1} of {len(config["artifacts"])} registered report artifacts',flush=True)
        payload=config['payload'];manifest={**payload['manifest'],'report_artifacts':report_entries}
        document('manifest.json',manifest)
        write('manifest.csv',payload['csv'].encode())
        document('qc-metrics.json',payload['qc_metrics'])
        document('provenance.json',payload['provenance'])
        document('release-review.json',payload['review'])
        report='<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'"><title>QualiDock release review</title><h1>QualiDock '+html.escape(payload['release_status'])+'</h1><p>Reference-only handoff. FASTQs are not included. Source checksums are not post-transfer verification.</p><h2>Selected sample yield and provenance</h2><pre>'+html.escape(json.dumps(manifest,indent=2,ensure_ascii=False))+'</pre><h2>Review and exceptions</h2><pre>'+html.escape(json.dumps(payload['review'],indent=2,ensure_ascii=False))+'</pre>'
        write('release-report.html',report.encode())
        write('README.md',payload['readme'].encode())
        lines=[f"{file['sha256']}  {file['input_reference']}" for file in manifest['files']]
        lines += [f"{entry['sha256']}  {entry['path']}" for entry in metadata]
        archive.writestr(info('checksums.sha256'),('\n'.join(lines)+'\n').encode())
    with output.open('rb') as stream:
        sha=hashlib.file_digest(stream,'sha256').hexdigest();os.fsync(stream.fileno())
    return {'sha256':sha,'bytes':output.stat().st_size,'archive_entries':len(names),'source_file_count':len(config['source_files'])}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',required=True);parser.add_argument('--result',required=True);args=parser.parse_args()
    config=json.loads(Path(args.config).read_text());result=build(config,args.output);save_json(Path(args.result),result)

if __name__=='__main__':main()
