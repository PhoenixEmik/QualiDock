"""Delivery API persistence and authorization; synthetic executors are test-only."""
import csv
import io
import json
from fastapi.testclient import TestClient
from qualidock.app import create_app
from test_workspace import start,wait
from test_validation_jobs import finish


def test_expected_manifest_target_export_and_restart(setup):
 settings,root=setup;headers={'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'}
 originals={path:path.read_bytes() for path in root.glob('*.fastq')}
 with TestClient(create_app(settings),headers=headers) as client:
  run=wait(client,start(client,root,mode='fastqc')['id']);base=f"/api/runs/{run['id']}"
  before=client.get(base+'/delivery').json();sample=before['files'][0]['sample_id']
  assert all(file['reads']==1000 and file['bases']==150000 for file in before['files']) # test executor's explicit fixed-length result
  assert before['reconciliation']['status']=='not_evaluated' and before['yields'][0]['totals']['q30_percent'] is None
  template=client.get(base+'/expected-template').json()
  assert set(template['files'][0])=={'file_id','filename'}
  response=client.post(base+'/expected-delivery',json={'format':'json','content':json.dumps(template)})
  assert response.status_code==200 and response.json()['updated_by']['unix_user']
  assert client.post(base+'/yield-targets',json={'assay':'Example assay, explicit contract','input_stage':'upstream_processed','processing_notes':'No processing performed by QualiDock','targets':[{'sample_id':sample,'metric':'read_pairs','minimum':2}]}).status_code==200
  assert client.get(base+'/delivery').json()['yields'][0]['target_state']=='not_evaluated'
  assert client.post(base+'/integrity',json={'mode':'full'}).status_code==202
  assert finish(client,run['id'])['result']=='passed'
  after=client.get(base+'/delivery').json();yielded=after['yields'][0]
  assert yielded['totals']['reads']==2 and yielded['totals']['read_pairs']==1 and yielded['totals']['bases']==8
  assert yielded['target_state']=='below_target' and yielded['totals']['q30_percent']==100
  assert after['reconciliation']['status']=='matched'
  exported=client.get(base+'/delivery-manifest').json()
  assert str(root) not in json.dumps(exported)
  assert exported['yields'][0]['totals']==yielded['totals']
  assert client.get(base+'/delivery-manifest',params={'include_paths':True}).json()['files'][0]['path'].startswith(str(root))
  rows=list(csv.DictReader(io.StringIO(client.get(base+'/delivery-manifest',params={'format':'csv','mode':'verbatim'}).text)))
  assert rows[0]['reads']=='1' and len(rows[0]['sha256'])==64
  previous=client.get(base).json();reports={report['path']:client.get(base+'/download',params={'path':report['path']}).content for report in previous['reports'] if report['path'].endswith(('.html','.zip'))}
 with TestClient(create_app(settings),headers=headers) as client:
  restored=client.get(base+'/delivery').json()
  assert restored['targets']==after['targets'] and restored['expected_manifest']==after['expected_manifest']
  assert restored['yields']==after['yields']
  assert all(client.get(base+'/download',params={'path':path}).content==body for path,body in reports.items())
  (root/'sample_R2_001.fastq').unlink()
  missing=client.get(base+'/delivery').json()
  assert missing['reconciliation']['missing'] and missing['yields'][0]['target_state']=='not_evaluated'
 assert all(path.read_bytes()==body for path,body in originals.items() if path.exists())


def test_expected_input_is_bounded_text_not_a_filesystem_reader_and_targets_are_strict(client,setup):
 _,root=setup;run=wait(client,start(client,root)['id']);base=f"/api/runs/{run['id']}"
 sample=client.get(base+'/delivery').json()['files'][0]['sample_id']
 # Arbitrary paths are inert expected identities, never opened by reconciliation.
 assert client.post(base+'/expected-delivery',json={'format':'csv','content':'path\n/etc/passwd\n../../secret\n'}).status_code==200
 assert len(client.get(base+'/delivery').json()['reconciliation']['missing'])==2
 for target in [{'sample_id':'unknown','metric':'reads','minimum':1},{'sample_id':sample,'metric':'reads','minimum':True},{'sample_id':sample,'metric':'reads','minimum':1.5},{'sample_id':sample,'metric':'reads','minimum':2**53},{'sample_id':sample,'metric':'Q30','minimum':1}]:
  assert client.post(base+'/yield-targets',json={'targets':[target]}).status_code in {400,422}
 assert client.post(base+'/expected-delivery',json={'format':'csv','content':'filename,unknown\nx,y'}).status_code==400
 client.headers.pop('Authorization')
 assert client.get(base+'/delivery').status_code==401
 assert client.get(base+'/delivery-manifest').status_code==401
 assert client.post(base+'/expected-delivery',json={'format':'json','content':'[]'}).status_code==401
