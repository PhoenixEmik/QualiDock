"""Synthetic file metadata / executable doubles here; genuine engine coverage remains in test_real_tools."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import uuid

import pytest
from fastapi.testclient import TestClient

from qualidock.app import create_app
from qualidock.files import FileAccess
from qualidock.manager import RunManager
from qualidock.sample_metadata import describe
from qualidock.store import ResultStores
from test_workspace import wait


def auth(settings):
    return {"Authorization": f"Bearer {settings.token}", "X-QualiDock-Request": "1"}


def configuration(client, paths):
    response = client.post('/api/sample-configuration', json={'paths': [str(path) for path in paths]})
    assert response.status_code == 200, response.text
    return response.json()


def run(client, paths, **options):
    response = client.post('/api/runs', json={'mode': 'fastqc', 'paths': [str(path) for path in paths], **options})
    assert response.status_code == 201, response.text
    return wait(client, response.json()['id'])


@pytest.mark.parametrize('name,lane,chunk,display', [
    ('C15_S1_L001_R1_001.fastq.gz','L001','001','C15'),
    ('C15_L003_R2.fq.gz','L003',None,'C15'),
    ('C15_R1_010.fastq',None,'010','C15'),
    ('C15_2.fastq',None,None,'C15'),
])
def test_illumina_identity(name,lane,chunk,display):
    value=describe('/data/'+name)
    assert (value['lane'],value['chunk'],value['sample_name'])==(lane,chunk,display)
    assert describe('/other/'+name)['sample_key'] != value['sample_key']
    assert describe('/data/S1_L001_R1_001.fastq')['sample_key'] is None


def test_lane_chunk_sample_detection_selection_and_snapshot(client,setup):
    _,root=setup
    paths=[]
    for sample in ['C15_S1','C15_S2','D20_S1']:
        for lane in ['L001','L002']:
            for chunk in ['001','002']:
                for read in ['R1','R2']:
                    path=root/f'{sample}_{lane}_{read}_{chunk}.fastq'
                    path.write_text('@r\nACGT\n+\nIIII\n');paths.append(path)
    config=configuration(client,paths)
    assert len(config['sample_groups'])==3
    assert all(len(group['files'])==8 for group in config['sample_groups'])
    assert len({r['pair_key'] for r in config['input_pairing']})==12
    page=client.get('/api/files',params={'path':str(root),'limit':1}).json()
    assert len(page['sample_groups'])==1
    group=next(iter(page['sample_groups'].values()))
    assert group['total']==8 and len(group['paths'])==8
    assert page['entries'][0]['lane']=='L001'
    original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    record=run(client,paths,**{k:config[k] for k in ['input_pairing','sample_groups']})
    assert record['sample_groups']==config['sample_groups']
    assert record['sample_count']==24
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}==original


def manual_config(config):
    result=deepcopy(config)
    a,b=result['input_pairing'][:2]
    for record,read,mate in [(a,'R1',b['path']),(b,'R2',a['path'])]:
        record.update(paired=True,assignment='paired',pair_key='manual:pair',read=read,mate=mate,source='manual',lane='L001',chunk='001')
    result['sample_groups']=[{'id':'sample:user','display_name':'User supplied sample','files':[a['path'],b['path']],'source':'manual'}]
    return result


def test_nonstandard_manual_pair_confirm_remove_and_rerun(setup):
    settings,root=setup
    paths=[root/'forward reads ; $(touch BAD).fastq',root/'reverse & reads.fastq']
    for path in paths:path.write_text('@r\nACGT\n+\nIIII\n')
    with TestClient(create_app(settings),headers=auth(settings)) as client:
        config=manual_config(configuration(client,paths))
        record=run(client,paths,name='Manual sample',input_pairing=config['input_pairing'],sample_groups=config['sample_groups'])
        assert all(r['source']=='manual' for r in record['input_pairing'])
        assert record['sample_count']==2 and record['state']=='completed'
        assert not (root/'BAD').exists()
        renamed=client.patch(f"/api/runs/{record['id']}",json={'name':'Renamed <sample>'})
        assert renamed.status_code==200
        draft=client.get(f"/api/runs/{record['id']}/configuration").json()
        rerun=run(client,draft['paths'],name=draft['name'],input_pairing=draft['input_pairing'],sample_groups=draft['sample_groups'],output_root=draft['output_root'],rerun_of=draft['rerun_of'])
        assert rerun['id']!=record['id'] and rerun['input_pairing']==record['input_pairing']
        assert rerun['rerun_of']==record['id']
        removed=deepcopy(config['input_pairing'])
        for r in removed:r.update(paired=False,assignment='single',mate=None,pair_key=None,read=None)
        single=run(client,paths,input_pairing=removed,sample_groups=config['sample_groups'])
        assert all(r['assignment']=='single' and not r['paired'] for r in single['input_pairing'])
    with TestClient(create_app(settings),headers=auth(settings)) as client:
        restored=client.get(f"/api/runs/{record['id']}").json()
        assert restored['name']=='Renamed <sample>' and restored['sample_groups']==record['sample_groups']
        paths[0].unlink()
        assert client.get(f"/api/runs/{record['id']}/configuration").status_code==403


@pytest.mark.parametrize('attack',['self','duplicate','missing','conflict','auto_spoof','group_duplicate','group_missing'])
def test_pair_and_group_rejection(client,setup,attack):
    _,root=setup
    paths=sorted(root.glob('*.fastq'))
    config=configuration(client,paths)
    records=config['input_pairing'];groups=config['sample_groups']
    if attack=='self': records[0]['mate']=records[0]['path']
    if attack=='duplicate':records.append(deepcopy(records[0]))
    if attack=='missing':records[0]['mate']=str(root/'missing.fastq')
    if attack=='conflict':records[0]['pair_key']='different'
    if attack=='auto_spoof':records[0]['read'],records[1]['read']='R2','R1'
    if attack=='group_duplicate':groups[0]['files'].append(groups[0]['files'][0])
    if attack=='group_missing':groups[0]['files'].pop()
    response=client.post('/api/runs',json={'mode':'fastqc','paths':list(map(str,paths)), 'input_pairing':records,'sample_groups':groups})
    assert response.status_code in [400,403,422],response.text


def test_incomplete_ambiguous_and_independent_samples(client,setup):
    _,root=setup
    extra=root/'sample_1_001.fastq';extra.write_text('@r\nA\n+\nI\n')
    config=configuration(client,sorted(root.glob('*.fastq')))
    assert not any(r['paired'] for r in config['input_pairing'])
    assert len(config['sample_groups'])==3
    extra.unlink()
    config=configuration(client,[root/'sample_R1_001.fastq'])
    assert not config['input_pairing'][0]['paired']
    assert config['input_pairing'][0]['read']=='R1'


def test_output_stores_restart_rename_integrity_and_aggregate(setup):
    settings,root=setup
    extra=root.parent/'project-results';extra.mkdir()
    settings=replace(settings,output_roots=[extra])
    with TestClient(create_app(settings),headers=auth(settings)) as client:
        paths=sorted(root.glob('*.fastq'))
        record=run(client,paths,name='Project QC',output_root=str(extra))
        directory=extra/record['id']
        assert directory.is_dir() and not (settings.output/record['id']).exists()
        html=next(path for path in directory.rglob('*.html'))
        original=html.read_bytes()
        assert client.patch(f"/api/runs/{record['id']}",json={'name':'Updated name'}).status_code==200
        assert html.read_bytes()==original
        assert client.get(f"/api/runs/{record['id']}/download",params={'path':str(html.relative_to(directory))}).content==original
        aggregate=client.post(f"/api/runs/{record['id']}/multiqc")
        assert aggregate.status_code==201
        combined=wait(client,aggregate.json()['id'])
        assert combined['output_root']==str(extra)
        assert combined['input_pairing']==record['input_pairing']
        draft=client.get(f"/api/runs/{combined['id']}/configuration").json()
        recreated=client.post('/api/runs',json={k:draft[k] for k in ['name','mode','paths','threads','output_root','rerun_of']})
        assert recreated.status_code==201,recreated.text
        assert wait(client,recreated.json()['id'])['state']=='completed'
    with TestClient(create_app(settings),headers=auth(settings)) as client:
        restored=client.get(f"/api/runs/{record['id']}").json()
        assert restored['name']=='Updated name'
        assert restored['output_directory']==str(directory)
        assert client.get(f"/api/runs/{record['id']}/metrics").status_code==200


@pytest.mark.parametrize('attack',['outside','traversal','symlink','read_only','collision','no_space'])
def test_output_rejection(client,setup,monkeypatch,attack):
    settings,root=setup
    output=settings.output
    chosen=str(output)
    if attack=='outside':chosen=str(root)
    if attack=='traversal':chosen=str(output/'..'/'results')
    if attack=='symlink':
        link=root.parent/'alias';link.symlink_to(output,target_is_directory=True);chosen=str(link)
    if attack=='read_only':output.chmod(0o500)
    if attack=='collision':
        value=uuid.UUID('f'*32);(output/value.hex).mkdir();(output/value.hex/'sentinel').write_text('keep')
        monkeypatch.setattr('qualidock.manager.uuid.uuid4',lambda:value)
    if attack=='no_space':monkeypatch.setattr('qualidock.store.shutil.disk_usage',lambda _:type('Usage',(),{'free':0})())
    try:
        response=client.post('/api/runs',json={'mode':'fastqc','paths':list(map(str,root.glob('*.fastq'))),'output_root':chosen})
        assert response.status_code in [400,403],response.text
        if attack=='collision':assert (output/('f'*32)/'sentinel').read_text()=='keep'
    finally:
        if attack=='read_only':output.chmod(0o700)


def test_all_output_roots_are_locked_and_duplicate_ids_rejected(setup):
    settings,root=setup
    extra=root.parent/'project';extra.mkdir()
    first=RunManager(replace(settings,output_roots=[extra]));first.start()
    second=RunManager(replace(settings,output=extra))
    try:
        with pytest.raises(RuntimeError,match='Another QualiDock'):second.start()
    finally:first.stores.close()
    run_id='a'*32
    for store in [settings.output,extra]:
        directory=store/run_id;directory.mkdir()
        (directory/'manifest.json').write_text(json.dumps({'id':run_id,'state':'completed','created_at':'2026-01-01','reports':[]}))
    manager=RunManager(replace(settings,output_roots=[extra]))
    with pytest.raises(RuntimeError,match='Duplicate analysis'):manager.start()
    assert not manager.stores.locks


def test_original_fastq_permission_and_metadata_revalidation(client,setup):
    _,root=setup
    path=root/'sample_R1_001.fastq';path.chmod(0)
    try:assert client.post('/api/sample-configuration',json={'paths':[str(path)]}).status_code==400
    finally:path.chmod(0o600)


@pytest.mark.parametrize('name',['','  ','name\nwith newline'])
def test_invalid_rename_leaves_manifest_unchanged(client,setup,name):
    _,root=setup
    record=run(client,sorted(root.glob('*.fastq')),name='Original')
    response=client.patch(f"/api/runs/{record['id']}",json={'name':name})
    assert response.status_code in [400,422]
    assert client.get(f"/api/runs/{record['id']}").json()['name']=='Original'


def test_output_loss_while_queued_surfaces_failure_without_starting_tool(setup):
    import asyncio
    settings,root=setup
    async def scenario():
        manager=RunManager(settings);manager.start()
        await manager.slot.acquire()
        record=await manager.create('Queued output loss','fastqc',list(map(str,root.glob('*.fastq'))),1)
        settings.output.chmod(0o500)
        manager.slot.release()
        await asyncio.gather(*list(manager.tasks.values()))
        assert record['state']=='failed' and 'writable' in record['error']
        assert not record['executions']
        settings.output.chmod(0o700)
        await manager.close()
    try:asyncio.run(scenario())
    finally:settings.output.chmod(0o700)


def test_finished_download_survives_readonly_store_and_rename_is_atomic(client,setup):
    settings,root=setup
    record=run(client,sorted(root.glob('*.fastq')),name='Original')
    artifact=next(r['path'] for r in record['reports'] if r['path'].endswith('.html'))
    settings.output.chmod(0o500)
    try:
        assert client.get(f"/api/runs/{record['id']}/download",params={'path':artifact}).status_code==200
        assert client.patch(f"/api/runs/{record['id']}",json={'name':'Rejected'}).status_code==403
        assert client.get(f"/api/runs/{record['id']}").json()['name']=='Original'
        assert json.loads((settings.output/record['id']/'manifest.json').read_text())['name']=='Original'
    finally:settings.output.chmod(0o700)
