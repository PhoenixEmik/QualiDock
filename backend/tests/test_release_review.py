"""Explicit release policy and Unix-identity audit; no universal QC thresholds."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from qualidock.app import create_app
from test_workspace import start,wait
from test_validation_jobs import finish

POLICY={'version':'assay-contract-1','assay':'Explicit fixture contract','required_checks':['integrity','expected_delivery','quantity'],'fastqc_rules':[]}


def scope(client,base):return [row['sample_id'] for row in client.get(base+'/delivery').json()['yields']]
def evaluation(client,base,ids):
 response=client.post(base+'/release-review/evaluate',json={'sample_ids':ids})
 assert response.status_code==200,response.text
 return response.json()
def action(client,base,value,action='approve',reason='Fixture evidence reviewed',rule_id=None):
 return client.post(base+'/release-review',json={'sample_ids':value['sample_ids'],'fingerprint':value['fingerprint'],'action':action,'reason':reason,'rule_id':rule_id})


def prepare(client,root):
 run=wait(client,start(client,root,mode='fastqc')['id']);base=f"/api/runs/{run['id']}";ids=scope(client,base)
 assert client.post(base+'/integrity',json={'mode':'full'}).status_code==202
 assert finish(client,run['id'])['result']=='passed'
 files=client.get(base+'/delivery').json()['files']
 expected=[{'file_id':file['file_id'],'expected_reads':1,'sha256':file['sha256']} for file in files]
 assert client.post(base+'/expected-delivery',json={'format':'json','content':json.dumps(expected)}).status_code==200
 assert client.post(base+'/yield-targets',json={'assay':'Fixture','input_stage':'unknown','targets':[{'sample_id':ids[0],'metric':'read_pairs','minimum':1}]}).status_code==200
 assert client.post(base+'/release-policy',json=POLICY).status_code==200
 return run,base,ids


def test_missing_policy_and_required_evidence_never_approve_and_integrity_cannot_be_waived(client,setup):
 _,root=setup;run=wait(client,start(client,root)['id']);base=f"/api/runs/{run['id']}";ids=scope(client,base)
 before=evaluation(client,base,ids)
 assert before['readiness']=='review_required' and before['review_state']=='pending'
 assert action(client,base,before).status_code==400
 assert client.post(base+'/release-policy',json=POLICY).status_code==200
 value=evaluation(client,base,ids)
 assert value['readiness']=='blocked'
 assert all(check['state']=='not_evaluated' for check in value['checks'] if check['id'] in {'integrity','expected_delivery','quantity'})
 assert action(client,base,value,'waive',rule_id='integrity').status_code==400
 assert action(client,base,value,reason=' ').status_code==400


def test_informational_fastqc_warning_is_not_an_automatic_rejection_and_approval_is_persistent(setup):
 settings,root=setup;headers={'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'}
 with TestClient(create_app(settings),headers=headers) as client:
  run,base,ids=prepare(client,root);value=evaluation(client,base,ids)
  info=next(check for check in value['checks'] if check['id']=='fastqc_information')
  assert info['state']=='warning' and not info['mandatory']
  assert value['readiness']=='ready' and value['review_state']=='pending'
  approved=action(client,base,value);assert approved.status_code==200,approved.text
  assert approved.json()['actor']['unix_user']
  saved=evaluation(client,base,ids)
  assert saved['fingerprint']==value['fingerprint'] and saved['review_state']=='approved'
 with TestClient(create_app(settings),headers=headers) as client:
  assert evaluation(client,base,ids)['review_state']=='approved'
  assert client.patch(base,json={'name':'Renamed contract'}).status_code==200
  assert evaluation(client,base,ids)['review_state']=='stale'
  assert action(client,base,value).status_code==409


def test_explicit_module_policy_requires_reasoned_waiver_and_configuration_changes_stale_it(client,setup):
 _,root=setup;run,base,ids=prepare(client,root)
 strict={**POLICY,'fastqc_rules':[{'module':'Per sequence GC content','allowed_statuses':['pass']}]}
 assert client.post(base+'/release-policy',json=strict).status_code==200
 value=evaluation(client,base,ids);rule='fastqc:Per sequence GC content'
 assert value['readiness']=='blocked'
 assert action(client,base,value,'waive','Protocol-specific GC distribution reviewed',rule).status_code==200
 waived=evaluation(client,base,ids)
 assert waived['readiness']=='ready' and waived['active_waivers'][0]['reason']
 assert action(client,base,waived).status_code==200
 # Re-saving even an identical version/definition advances its revision; A→B→A
 # must not accidentally revive an old approval or exception.
 assert client.post(base+'/release-policy',json=strict).status_code==200
 stale=evaluation(client,base,ids)
 assert stale['readiness']=='blocked' and stale['review_state']=='stale' and not stale['active_waivers']
 assert len(stale['history'])==2


def test_changed_metrics_inputs_and_targets_stale_previous_decision(client,setup):
 settings,root=setup;run,base,ids=prepare(client,root);value=evaluation(client,base,ids)
 assert action(client,base,value).status_code==200
 path=settings.output/run['id']/'metrics.json';metrics=json.loads(path.read_text());metrics['samples'][0]['modules'][0]['status']='warn';path.write_text(json.dumps(metrics))
 assert evaluation(client,base,ids)['review_state']=='stale'
 value=evaluation(client,base,ids);assert action(client,base,value).status_code==200
 assert client.post(base+'/yield-targets',json={'targets':[{'sample_id':ids[0],'metric':'read_pairs','minimum':2}]}).status_code==200
 value=evaluation(client,base,ids);assert value['readiness']=='blocked' and value['review_state']=='stale'
 (root/'sample_R2_001.fastq').unlink()
 assert next(check for check in evaluation(client,base,ids)['checks'] if check['id']=='integrity')['state']=='fail'


def test_subset_release_keeps_failed_other_groups_excluded_without_merging_metrics(client,setup):
 import shutil
 _,root=setup
 for read in [1,2]:shutil.copyfile(root/f'sample_R{read}_001.fastq',root/f'other_R{read}_001.fastq')
 run=wait(client,start(client,root,mode='fastqc')['id']);base=f"/api/runs/{run['id']}"
 (root/'other_R2_001.fastq').unlink()
 assert client.post(base+'/integrity',json={'mode':'full'}).status_code==202
 assert finish(client,run['id'])['result']=='failed'
 assert client.post(base+'/release-policy',json={**POLICY,'required_checks':['integrity']}).status_code==200
 data=client.get(base+'/delivery').json()
 good=next(file['sample_id'] for file in data['files'] if file['filename']=='sample_R1_001.fastq')
 value=evaluation(client,base,[good]);assert value['readiness']=='ready'
 assert action(client,base,value).status_code==200
 assert evaluation(client,base,[good])['review_state']=='approved'
 all_ids=scope(client,base);all_value=evaluation(client,base,all_ids)
 assert all_value['readiness']=='blocked' and all_value['review_state']=='stale'


def test_unavailable_module_and_unmapped_upstream_files_cannot_satisfy_required_checks(client,setup):
 import base64
 settings,root=setup;run,base,ids=prepare(client,root)
 policy={**POLICY,'required_checks':['integrity','demultiplex'],'fastqc_rules':[{'module':'Per base sequence quality','allowed_statuses':['pass','warn','fail']}]}
 assert client.post(base+'/release-policy',json=policy).status_code==200
 from test_demultiplex import documents
 assert client.post(base+'/demultiplex',json={'documents':[{'name':name,'content_base64':base64.b64encode(raw).decode()} for name,raw in documents().items()]}).status_code==200
 value=evaluation(client,base,ids)
 assert next(check for check in value['checks'] if check['id']=='demultiplex')['state']=='not_evaluated' # Genuine reports are not these FASTQs.
 path=settings.output/run['id']/'metrics.json';data=json.loads(path.read_text())
 data['samples'][0]['modules'][1]['available']=False;path.write_text(json.dumps(data))
 value=evaluation(client,base,ids)
 assert next(check for check in value['checks'] if check['id']=='fastqc:Per base sequence quality')['state']=='not_evaluated'
 assert value['readiness']=='blocked'
