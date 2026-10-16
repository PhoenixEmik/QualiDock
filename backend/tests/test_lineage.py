"""Synthetic topology tests contain metadata only; chain acceptance runs genuine tools."""
from copy import deepcopy
import hashlib
import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.lineage import MAX_DEPTH, MAX_NODES, MAX_ITEMS
from test_processing_real import FASTP, SEQKIT, FASTQC, FIXTURE, settings, auth, submit
from test_workspace import wait


def synthetic(manager,number,parents=()):
    identity=f'{number:032x}'
    manager.runs[identity]={'id':identity,'name':f'Metadata topology {number}','state':'completed','mode':'fastqc','inputs':[],
        'input_datasets':[{'run_id':f'{parent:032x}','dataset_id':'example'} for parent in parents]}
    return identity


def test_historical_missing_parents_rerun_and_auth(client):
    manager=client.app.state.manager
    identity=synthetic(manager,1,[999])
    manager.runs[identity]['rerun_of']=f'{998:032x}'
    response=client.get(f'/api/runs/{identity}/lineage')
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    node=response.json()['nodes'][0]
    assert node['parents'][0]['integrity']=='missing_parent' and node['rerun_of']==f'{998:032x}'
    assert node['tools']=={} and node['parameters']=={}
    old=synthetic(manager,2)
    assert client.get(f'/api/runs/{old}/lineage').json()['nodes'][0]['parents']==[]
    client.headers.pop('Authorization')
    assert client.get(f'/api/runs/{identity}/lineage').status_code==401


def test_cycle_depth_and_total_node_limits(client):
    manager=client.app.state.manager
    first=synthetic(manager,1,[2]);synthetic(manager,2,[1])
    result=client.get(f'/api/runs/{first}/lineage').json()
    assert len(result['nodes'])==2 and any('Cycle' in w for w in result['warnings'])
    manager.runs.clear()
    for n in range(1,MAX_DEPTH+5): synthetic(manager,n,[n+1])
    result=client.get(f'/api/runs/{first}/lineage').json()
    assert len(result['nodes'])==MAX_DEPTH+1 and result['warnings']
    manager.runs.clear()
    synthetic(manager,1,range(2,40))
    for n in range(2,40): synthetic(manager,n)
    result=client.get(f'/api/runs/{first}/lineage').json()
    assert len(result['nodes'])==MAX_NODES and result['warnings']


def test_input_limits_unchanged_vs_changed_and_no_persisted_graph(client,setup):
    from qualidock.reports import metadata
    manager=client.app.state.manager;_,root=setup
    identity=synthetic(manager,1)
    path=root/'sample_R1_001.fastq'
    info=path.stat()
    manager.runs[identity].update(inputs=[str(path)],input_metadata=[{**metadata(path),'device':info.st_dev,'inode':info.st_ino}])
    before=set(manager.settings.output.rglob('*'))
    first=client.get(f'/api/runs/{identity}/lineage').json()['nodes'][0]
    assert first['inputs'][0]['integrity']=='metadata_matches_recorded_not_rehashed'
    assert not first['inputs'][0]['parent_recorded']
    path.write_text('@changed\nACGT\n+\nIIII\n')
    assert client.get(f'/api/runs/{identity}/lineage').json()['nodes'][0]['inputs'][0]['integrity']=='unavailable_or_changed'
    manager.runs[identity]['inputs']=[str(path)]*(MAX_ITEMS+5)
    result=client.get(f'/api/runs/{identity}/lineage').json()['nodes'][0]
    assert len(result['inputs'])==MAX_ITEMS and result['omitted_inputs']==5
    assert before==set(manager.settings.output.rglob('*'))


