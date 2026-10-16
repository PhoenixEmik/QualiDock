"""Genuine Kraken2 execution, official simulated reads and public experimental RNA-seq."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from qualidock.screening import parse_report
from test_workspace import wait

ROOT=(Path(__file__).parent/'fixtures/screening').resolve()
KRAKEN=shutil.which(os.environ.get('QUALIDOCK_KRAKEN2','kraken2'))
FASTQC=shutil.which(os.environ.get('QUALIDOCK_FASTQC','fastqc'))
DB=os.environ.get('QUALIDOCK_SCREENING_TEST_DB')
if os.environ.get('QUALIDOCK_REQUIRE_SCREENING_TESTS')=='1' and not (KRAKEN and FASTQC and DB):raise RuntimeError('CI requires actual Kraken2, FastQC and the pinned offline test database')
pytestmark=pytest.mark.skipif(not (KRAKEN and FASTQC and DB),reason='Explicit offline screening tools/test reference are required')


def settings(tmp_path):
 proof=json.loads((Path(DB)/'qualidock-fixture-provenance.json').read_text())
 return Settings(roots=[ROOT,tmp_path.resolve()],output=tmp_path/'runs',frontend=tmp_path/'frontend',token='screening-real-only',fastqc=FASTQC,kraken2=KRAKEN,
                 multiqc='/unused/multiqc',screening_databases=[proof['database']],cpus=1,memory_mb=2048,allow_root=True)


def finish(client,base):
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  value=client.get(base).json()['screening']
  if value['state'] not in {'queued','running'}:return value
  time.sleep(.02)
 raise AssertionError(value)


def analysis(client,paths):
 response=client.post('/api/runs',json={'mode':'fastqc','paths':list(map(str,paths))})
 assert response.status_code==201,response.text
 run=wait(client,response.json()['id']);assert run['state']=='completed',run
 return run,f"/api/runs/{run['id']}"


def test_real_offline_tool_counts_reference_hashes_exact_reports_and_restart(tmp_path):
 config=settings(tmp_path);headers={'Authorization':f'Bearer {config.token}','X-QualiDock-Request':'1'}
 sources=[ROOT/'sim_1.fq',ROOT/'SRR6357070_first100_R1.fastq.gz',ROOT/'SRR6357070_first100_R2.fastq.gz']
 before={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
 with TestClient(create_app(config),headers=headers) as client:
  detected=client.get('/api/screening').json();assert detected['tool']['compatible'] and detected['tool']['version']=='2.17.1'
  run,base=analysis(client,sources);metrics=client.get(base+'/metrics').content;executions=run['executions']
  inventory=client.get(base+'/delivery').json();ids=[file['file_id'] for file in inventory['files']]
  response=client.post(base+'/screening',json={'file_ids':ids,'database_id':'official-viral-test','assay':'Yeast RNA-seq / official simulated viral fixture; reference coverage is limited','expected_taxids':['4932'],'threads':1})
  assert response.status_code==202,response.text
  record=finish(client,base);assert record['state']=='completed',record
  assert record['parameters']['paired'] is False and record['parameters']['memory_mapping'] is True and record['parameters']['subsampling'] is False
  assert all(file['coverage']=='full' and file['screened_fraction']==1 for file in record['files'])
  assert sorted(file['records_processed'] for file in record['files'])==[100,100,440]
  assert len(record['database_files'])==3 and '4932' not in record['database']['reference_taxids']
  for item in record['database_files']:
   assert item['sha256']==hashlib.sha256((Path(DB)/item['name']).read_bytes()).hexdigest()
  for file in record['files']:
   raw=client.get(base+'/download',params={'path':file['report_artifact']});assert raw.status_code==200
   normalized=client.get(base+'/screening-metrics',params={'file_id':file['id']});assert normalized.status_code==200
   assert normalized.json()['records_processed']==file['records_processed']
   assert normalized.json()['source_analysis_id']==run['id'] and normalized.json()['source_task_id']==record['task_id']
   direct=tmp_path/(file['id']+'.direct.tsv')
   source=Path(file['path']);compressed=source.suffix=='.gz'
   subprocess.run([KRAKEN,'--db',DB,'--threads','1','--memory-mapping','--confidence','0','--minimum-hit-groups','2','--report',str(direct),'--output','/dev/null',*(['--gzip-compressed'] if compressed else []),'--',str(source)],check=True,capture_output=True)
   assert raw.content==direct.read_bytes() # Independently executed official output, not fabricated expectations.
  assert client.get(base+'/metrics').content==metrics and client.get(base).json()['executions']==executions
  exported=client.get(base+'/delivery-manifest').json()
  assert exported['offline_screening']['tool_version']=='2.17.1'
  assert str(Path(DB)) not in json.dumps(exported) and str(ROOT) not in json.dumps(exported)
  assert client.get(base+'/screening-metrics',params={'file_id':'../../etc/passwd'}).status_code==404
  client.headers.pop('Authorization')
  assert client.get(base+'/screening-metrics',params={'file_id':ids[0]}).status_code==401
 with TestClient(create_app(config),headers=headers) as client:
  saved=client.get(base).json()['screening'];assert saved==record
  assert client.get(base+'/screening-metrics',params={'file_id':ids[0]}).status_code==200
  sources[0].stat() # Historical results are read, not rerun.
 assert before=={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}


def test_real_gzip_paths_with_shell_characters_partial_failure_and_cancellation(tmp_path):
 config=settings(tmp_path);headers={'Authorization':f'Bearer {config.token}','X-QualiDock-Request':'1'}
 source=tmp_path/'reads $(touch exploited); specimen.fastq.gz';shutil.copyfile(ROOT/'SRR6357070_first100_R1.fastq.gz',source)
 other=tmp_path/'other.fastq.gz';shutil.copyfile(source,other)
 with TestClient(create_app(config),headers=headers) as client:
  run,base=analysis(client,[source,other]);files=client.get(base+'/delivery').json()['files'];ids=[file['file_id'] for file in files]
  other.unlink()
  response=client.post(base+'/screening',json={'file_ids':ids,'database_id':'official-viral-test'})
  assert response.status_code==202,response.text
  record=finish(client,base);assert record['state']=='partial',record
  assert {file['state'] for file in record['files']}=={'completed','failed'}
  assert next(file for file in record['files'] if file['state']=='completed')['records_processed']==100
  assert not list((config.output/run['id']).rglob('exploited'))
  manager=client.app.state.manager;client.portal.call(manager.slot.acquire)
  try:
   assert client.post(base+'/screening',json={'file_ids':ids,'database_id':'official-viral-test'}).status_code==202
   cancelled=client.post(base+'/screening/cancel').json();assert cancelled['state']=='cancelled'
  finally:client.portal.call(manager.slot.release)
  deadline=time.monotonic()+5
  while run['id'] in manager.screening.tasks and time.monotonic()<deadline:time.sleep(.01)
  response=client.post(base+'/screening',json={'file_ids':ids,'database_id':'official-viral-test'})
  assert response.status_code==202,response.text
  task_id=response.json()['task_id'];deadline=time.monotonic()+5
  while task_id not in manager.executor.processes and time.monotonic()<deadline:time.sleep(.002)
  assert task_id in manager.executor.processes,'The real internal worker must start before running-cancellation acceptance'
  assert client.post(base+'/screening/cancel').json()['state']=='cancelled'
  deadline=time.monotonic()+5
  while run['id'] in manager.screening.tasks and time.monotonic()<deadline:time.sleep(.01)
  assert task_id not in manager.executor.processes
  assert client.get(base).json()['state']=='completed'


def test_real_detection_revalidation_allocation_guard_and_interrupted_history(tmp_path):
 config=settings(tmp_path);headers={'Authorization':f'Bearer {config.token}','X-QualiDock-Request':'1'}
 with TestClient(create_app(config),headers=headers) as client:
  run,base=analysis(client,[ROOT/'SRR6357070_first100_R1.fastq.gz'])
  ids=[entry['file_id'] for entry in client.get(base+'/delivery').json()['files']]
  request={'file_ids':ids,'database_id':'official-viral-test'}
  assert client.post(base+'/screening',json={**request,'threads':2}).status_code==400 # Actual 1-CPU configuration.
  assert client.post(base+'/screening',json={**request,'database_id':'../../arbitrary'}).status_code==400
  assert client.post(base+'/screening',json=request).status_code==202
  record=finish(client,base);assert record['state']=='completed',record
  assert record['execution']['exit_code']==0 and record['execution']['resources']['elapsed_seconds']>0
  # Enabling an explicit screening rule still requires source-integrity evidence;
  # a taxonomic classification is not a release approval or contamination verdict.
  assert client.post(base+'/release-policy',json={'version':'explicit-screening','assay':'RNA-seq fixture','required_checks':['integrity','screening']}).status_code==200
  groups=[row['sample_id'] for row in client.get(base+'/delivery').json()['yields']]
  review=client.post(base+'/release-review/evaluate',json={'sample_ids':groups}).json()
  assert next(check for check in review['checks'] if check['id']=='screening')['state']=='pass'
  assert review['readiness']=='blocked' and review['review_state']=='pending'
 path=config.output/run['id']/'manifest.json';saved=json.loads(path.read_text());saved['screening']['state']='running';path.write_text(json.dumps(saved))
 with TestClient(create_app(config),headers=headers) as client:
  saved=client.get(base).json()
  assert saved['state']=='completed' and saved['screening']['state']=='interrupted'
  assert client.get(base+'/screening-metrics',params={'file_id':ids[0]}).status_code==200
