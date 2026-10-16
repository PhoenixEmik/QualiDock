"""Actual internal worker ZIP validation, source checksums and cancellation."""
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile
import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.release_worker import safe_name
from test_release_review import prepare,evaluation,action,scope,POLICY
from test_workspace import start,wait


def exported(client,base):
 deadline=time.monotonic()+15
 while time.monotonic()<deadline:
  value=client.get(base).json()['release_export']
  if value['state'] not in {'queued','running'}:return value
  time.sleep(.02)
 raise AssertionError(value)


def launch(client,base,ids,**options):
 value=evaluation(client,base,ids)
 return client.post(base+'/release-exports',json={'sample_ids':ids,'fingerprint':value['fingerprint'],**options})


def test_approved_reproducible_reference_zip_checksums_original_reports_and_restart(setup):
 settings,root=setup;headers={'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'}
 before={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in root.glob('*.fastq')}
 with TestClient(create_app(settings),headers=headers) as client:
  run,base,ids=prepare(client,root);value=evaluation(client,base,ids)
  assert action(client,base,value).status_code==200
  assert launch(client,base,ids,include_reports=True).status_code==400
  hashes=[];records=[]
  for _ in range(2):
   response=launch(client,base,ids,include_reports=True,acknowledge_report_paths=True)
   assert response.status_code==202,response.text
   record=exported(client,base);assert record['state']=='completed',record
   body=client.get(base+'/download',params={'path':record['artifact']}).content
   hashes.append(hashlib.sha256(body).hexdigest());records.append(record)
   assert record['release_status']=='approved' and hashes[-1]==record['sha256']
   with zipfile.ZipFile(io.BytesIO(body)) as archive:
    names=archive.namelist();assert all(not name.startswith('/') and '..' not in Path(name).parts for name in names)
    manifest=json.loads(archive.read('manifest.json'));review=json.loads(archive.read('release-review.json'))
    assert manifest['release_status']=='approved' and review['review_state']=='approved'
    provenance=json.loads(archive.read('provenance.json'))
    assert provenance['qc_executions'][0]['tool']=='fastqc' and provenance['qc_executions'][0]['exit_code']==0
    assert provenance['integrity_execution']['exit_code']==0 and provenance['exporter']['python']
    assert str(root) not in archive.read('manifest.json').decode() and str(root) not in archive.read('release-review.json').decode()
    assert manifest['yields'][0]['totals']['read_pairs']==1
    for line in archive.read('checksums.sha256').decode().splitlines():
     sha,name=line.split('  ',1)
     if name in names:assert hashlib.sha256(archive.read(name)).hexdigest()==sha
     else:
      source=next(file for file in manifest['files'] if file['input_reference']==name)
      original=next(path for path in before if path.name==source['filename'])
      assert before[original]==sha and name not in names
    for report in manifest['report_artifacts']:
     original=client.get(base+'/download',params={'path':report['source_artifact']}).content
     assert archive.read(report['path'])==original
  assert hashes[0]==hashes[1] # Identical scientific/review snapshot, deterministic ZIP metadata.
 with TestClient(create_app(settings),headers=headers) as client:
  assert client.get(base+'/download',params={'path':records[0]['artifact']}).status_code==200
 assert before=={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in before}


def test_pending_review_is_labeled_and_incomplete_hash_cannot_produce_a_bundle(client,setup):
 _,root=setup;run=wait(client,start(client,root)['id']);base=f"/api/runs/{run['id']}";ids=scope(client,base)
 assert launch(client,base,ids).status_code==400
 run,base,ids=prepare(client,root)
 response=launch(client,base,ids);assert response.status_code==202,response.text
 record=exported(client,base);assert record['state']=='completed' and record['release_status']=='review_required'
 archive=zipfile.ZipFile(io.BytesIO(client.get(base+'/download',params={'path':record['artifact']}).content))
 assert not any(name.startswith('reports/') for name in archive.namelist())
 assert 'review_required' in archive.read('README.md').decode()


def test_cancelled_export_and_restart_never_register_partial_or_orphan_zip(client,setup):
 settings,root=setup;run,base,ids=prepare(client,root);manager=client.app.state.manager
 client.portal.call(manager.slot.acquire)
 try:
  assert launch(client,base,ids).status_code==202
  assert client.post(base+'/release-policy',json=POLICY).status_code==400
  assert client.post(base+'/integrity',json={'mode':'full'}).status_code==400
  record=client.post(base+'/release-exports/cancel').json()
  assert record['state']=='cancelled' and record['artifact'] is None
 finally:client.portal.call(manager.slot.release)
 deadline=time.monotonic()+5
 while run['id'] in manager.exports.tasks and time.monotonic()<deadline:time.sleep(.01)
 orphan=settings.output/run['id']/'release-exports'/'orphan';orphan.mkdir();(orphan/'bundle.zip').write_bytes(b'not a complete release')
 manager.refresh_reports(manager.runs[run['id']])
 assert all(report['path']!='release-exports/orphan/bundle.zip' for report in manager.runs[run['id']]['reports'])
 assert client.get(base+'/download',params={'path':'release-exports/orphan/bundle.zip'}).status_code==403