@pytest.mark.skipif(not all((FASTP,SEQKIT,FASTQC)),reason='Actual fastp, SeqKit and FastQC required')
def test_genuine_chain_restart_parent_integrity_and_mapping(tmp_path):
    config=settings(tmp_path)
    paths=sorted(FIXTURE.glob('*.fastq.gz'))
    original=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    with TestClient(create_app(config)) as client:
        auth(client,config)
        first=submit(client,'fastp',paths,{'compare_qc':False})
        draft=client.get(f"/api/runs/{first['id']}/datasets").json()
        def next_run(draft,mode,options=None):
            body={key:draft[key] for key in ('paths','input_pairing','sample_groups')}
            body.update(mode=mode,input_datasets=[{k:row[k] for k in ('run_id','dataset_id')} for row in draft['input_datasets']])
            if options is not None: body['processing_options']=options
            created=client.post('/api/runs',json=body)
            assert created.status_code==201,created.text
            run=wait(client,created.json()['id'],timeout=180)
            assert run['state']=='completed',run.get('error')
            return run
        second=next_run(draft,'seqkit-sample',{'count':7,'seed':73})
        draft=client.get(f"/api/runs/{second['id']}/datasets").json()
        third=next_run(draft,'fastqc')
    with TestClient(create_app(config)) as client:
        auth(client,config)
        response=client.get(f"/api/runs/{third['id']}/lineage")
        assert response.status_code==200
        result=response.json(); nodes=result['nodes']
        assert [n['id'] for n in nodes]==[first['id'],second['id'],third['id']]
        assert not result['warnings']
        assert nodes[0]['tools']['fastp'] and nodes[1]['tools']['seqkit'] and nodes[2]['tools']['fastqc']=='0.13.0'
        assert nodes[1]['parameters']['count']==7 and nodes[1]['parameters']['seed']==73
        assert {p['read'] for p in nodes[2]['inputs']}=={'R1','R2'}
        assert len(nodes[2]['parents'])==2 and len(nodes[1]['parents'])==2
        assert all(p['integrity']=='metadata_matches_recorded_not_rehashed' for p in nodes[2]['parents'])
        assert all(p['parent_id']==second['id'] for p in nodes[2]['parents'])
        # A historical copied hash cannot silently disagree with its source dataset.
        current=client.app.state.manager.runs[third['id']]
        saved=deepcopy(current['input_provenance'])
        current['input_provenance'][0]['sha256']='0'*64
        assert client.get(f"/api/runs/{third['id']}/lineage").json()['nodes'][-1]['parents'][0]['integrity']=='inconsistent_reference'
        current['input_provenance']=saved
        output=config.output/second['id']/second['derived_datasets'][0]['path']
        output.write_bytes(b'changed')
        changed=client.get(f"/api/runs/{third['id']}/lineage").json()['nodes'][-1]
        assert changed['parents'][0]['integrity']=='unavailable_or_changed'
        assert changed['inputs'][0]['integrity']=='unavailable_or_changed'
        del client.app.state.manager.runs[second['id']]
        missing=client.get(f"/api/runs/{third['id']}/lineage").json()['nodes'][-1]
        assert all(edge['integrity']=='missing_parent' for edge in missing['parents'])
    assert original==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]


def test_independent_inputs_lane_identity_and_old_snapshots(client,setup):
    manager=client.app.state.manager;_,root=setup
    identity=synthetic(manager,1)
    paths=[str(root/f'sample_R{n}_001.fastq') for n in (1,2)]
    manager.runs[identity].update(inputs=paths,input_pairing=[
        {'path':paths[0],'read':'R1','paired':False,'lane':'L001','chunk':'001'},
        {'path':paths[1],'read':'R2','paired':False,'lane':'L002','chunk':'002'}],
        input_metadata=[{'path':path,'size':(root/f'sample_R{n}_001.fastq').stat().st_size} for n,path in enumerate(paths,1)])
    node=client.get(f'/api/runs/{identity}/lineage').json()['nodes'][0]
    assert not node['parents'] and len(node['inputs'])==2
    assert [r['lane'] for r in node['inputs']]==['L001','L002']
    assert [r['chunk'] for r in node['inputs']]==['001','002']
    assert all(not r['paired'] and r['integrity']=='historical_metadata_unavailable' for r in node['inputs'])
