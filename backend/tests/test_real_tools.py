"""Scientific integration acceptance uses actual installed tools, never fixtures as executables."""
import hashlib
from pathlib import Path
import os
import shutil
import time

import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from qualidock.metrics import parse_report
from qualidock.preview import MEMORY_STORAGE_BOOTSTRAP
from test_workspace import wait

INPUTS = Path(__file__).parent / 'fixtures/fastqc-0.13.0'
FASTQC = shutil.which(os.environ.get('QUALIDOCK_FASTQC', 'fastqc'))
MULTIQC = shutil.which(os.environ.get('QUALIDOCK_MULTIQC', 'multiqc'))


def real_settings(tmp_path):
    return Settings(roots=[INPUTS.resolve()], output=tmp_path / 'results', frontend=tmp_path / 'frontend', token='real-tool-test-only', cpus=1, memory_mb=4096, fastqc=FASTQC or 'fastqc', multiqc=MULTIQC or 'multiqc', allow_root=True)


@pytest.mark.skipif(not FASTQC, reason='Real FastQC is not installed')
def test_real_fastqc_preserves_source_values_and_history(tmp_path):
    settings = real_settings(tmp_path)
    files = sorted(INPUTS.glob('*.fastq.gz'))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization': f'Bearer {settings.token}', 'X-QualiDock-Request': '1'})
        response = client.post('/api/runs', json={'mode': 'fastqc', 'paths': [str(p.resolve()) for p in files], 'threads': 1})
        assert response.status_code == 201, response.text
        run = wait(client, response.json()['id'])
        assert run['state'] == 'completed', client.get(f"/api/runs/{run['id']}/logs").json()
        assert run['tools']['fastqc']['version']
        assert run['executions'][0]['exit_code'] == 0
        samples = client.get(f"/api/runs/{run['id']}/metrics").json()['samples']
        assert len(samples) == 2
        for sample in samples:
            report = settings.output / run['id'] / sample['id']
            assert sample == parse_report(report, sample['id'])
            assert sample['status'] == 'fail'  # Actual QC results, not a failed process.
            assert any(b['base'] == '10-14' for b in sample['per_base_quality'])
            response = client.get(f"/api/runs/{run['id']}/download", params={'path': sample['id'].replace('.zip', '.html')})
            assert response.status_code == 200 and 'attachment' in response.headers['content-disposition']
            preview = client.get('/api/report-preview', params={'run_id': run['id'], 'path': sample['id'].replace('.zip', '.html')})
            assert preview.status_code == 200 and preview.content == response.content
            assert 'inline' in preview.headers['content-disposition']
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization': f'Bearer {settings.token}'})
        assert client.get(f"/api/runs/{run['id']}/metrics").json()['samples'] == samples
        assert client.get('/api/report-preview', params={'run_id': run['id'], 'path': samples[0]['id'].replace('.zip', '.html')}).status_code == 200
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


@pytest.mark.skipif(not FASTQC or not MULTIQC, reason='Real FastQC and MultiQC are both required')
def test_real_combined_and_existing_results_multiqc(tmp_path):
    settings = real_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization': f'Bearer {settings.token}', 'X-QualiDock-Request': '1'})
        response = client.post('/api/runs', json={'mode': 'both', 'paths': [str(p.resolve()) for p in sorted(INPUTS.glob('*.fastq.gz'))]})
        assert response.status_code == 201, response.text
        run_id = response.json()['id']
        # MultiQC can take longer to initialize than the small FastQC analysis itself.
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            run = client.get(f'/api/runs/{run_id}').json()
            if run['state'] not in {'queued', 'running'}: break
            time.sleep(0.1)
        assert run['state'] == 'completed', client.get(f'/api/runs/{run_id}/logs').json()
        assert run['executions'][-1]['exit_code'] == 0
        report = client.get(f'/api/runs/{run_id}/download', params={'path': 'multiqc/multiqc_report.html'})
        assert report.status_code == 200
        preview = client.get('/api/report-preview', params={'run_id': run_id, 'path': 'multiqc/multiqc_report.html'})
        assert preview.status_code == 200
        assert preview.content.replace(MEMORY_STORAGE_BOOTSTRAP, b'', 1) == report.content
        assert preview.content.count(MEMORY_STORAGE_BOOTSTRAP) == 1
        summary = client.get(f'/api/runs/{run_id}/metrics').json()['multiqc']
        assert len(summary['rows']) == 2 and summary['columns']
        response = client.post(f'/api/runs/{run_id}/multiqc')
        assert response.status_code == 201, response.text
        aggregate_id = response.json()['id']
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            aggregate = client.get(f'/api/runs/{aggregate_id}').json()
            if aggregate['state'] not in {'queued', 'running'}: break
            time.sleep(0.1)
        assert aggregate['state'] == 'completed', client.get(f'/api/runs/{aggregate_id}/logs').json()
        assert all(e['tool'] == 'multiqc' for e in aggregate['executions'])
        assert len(client.get(f'/api/runs/{aggregate_id}/metrics').json()['multiqc']['rows']) == 2
        imported_html = next(r['path'] for r in aggregate['reports'] if r['path'].startswith('inputs/') and r['path'].endswith('.html'))
        for path in (imported_html, 'multiqc/multiqc_report.html'):
            assert client.get('/api/report-preview', params={'run_id': aggregate_id, 'path': path}).status_code == 200
    with TestClient(create_app(settings)) as restored:
        restored.headers.update({'Authorization': f'Bearer {settings.token}'})
        response = restored.get('/api/report-preview', params={'run_id': run_id, 'path': 'multiqc/multiqc_report.html'})
        assert response.content.replace(MEMORY_STORAGE_BOOTSTRAP, b'', 1) == report.content


