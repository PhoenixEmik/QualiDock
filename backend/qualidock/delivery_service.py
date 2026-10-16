"""Manifest-based delivery organization; no source FASTQs are copied or rewritten."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import uuid

from .delivery import inventory, reconcile, yields, parse_expected, integer
from .integrity import snapshot
from .metrics import bounded_text
from .manager import now, save_json
from .files import PathViolation
from .demultiplex import parse_documents, map_fastqs


class DeliveryService:
    def __init__(self, manager):
        self.manager = manager

    def inspect(self, run_id, run_snapshot=None):
        manager = self.manager
        run = run_snapshot if run_snapshot is not None else manager.runs[run_id]
        context = dict(run)
        if run.get('source_run_id') in manager.runs:
            context['input_metadata'] = manager.runs[run['source_run_id']].get('input_metadata', [])
        current = {}
        paths = run.get('sample_input_paths', run['inputs'])
        if run['mode'] == 'multiqc' and not run.get('sample_input_paths'):
            paths = []
        for raw in paths:
            try:
                path = manager.files.resolve(raw)
                if str(path) != raw:
                    raise ValueError('Source reference now resolves to another file')
                manager.readable_fastq(path)
                current[raw] = {'snapshot':snapshot(path.stat())}
            except (OSError, ValueError) as exc:
                current[raw] = {'error':str(exc)}
        metrics = {}
        path = manager.directory(run_id) / 'metrics.json'
        if path.exists():
            try:
                metrics = json.loads(bounded_text(path))
            except (OSError, ValueError):
                metrics = {}
        result = inventory(context, metrics, current)
        expected = run.get('expected_delivery')
        target_config = run.get('yield_config', {})
        result.update(analysis_id=run_id,name=run['name'],reconciliation=reconcile(result['files'], expected.get('files') if expected else None),
                      expected_manifest=expected,targets=target_config.get('targets',[]),
                      input_stage=target_config.get('input_stage','unknown'), processing_notes=target_config.get('processing_notes',''),
                      assay=target_config.get('assay','Unspecified'), delivery_revision=run.get('delivery_revision',0),
                      tool_versions={name:info.get('version') for name,info in run.get('tools',{}).items()})
        result['screening'] = run.get('screening')
        screened={entry['id']:entry for entry in (run.get('screening') or {}).get('files',[])}
        for file in result['files']:
            file['screening_snapshot_matches']=bool(file['source_snapshot'] and screened.get(file['file_id'],{}).get('source_snapshot')==file['source_snapshot'])
        result['demultiplex'] = None
        if run.get('demultiplex'):
            try:
                evidence = json.loads(bounded_text(manager.artifact(run_id,run['demultiplex']['artifact'])))
                evidence['file_mappings'] = map_fastqs(evidence,result['files'])
                result['demultiplex'] = evidence
            except (OSError,ValueError,KeyError):
                result['demultiplex'] = {'state':'not_evaluated','message':'Saved demultiplexing evidence is missing, unsupported or inaccessible'}
        result['yields'] = yields(result['files'],context,target_config.get('targets',[]))
        return result

    def writable(self, run_id):
        run = self.manager.runs[run_id]
        self.manager.stores.resolve(str(self.manager.directory(run_id).parent))
        if run.get('release_export',{}).get('state') in {'queued','running'}:
            raise ValueError('Wait until the active release export finishes before changing delivery configuration')
        return run

    @staticmethod
    def actor():
        return {'uid':os.getuid(),'unix_user':pwd.getpwuid(os.getuid()).pw_name}

    def directory(self, run_id):
        directory = self.manager.directory(run_id) / 'delivery'
        if directory.is_symlink() or directory.resolve() != directory:
            raise PathViolation('Delivery output directory contains symlink components')
        directory.mkdir(exist_ok=True,mode=0o700)
        return directory

    def expected(self, run_id, content, format):
        run = self.writable(run_id)
        files = parse_expected(content,format)
        document = {'schema_version':1,'files':files,'format':format,'submitted_text_sha256':hashlib.sha256(content.encode()).hexdigest(),
                    'updated_at':now(),'updated_by':self.actor()}
        path = self.directory(run_id) / ('expected-' + uuid.uuid4().hex + '.json')
        save_json(path,document)
        self.manager.update(run,expected_delivery={**document,'artifact':str(path.relative_to(self.manager.directory(run_id)))},delivery_revision=run.get('delivery_revision',0)+1)
        self.manager.refresh_reports(run)
        return run['expected_delivery']

    def targets(self, run_id, config, allowed=None):
        run = self.writable(run_id)
        allowed = allowed if allowed is not None else {entry['sample_id'] for entry in self.inspect(run_id)['files']}
        if set(config) - {'targets','assay','input_stage','processing_notes'}:
            raise ValueError('Unsupported yield target configuration')
        entries = config.get('targets',[])
        if len(entries) > 500:
            raise ValueError('Configure at most 500 sample quantity targets')
        seen = set()
        for target in entries:
            if set(target) != {'sample_id','metric','minimum'} or target['sample_id'] not in allowed or target['sample_id'] in seen:
                raise ValueError('Use one explicit quantity target per stable sample identity')
            if target['metric'] not in {'reads','read_pairs','bases'} or integer(target['minimum']) is None:
                raise ValueError('Target units must be reads, read_pairs or bases, with a nonnegative safe integer minimum')
            seen.add(target['sample_id'])
        if config.get('input_stage','unknown') not in {'unknown','raw_fastq','upstream_processed'}:
            raise ValueError('Select a declared input stage')
        for field,limit in [('assay',120),('processing_notes',2000)]:
            value = config.get(field,'')
            if not isinstance(value,str) or len(value) > limit:
                raise ValueError('Assay/processing notes exceed the supported length')
        self.manager.update(run,yield_config={'schema_version':1,**config,'updated_at':now(),'updated_by':self.actor()},delivery_revision=run.get('delivery_revision',0)+1)
        return run['yield_config']

    def import_demultiplex(self,run_id,documents,declared_version='',declared_run_id=''):
        run = self.writable(run_id)
        evidence = parse_documents(documents,declared_version,declared_run_id)
        destination = self.directory(run_id) / ('demultiplex-' + uuid.uuid4().hex)
        destination.mkdir(mode=0o700)
        for document in evidence['documents']:
            name = document['name']
            target = destination / name
            fd = os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream:
                stream.write(documents[name]);stream.flush();os.fsync(stream.fileno())
            document['artifact'] = str(target.relative_to(self.manager.directory(run_id)))
        evidence.update(imported_at=now(),imported_by=self.actor())
        path = destination / 'evidence.json'
        save_json(path,evidence)
        previous = run.get('demultiplex_history',[])
        if run.get('demultiplex'):previous = [*previous,run['demultiplex']]
        record = {'state':evidence['state'],'artifact':str(path.relative_to(self.manager.directory(run_id))),
                  'imported_at':evidence['imported_at'],'run_id':evidence['run_id'],'declared_tool_version':declared_version or None}
        self.manager.update(run,demultiplex=record,demultiplex_history=previous,delivery_revision=run.get('delivery_revision',0)+1)
        self.manager.refresh_reports(run)
        return evidence
