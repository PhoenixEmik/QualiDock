"""Real internal streaming worker through LocalExecutor, with fixture QC as context."""
import time
from fastapi.testclient import TestClient
from qualidock.app import create_app
from test_workspace import start, wait


def finish(client,run_id):
 deadline=time.monotonic()+15
 while time.monotonic()<deadline:
  record=client.get(f'/api/runs/{run_id}').json()['integrity']
  if record['state'] not in {'queued','running'}:return record
  time.sleep(.02)
 raise AssertionError(record)


def test_validation_task_is_persistent_readonly_and_preserves_qc_state(setup):
 settings,root=setup;headers={'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'}
 before={p:p.read_bytes() for p in root.glob('*.fastq')}
 with TestClient(create_app(settings),headers=headers) as client:
  run=wait(client,start(client,root,mode='fastqc')['id'])
  executions=run['executions']
  response=client.post(f"/api/runs/{run['id']}/integrity",json={'mode':'full'})
  assert response.status_code==202,response.text
  record=finish(client,run['id'])
  assert record['state']=='completed' and record['result']=='passed',record
  assert len(record['files'])==2 and record['pairs'][0]['state']=='passed'
  assert all(r['records_scanned']==1 and r['sha256'] for r in record['files'])
  assert record['requested_by']['unix_user'] and record['version']=='1.0'
  assert client.get(f"/api/runs/{run['id']}/download",params={'path':record['artifact']}).status_code==200
  saved=client.get(f"/api/runs/{run['id']}").json()
  assert saved['state']=='completed' and saved['executions']==executions
 with TestClient(create_app(settings),headers=headers) as client:
  assert client.get(f"/api/runs/{run['id']}").json()['integrity']==record
 assert before=={p:p.read_bytes() for p in before}


def test_changed_original_and_missing_mate_fail_without_false_complete(client,setup):
 _,root=setup
 run=wait(client,start(client,root,mode='fastqc')['id'])
 original=root/'sample_R2_001.fastq';original.unlink()
 assert client.post(f"/api/runs/{run['id']}/integrity",json={'mode':'full'}).status_code==202
 record=finish(client,run['id'])
 assert record['state']=='completed' and record['result']=='failed'
 assert any(r['state']=='failed' for r in record['files'])
 assert record['pairs'][0]['state']=='failed'


def test_validation_cancel_is_not_completed_and_old_attempt_is_retained(client,setup):
 _,root=setup
 run=wait(client,start(client,root,mode='fastqc')['id'])
 # Force the shared resource slot to queue the integrity task deterministically.
 manager=client.app.state.manager
 import anyio
 client.portal.call(manager.slot.acquire)
 try:
  response=client.post(f"/api/runs/{run['id']}/integrity",json={'mode':'full'})
  assert response.status_code==202
  first=response.json()
  cancelled=client.post(f"/api/runs/{run['id']}/integrity/cancel").json()
  assert cancelled['state']=='cancelled' and cancelled['result']=='not_evaluated'
 finally:client.portal.call(manager.slot.release)
 deadline=time.monotonic()+5
 while run['id'] in manager.validation.tasks and time.monotonic()<deadline:time.sleep(.01)
 assert client.post(f"/api/runs/{run['id']}/integrity",json={'mode':'quick'}).status_code==202
 record=finish(client,run['id'])
 assert record['state']=='completed' and record['task_id']!=first['task_id']
 assert client.get(f"/api/runs/{run['id']}").json()['integrity_history'][0]['state']=='cancelled'


def test_imported_reports_cannot_claim_source_fastq_integrity(client,setup):
 settings,root=setup
 run=wait(client,start(client,root,mode='fastqc')['id'])
 imported=client.post(f"/api/runs/{run['id']}/multiqc")
 # Provenanced aggregation can scan its original reads.
 assert imported.status_code==201
 imported=wait(client,imported.json()['id'])
 assert client.post(f"/api/runs/{imported['id']}/integrity",json={'mode':'full'}).status_code==202
 assert finish(client,imported['id'])['result']=='passed'


def test_unprovenanced_import_has_no_source_integrity_and_restart_interrupts_scan(setup):
 import json,shutil
 settings,root=setup;headers={'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'}
 with TestClient(create_app(settings),headers=headers) as client:
  run=wait(client,start(client,root,mode='fastqc')['id'])
  archive=next((settings.output/run['id']/'fastqc').glob('*.zip'))
  imported_zip=root/'existing_fastqc.zip';shutil.copyfile(archive,imported_zip)
  imported=client.post('/api/runs',json={'mode':'multiqc','paths':[str(imported_zip)]})
  imported=wait(client,imported.json()['id'])
  response=client.post(f"/api/runs/{imported['id']}/integrity",json={'mode':'full'})
  assert response.status_code==400 and 'absent source FASTQs' in response.text
 path=settings.output/run['id']/'manifest.json';manifest=json.loads(path.read_text())
 manifest['integrity']={'state':'running','result':'not_evaluated','files':[],'pairs':[],'task_id':'old-worker','current_file':{'state':'running'}}
 path.write_text(json.dumps(manifest))
 with TestClient(create_app(settings),headers=headers) as client:
  restored=client.get(f"/api/runs/{run['id']}").json()
  assert restored['state']=='completed'
  assert restored['integrity']['state']=='interrupted'
  assert restored['integrity']['current_file']['state']=='not_evaluated'