@pytest.mark.skipif(not FASTQC or not MULTIQC, reason='Real FastQC and MultiQC are required')
def test_real_manual_pair_groups_custom_output_and_rerun(tmp_path):
    # Exact copies of the small genuine inputs, with nonstandard facility filenames.
    from dataclasses import replace
    inputs=tmp_path/'facility';inputs.mkdir()
    files=[]
    for read,name in [('R1','facility forward.fastq.gz'),('R2','facility reverse.fastq.gz')]:
        path=inputs/name;shutil.copyfile(INPUTS/f'coverage_{read}.fastq.gz',path);files.append(path)
    project=tmp_path/'project-results';project.mkdir()
    settings=replace(real_settings(tmp_path), roots=[inputs], output_roots=[project])
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'})
        pairs=[{'path':str(path),'paired':True,'assignment':'paired','read':f'R{i+1}','mate':str(files[1-i]),'pair_key':'manual:facility','source':'manual','lane':'L001','chunk':'001'} for i,path in enumerate(files)]
        groups=[{'id':'sample:facility','display_name':'Facility sample','files':list(map(str,files)),'source':'manual'}]
        response=client.post('/api/runs',json={'name':'Real manual metadata','mode':'both','paths':list(map(str,files)),'input_pairing':pairs,'sample_groups':groups,'output_root':str(project)})
        assert response.status_code==201,response.text
        run=wait(client,response.json()['id'],timeout=180)
        assert run['state']=='completed',run.get('error')
        metrics=client.get(f"/api/runs/{run['id']}/metrics").json()
        assert len(metrics['samples'])==2 and len(metrics['multiqc']['rows'])==2
        for sample in metrics['samples']:
            assert sample==parse_report(project/run['id']/sample['id'],sample['id'])
        original=(project/run['id']/'multiqc/multiqc_report.html').read_bytes()
        assert client.patch(f"/api/runs/{run['id']}",json={'name':'Renamed real run'}).status_code==200
        draft=client.get(f"/api/runs/{run['id']}/configuration").json()
        draft.pop('entries')
        rerun=client.post('/api/runs',json=draft)
        assert rerun.status_code==201,rerun.text
        rerun=wait(client,rerun.json()['id'],timeout=180)
        assert rerun['state']=='completed' and rerun['id']!=run['id']
        assert (project/run['id']/'multiqc/multiqc_report.html').read_bytes()==original
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization':f'Bearer {settings.token}'})
        restored=client.get(f"/api/runs/{run['id']}").json()
        assert restored['sample_groups']==groups
        assert restored['output_root']==str(project)
        assert client.get(f"/api/runs/{run['id']}/metrics").json()==metrics
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