def test_archive_names_and_untrusted_labels_do_not_create_html_or_path_injection(client,setup):
 for value in ['../escape','/absolute','a/../../b','a\\b','a\nname']:
  with pytest.raises(ValueError):safe_name(value)
 _,root=setup;run,base,ids=prepare(client,root)
 assert action(client,base,evaluation(client,base,ids),'needs_review','<script>alert(1)</script>').status_code==200
 assert launch(client,base,ids).status_code==202
 record=exported(client,base);assert record['state']=='completed',record
 archive=zipfile.ZipFile(io.BytesIO(client.get(base+'/download',params={'path':record['artifact']}).content))
 report=archive.read('release-report.html').decode()
 assert '<script>alert(1)</script>' not in report and '&lt;script&gt;alert(1)&lt;/script&gt;' in report


def test_restart_interrupts_uncommitted_export_and_rejects_unauthenticated_access(setup):
 settings,root=setup;headers={'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'}
 with TestClient(create_app(settings),headers=headers) as client:
  run,base,ids=prepare(client,root)
  client.headers.pop('Authorization')
  assert client.post(base+'/release-exports',json={'sample_ids':ids,'fingerprint':'0'*64}).status_code==401
 path=settings.output/run['id']/'manifest.json';record=json.loads(path.read_text())
 record['release_export']={'task_id':'crashed','state':'running','release_status':'approved','artifact':None}
 path.write_text(json.dumps(record))
 with TestClient(create_app(settings),headers=headers) as client:
  restored=client.get(base).json()
  assert restored['release_export']['state']=='interrupted' and restored['release_export']['artifact'] is None


def test_worker_streams_report_chunks_and_rejects_symlink_sources(tmp_path,monkeypatch):
 from qualidock import release_worker as worker
 from qualidock.integrity import snapshot
 root=tmp_path.resolve();source=root/'synthetic-load.log'
 # Clearly synthetic load bytes, not a substitute for QC scientific data.
 source.write_bytes(b'streaming-load-test\n'*250000)
 entry={'source':str(source),'source_artifact':source.name,'snapshot':snapshot(source.stat()),'archive_path':'reports/test/source.log'}
 native=worker.source_file;reads=[]
 class Guarded:
  def __init__(self,stream):self.stream=stream
  def __enter__(self):return self
  def __exit__(self,*args):self.stream.close()
  def fileno(self):return self.stream.fileno()
  def read(self,size):
   assert 0<size<=1024*1024;reads.append(size);return self.stream.read(size)
 monkeypatch.setattr(worker,'source_file',lambda item,base:Guarded(native(item,base)))
 payload={'manifest':{'files':[]},'csv':'synthetic load metadata\n','qc_metrics':{'synthetic_load_test':True},'provenance':{},'review':{},'release_status':'review_required','readme':'Synthetic streaming-load fixture only'}
 output=root/'test.zip.pending'
 result=worker.build({'artifact_root':str(root),'source_files':[],'artifacts':[entry],'payload':payload},output)
 assert len(reads)>=5 and result['sha256']==hashlib.sha256(output.read_bytes()).hexdigest()
 with zipfile.ZipFile(output) as archive:assert archive.read(entry['archive_path'])==source.read_bytes()
 link=root/'link.log';link.symlink_to(source)
 with pytest.raises(ValueError):native({**entry,'source':str(link)},root)
 for value in ['a/./b','a//b','C:/escape','reports/file:stream']:
  with pytest.raises(ValueError):safe_name(value)


def test_actual_running_export_can_be_cancelled_without_registered_bundle(client,setup):
 _,root=setup;run,base,ids=prepare(client,root);manager=client.app.state.manager
 response=launch(client,base,ids);assert response.status_code==202,response.text
 task_id=response.json()['task_id'];deadline=time.monotonic()+5
 while task_id not in manager.executor.processes and time.monotonic()<deadline:time.sleep(.002)
 assert task_id in manager.executor.processes,'Internal worker must actually start for running cancellation acceptance'
 response=client.post(base+'/release-exports/cancel');assert response.status_code==200
 assert response.json()['state']=='cancelled'
 deadline=time.monotonic()+5
 while run['id'] in manager.exports.tasks and time.monotonic()<deadline:time.sleep(.01)
 assert task_id not in manager.executor.processes
 saved=client.get(base).json()
 assert saved['release_export']['artifact'] is None
 assert not any(report['path'].startswith('release-exports/') and report['path'].endswith('.zip') for report in saved['reports'])


def test_changed_queued_evidence_and_insufficient_space_withhold_export(client,setup,monkeypatch):
 from types import SimpleNamespace
 from qualidock import release_exports
 _,root=setup;run,base,ids=prepare(client,root);manager=client.app.state.manager
 with monkeypatch.context() as patch:
  patch.setattr(release_exports.shutil,'disk_usage',lambda path:SimpleNamespace(free=0))
  assert launch(client,base,ids).status_code==400
 client.portal.call(manager.slot.acquire)
 try:
  assert launch(client,base,ids).status_code==202
  with (root/'sample_R1_001.fastq').open('a') as stream:stream.write('@changed\nACGT\n+\nIIII\n')
 finally:client.portal.call(manager.slot.release)
 record=exported(client,base)
 assert record['state']=='failed' and record['artifact'] is None
 assert 'changed' in record['error'].lower()
