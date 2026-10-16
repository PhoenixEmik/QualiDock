"""Versioned JSON policy and auditable review, scoped to one existing analysis."""
import hashlib
import json
from pathlib import Path
import uuid
from .metrics import bounded_text
from .manager import now,save_json
from .release_policy import evaluate,validate_policy,digest


class ReleaseService:
    def __init__(self,manager):self.manager=manager

    def directory(self,run_id):
        destination=self.manager.delivery.directory(run_id)/'release-review'
        if destination.is_symlink() or destination.resolve()!=destination:raise ValueError('Release review directory has symlink components')
        destination.mkdir(exist_ok=True,mode=0o700)
        return destination

    def policy(self,run_id,definition):
        run=self.manager.delivery.writable(run_id);validate_policy(definition)
        old=run.get('release_policy');history=run.get('release_policy_history',[])
        if old:history=[*history,old]
        record={'definition':definition,'revision':run.get('delivery_revision',0)+1,'updated_at':now(),'updated_by':self.manager.delivery.actor()}
        path=self.directory(run_id)/('policy-'+uuid.uuid4().hex+'.json');save_json(path,record)
        record['artifact']=str(path.relative_to(self.manager.directory(run_id)))
        self.manager.update(run,release_policy=record,release_policy_history=history,delivery_revision=record['revision'])
        self.manager.refresh_reports(run)
        return record

    def inspect(self,run_id,sample_ids,run_snapshot=None):
        run=run_snapshot if run_snapshot is not None else self.manager.runs[run_id]
        data=self.manager.delivery.inspect(run_id,run)
        metrics={};metrics_hash=None
        path=self.manager.directory(run_id)/'metrics.json'
        if path.exists():
            text=bounded_text(path);metrics=json.loads(text);metrics_hash=hashlib.sha256(text.encode()).hexdigest()
        artifacts=[]
        for report in run.get('reports',[]):
            name=report['path']
            # Review/export audit sidecars are deliberately not scientific inputs
            # to their own fingerprint (otherwise each review invalidates itself).
            if not (name.startswith(('fastqc/','multiqc/','inputs/')) or name=='metrics.json'):continue
            try:
                target=self.manager.artifact(run_id,name);stat=target.stat()
                artifacts.append({'path':name,'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'inode':stat.st_ino,'device':stat.st_dev})
            except (OSError,ValueError):artifacts.append({'path':name,'state':'unavailable'})
        context={'qc_state':run['state'],'tools':run.get('tools'), 'parameters':run.get('parameters'),'metrics_sha256':metrics_hash,'integrity_state':run.get('integrity',{}).get('state'),
                 'screening':run.get('screening'),'demultiplex':run.get('demultiplex'),'demultiplex_data_sha256':digest(data.get('demultiplex')),'artifacts':artifacts}
        result=evaluate(run,data,metrics,sample_ids,context)
        result['delivery']=data
        return result

    def action(self,run_id,evaluation,action,reason,rule_id=None,reviewer_label=''):
        run=self.manager.delivery.writable(run_id)
        if action not in {'approve','needs_review','block','waive'} or not isinstance(reason,str) or not reason.strip() or len(reason)>2000 or len(reviewer_label)>120:
            raise ValueError('Choose a known review action and supply a reason (1–2000 characters)')
        if action=='approve' and evaluation['readiness']!='ready':raise ValueError('Required checks remain blocked or unevaluated; approval is not allowed')
        if action=='waive':
            check=next((check for check in evaluation['checks'] if check['id']==rule_id),None)
            if not check or rule_id=='integrity' or not check['mandatory'] or check['state']=='pass':
                raise ValueError('Only a nonpassing configured rule can be waived; full integrity cannot be waived')
        elif rule_id is not None:raise ValueError('Rule identity is only used for a waiver')
        event={'id':uuid.uuid4().hex,'action':action,'reason':reason.strip(),'rule_id':rule_id,'reviewer_label':reviewer_label,
               'actor':self.manager.delivery.actor(),'created_at':now(),'sample_ids':evaluation['sample_ids'],'fingerprint':evaluation['fingerprint']}
        path=self.directory(run_id)/('review-'+event['id']+'.json');save_json(path,event)
        self.manager.update(run,release_reviews=[*run.get('release_reviews',[]),event])
        self.manager.refresh_reports(run)
        return event
