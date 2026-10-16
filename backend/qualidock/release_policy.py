"""Explainable policy checks; official QC classifications remain unchanged."""
import hashlib
import json
from .delivery import reconcile

CHECKS={'integrity','expected_delivery','quantity','demultiplex'}
STATUSES={'pass','warn','fail'}


def validate_policy(policy):
    if set(policy)-{'version','assay','required_checks','fastqc_rules'}:raise ValueError('Unsupported release policy field')
    if any(not isinstance(policy.get(key),str) or not policy[key].strip() or len(policy[key])>120 for key in ('version','assay')):
        raise ValueError('An explicit policy version and assay/project label are required')
    required=policy.get('required_checks',[])
    if not isinstance(required,list) or len(set(required))!=len(required) or set(required)-CHECKS or 'integrity' not in required:
        raise ValueError('Choose known required checks; full source integrity is mandatory and cannot be waived')
    rules=policy.get('fastqc_rules',[]);seen=set()
    if not isinstance(rules,list) or len(rules)>20:raise ValueError('Too many FastQC policy rules')
    for rule in rules:
        if set(rule)!={'module','allowed_statuses'} or not isinstance(rule['module'],str) or not 1<=len(rule['module'])<=120 or rule['module'] in seen:
            raise ValueError('FastQC rules require unique module names')
        allowed=rule['allowed_statuses']
        if not isinstance(allowed,list) or not allowed or len(set(allowed))!=len(allowed) or set(allowed)-STATUSES:
            raise ValueError('Use original FastQC pass/warn/fail classifications in policy rules')
        seen.add(rule['module'])
    return policy


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def scoped_expected(all_files,selected,expected):
    if expected is None:return None
    keys=('file_id','path','filename','sample_id','sample_name','lane','chunk','read')
    ids={file['file_id'] for file in selected};rows=[]
    for row in expected:
        matches=[file for file in all_files if all(key not in row or row[key]==file[key] for key in keys)]
        # Missing/unattributable expectations remain visible for an explicit
        # waiver rather than being silently excluded from a subset release.
        if not matches or any(file['file_id'] in ids for file in matches):rows.append(row)
    return rows