@pytest.mark.skipif(not FASTQC or not MULTIQC, reason='Real FastQC and MultiQC are required')
def test_real_same_basename_pairs_namespaces_multiqc_and_restart(tmp_path):
    import json
    from dataclasses import replace
    inputs=tmp_path/'duplicate-inputs';inputs.mkdir()
    paths=[]
    for study in ['study a','study b']:
        folder=inputs/study;folder.mkdir()
        for source in sorted(INPUTS.glob('*.fastq.gz')):
            target=folder/source.name;shutil.copyfile(source,target);paths.append(target)
    settings=replace(real_settings(tmp_path),roots=[inputs])
    headers={'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'}
    before={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    with TestClient(create_app(settings),headers=headers) as client:
        response=client.post('/api/runs',json={'mode':'both','paths':list(before)})
        assert response.status_code==201,response.text
        run=wait(client,response.json()['id'],timeout=180)
        assert run['state']=='completed',run['error']
        metrics=client.get(f"/api/runs/{run['id']}/metrics").json()
        assert len(metrics['samples'])==len(metrics['multiqc']['rows'])==4
        assert all(r['state']=='completed' for r in run['input_outcomes'])
        assert len({row['sample'] for row in metrics['multiqc']['rows']})==4
        assert {entry['path'] for entry in run['report_input_map'].values()}==set(before)
        assert all(entry['multiqc_name'] in {row['sample'] for row in metrics['multiqc']['rows']} for entry in run['report_input_map'].values())
        aggregated=client.post(f"/api/runs/{run['id']}/multiqc")
        assert aggregated.status_code==201,aggregated.text
        aggregated=wait(client,aggregated.json()['id'],timeout=180)
        assert aggregated['state']=='completed',aggregated['error']
        restored_metrics=client.get(f"/api/runs/{aggregated['id']}/metrics").json()
        assert len(restored_metrics['multiqc']['rows'])==4
        assert {entry['path'] for entry in aggregated['report_input_map'].values()}==set(before)
        for sample in metrics['samples']:
            parsed=parse_report(settings.output/run['id']/sample['id'],sample['id'])
            assert sample==parsed
    with TestClient(create_app(settings),headers=headers) as client:
        restored=client.get(f"/api/runs/{run['id']}").json()
        assert restored['report_input_map']==run['report_input_map']
        assert restored['input_outcomes']==run['input_outcomes']
    assert before=={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


@pytest.mark.skipif(not FASTQC, reason='Real FastQC is required')
def test_real_corrupt_input_keeps_good_report_and_truthful_file_outcome(tmp_path):
    from dataclasses import replace
    root=tmp_path/'mixed';root.mkdir()
    good=root/'coverage_R1.fastq.gz';shutil.copyfile(INPUTS/'coverage_R1.fastq.gz',good)
    broken=root/'corrupt.fastq';broken.write_text('@broken\nACGT\n+\n')
    settings=replace(real_settings(tmp_path),roots=[root])
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'})
        response=client.post('/api/runs',json={'mode':'fastqc','paths':[str(good),str(broken)]})
        assert response.status_code==201,response.text
        run=wait(client,response.json()['id'],timeout=180)
        assert run['state']=='partial',run['error']
        by_name={record['name']:record for record in run['input_outcomes']}
        assert by_name[good.name]['state']=='completed'
        assert by_name[broken.name]['state']=='failed' and by_name[broken.name]['error']
        assert client.get(f"/api/runs/{run['id']}/download",params={'path':by_name[good.name]['report']}).status_code==200


@pytest.mark.skipif(not MULTIQC,reason='Real MultiQC is required')
def test_real_fastp_only_and_mixed_import_preserve_provenance_and_native_fastqc(tmp_path):
 import json
 root=(Path(__file__).parent/'fixtures').resolve()
 settings=real_settings(tmp_path);settings.roots=[root]
 fastp=root/'imported-qc/fastp/HG001.fastp.json';older=root/'imported-qc/fastp/fastp.json'
 fastqc=root/'fastqc-0.13.0/coverage_R1_fastqc/fastqc_data.txt'
 before={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in [fastp,older,fastqc]}
 saved=[]
 with TestClient(create_app(settings)) as client:
  client.headers.update({'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'})
  for sources in [[fastp,older],[fastp,older,fastqc]]:
   response=client.post('/api/runs',json={'mode':'multiqc','paths':list(map(str,sources))})
   assert response.status_code==201,response.text
   run=wait(client,response.json()['id']);base=f"/api/runs/{run['id']}"
   assert run['state']=='completed',client.get(base+'/logs').text
   metrics=client.get(base+'/metrics').json();summary=metrics['multiqc']
   assert summary['status']=='available' and len(summary['rows'])==len(sources)
   assert len(metrics['samples'])==len(sources)-2
   assert not any(execution['tool']=='fastqc' for execution in run['executions'])
   assert all(record['snapshot_sha256']==before[Path(record['path'])] for record in run['report_inputs'])
   names=[mapping.get('multiqc_name') for mapping in run['report_input_map'].values()]
   assert len(set(names))==len(sources) and all(names)
   assert {mapping['source_report'] for mapping in run['report_input_map'].values()}==set(map(str,sources))
   for record in run['report_inputs']:
    assert client.get(base+'/download',params={'path':record['snapshot_artifact']}).content==Path(record['path']).read_bytes()
   assert client.get(base+'/download',params={'path':'multiqc/multiqc_report.html'}).status_code==200
   imported_row=next(row for row in summary['rows'] if row['sample']==next(mapping['multiqc_name'] for mapping in run['report_input_map'].values() if mapping['source_report']==str(fastp)))
   source=json.loads(fastp.read_text())
   count=next(column['key'] for column in summary['columns'] if column['raw_key']=='filtering_result_passed_filter_reads')
   assert imported_row['values'][count]==source['filtering_result']['passed_filter_reads']
   saved.append((base,metrics))
 with TestClient(create_app(settings)) as client:
  client.headers.update({'Authorization':f'Bearer {settings.token}'})
  assert all(client.get(base+'/metrics').json()==metrics for base,metrics in saved)
 assert before=={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in before}


@pytest.mark.skipif(not FASTQC,reason='Real FastQC is required')
def test_real_fastqc_full_integrity_review_and_original_report_bundle(tmp_path):
 import io,json,zipfile
 from test_validation_jobs import finish
 from test_release_exports import exported
 settings=real_settings(tmp_path);sources=sorted(INPUTS.resolve().glob('*.fastq.gz'))
 original={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
 with TestClient(create_app(settings)) as client:
  client.headers.update({'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'})
  response=client.post('/api/runs',json={'name':'Genuine fixture release','mode':'fastqc','paths':list(map(str,sources))})
  assert response.status_code==201,response.text
  run=wait(client,response.json()['id']);assert run['state']=='completed'
  base=f"/api/runs/{run['id']}"
  assert client.post(base+'/integrity',json={'mode':'full'}).status_code==202
  assert finish(client,run['id'])['result']=='passed'
  delivery=client.get(base+'/delivery').json();group=delivery['files'][0]['sample_id']
  expected=[{'filename':path.name,'expected_reads':400,'sha256':sha} for path,sha in original.items()]
  assert client.post(base+'/expected-delivery',json={'format':'json','content':json.dumps(expected)}).status_code==200
  assert client.post(base+'/yield-targets',json={'assay':'Genuine paired-read fixture','input_stage':'unknown','targets':[{'sample_id':group,'metric':'read_pairs','minimum':300}]}).status_code==200
  assert client.post(base+'/release-policy',json={'version':'fixture-1','assay':'Genuine paired-read fixture','required_checks':['integrity','expected_delivery','quantity']}).status_code==200
  value=client.post(base+'/release-review/evaluate',json={'sample_ids':[group]}).json()
  assert value['readiness']=='ready'
  assert client.post(base+'/release-review',json={'sample_ids':[group],'fingerprint':value['fingerprint'],'action':'approve','reason':'Independent fixture counts and hashes verified'}).status_code==200
  response=client.post(base+'/release-exports',json={'sample_ids':[group],'fingerprint':value['fingerprint'],'include_reports':True,'acknowledge_report_paths':True})
  assert response.status_code==202,response.text
  record=exported(client,base);assert record['state']=='completed',record
  archive=zipfile.ZipFile(io.BytesIO(client.get(base+'/download',params={'path':record['artifact']}).content))
  manifest=json.loads(archive.read('manifest.json'));assert manifest['release_status']=='approved'
  assert manifest['yields'][0]['totals']['reads']==800 and manifest['yields'][0]['totals']['read_pairs']==400
  selected=json.loads(archive.read('qc-metrics.json'))['samples'];saved=client.get(base+'/metrics').json()['samples']
  assert selected==saved
  for report in manifest['report_artifacts']:
   assert archive.read(report['path'])==client.get(base+'/download',params={'path':report['source_artifact']}).content
 assert original=={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