def evaluate(run,data,metrics,sample_ids,source_fingerprint):
    allowed={file['sample_id'] for file in data['files']}
    if not sample_ids or len(sample_ids)!=len(set(sample_ids)) or set(sample_ids)-allowed:
        raise ValueError('Select whole known sample groups for release review')
    selected=[file for file in data['files'] if file['sample_id'] in sample_ids]
    policy=run.get('release_policy');definition=policy.get('definition') if policy else None
    required=set(definition.get('required_checks',[])) if definition else {'integrity'}
    checks=[]
    def add(key,label,state,explanation,**details):
        checks.append({'id':key,'name':label,'state':state,'mandatory':key in required or key.startswith('fastqc:'),'explanation':explanation,**details})
    scan=run.get('integrity',{});pairs={pair['id']:pair for pair in scan.get('pairs',[])}
    pair_ids={file['pair_id'] for file in selected if file['pair_id']}
    bad=any(not file['input_available'] or file['integrity_state']=='failed' for file in selected) or any(pairs.get(key,{}).get('state')=='failed' for key in pair_ids)
    measured=scan.get('state')=='completed' and all(file['integrity_state']=='passed' and file['sha256'] and file['source_snapshot'] for file in selected) and all(pairs.get(key,{}).get('state')=='passed' for key in pair_ids)
    add('integrity','Full current source / mate integrity','fail' if bad else 'pass' if measured else 'not_evaluated',
        'Every selected source requires a full current checksum and structural validation; confirmed mates require matching counts and identifier order. A cancelled or interrupted task cannot establish a complete release.',file_ids=[file['file_id'] for file in selected])
    expected=(data.get('expected_manifest') or {}).get('files')
    reconciliation=reconcile(selected,scoped_expected(data['files'],selected,expected))
    add('expected_delivery','Independent expected delivery','pass' if reconciliation['status']=='matched' else 'fail' if reconciliation['status']=='review_required' else 'not_evaluated',
        'Exact expected-file identities and supplied counts/checksums, scoped to selected groups. Missing expectations with unknown scope remain visible.',evidence=reconciliation)
    quantities=[row for row in data['yields'] if row['sample_id'] in sample_ids]
    state='fail' if any(row['target_state']=='below_target' for row in quantities) else 'pass' if quantities and all(row['target_state']=='met' for row in quantities) else 'not_evaluated'
    add('quantity','Explicit per-sample quantity contract',state,'Uses saved user-defined read / synchronized-pair / base minima. Quality does not substitute for yield.',evidence=[{'sample_id':row['sample_id'],'target':row['target'],'observed':row['observed'],'state':row['target_state'],'provenance':row['provenance']} for row in quantities])
    demux=data.get('demultiplex') or {}
    mapped_ids={entry['file_id'] for entry in demux.get('file_mappings',[]) if entry['state']=='matched'}
    demux_state='fail' if demux.get('reconciliation_state')=='review_required' else 'pass' if demux.get('state')=='available' and demux.get('reconciliation_state')=='matched' and all(file['file_id'] in mapped_ids for file in selected) else 'not_evaluated'
    add('demultiplex','Supported SampleSheet / demultiplex reconciliation',demux_state,'Requires supported SampleSheet/demultiplex reconciliation and an explicit unique FASTQ-list mapping for every selected file. CSVs may not report the tool version; biological identity, contamination and sample swaps are not inferred.',source_state=demux.get('state','not_evaluated'))
    samples={sample['id']:sample for sample in metrics.get('samples',[])}
    classifications=[]
    for file in selected:
        for module in samples.get(file['report_id'],{}).get('modules',[]):
            classifications.append({'file_id':file['file_id'],'module':module['name'],'status':module['status'],'qc_snapshot_matches':file['qc_snapshot_matches']})
    add('fastqc_information','Official FastQC classifications (informational)','warning' if any(row['status'] in {'warn','fail'} for row in classifications) else 'pass' if classifications else 'not_evaluated',
        'Module-specific WARN/FAIL does not automatically reject a sample; protocol context and the explicit assay policy govern review.',evidence=classifications)
    checks[-1]['mandatory']=False
    add('screening_information','Offline contamination screening','not_evaluated','No screening tool/database was run. FastQC overrepresented sequences do not establish contamination or sample identity.')
    checks[-1]['mandatory']=False
    for rule in definition.get('fastqc_rules',[]) if definition else []:
        states=[next((module['status'] for module in samples.get(file['report_id'],{}).get('modules',[]) if module['name']==rule['module'] and module.get('available') is not False),None) if file['qc_snapshot_matches'] is True else None for file in selected]
        state='not_evaluated' if any(status not in STATUSES for status in states) else 'pass' if all(status in rule['allowed_statuses'] for status in states) else 'fail'
        add('fastqc:'+rule['module'],'Policy: '+rule['module'],state,'Explicit permitted original statuses: '+', '.join(rule['allowed_statuses']),source_statuses=[{'file_id':file['file_id'],'status':status} for file,status in zip(selected,states)])
    fingerprint=digest({'analysis_id':run['id'],'name':run['name'],'sample_ids':sorted(sample_ids),'policy':policy,'delivery_revision':run.get('delivery_revision',0),
                        'integrity_task':scan.get('task_id'),'files':selected,'checks':checks,'source_fingerprint':source_fingerprint})
    events=run.get('release_reviews',[])
    active=[event for event in events if event['fingerprint']==fingerprint]
    waivers={event['rule_id']:event for event in active if event['action']=='waive'}
    for check in checks:
        if check['id']!='integrity' and check['id'] in waivers and check['state']!='pass':check['waiver']=waivers[check['id']]
    readiness='review_required' if not policy else 'blocked' if any(check['mandatory'] and check['state']!='pass' and not check.get('waiver') for check in checks) else 'ready'
    decisions=[event for event in active if event['action']!='waive'];decision=decisions[-1] if decisions else None
    historical=[event for event in events if event['action']!='waive']
    review_state={'approve':'approved','needs_review':'review_required','block':'blocked'}[decision['action']] if decision else 'stale' if historical else 'pending'
    if review_state=='approved' and readiness!='ready':review_state='stale'
    return {'schema_version':1,'analysis_id':run['id'],'sample_ids':sorted(sample_ids),'file_ids':[file['file_id'] for file in selected],
            'fingerprint':fingerprint,'policy':policy,'readiness':readiness,'review_state':review_state,'checks':checks,'decision':decision,
            'active_waivers':list(waivers.values()),'history':events,'files':selected}
