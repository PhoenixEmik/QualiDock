"""Parameter/path/lifecycle regressions; real scientific outputs live in *_real tests."""
import asyncio
import json
from pathlib import Path
import sys
import time
import pytest
from qualidock.processing import options, fastp_command, seqkit_command, units
from test_workspace import wait


@pytest.mark.parametrize('mode,value', [('fastp',{'shell':'rm'}),('fastp',{'min_length':0}),('fastp',{'qualified_quality':94}),('fastp',{'adapter_trimming':'yes'}),('seqkit-sample',{'fraction':0}),('seqkit-filter',{'min_length':30,'max_length':20}),('seqkit-extract',{'identifiers':['bad\nname']}),('seqkit-extract',{'identifiers':[]})])
def test_invalid_parameters(mode,value):
    with pytest.raises(ValueError): options(mode,value)


def test_literal_arguments_and_pair_units():
    paths=['/data/a $(touch PWNED).fq','/data/b ; exit.fq']
    command=fastp_command('/tool/fastp',[Path(p) for p in paths],[Path('/run/r1.fq'),Path('/run/r2.fq')],Path('/run'),1,options('fastp',{}))
    assert command[command.index('--in1')+1]==paths[0]
    assert command[command.index('--in2')+1]==paths[1]
    assert '--detect_adapter_for_pe' in command and '--dont_overwrite' in command
    run={'mode':'fastp','inputs':paths,'input_pairing':[{'path':paths[0],'mate':paths[1],'read':'R1','paired':True},{'path':paths[1],'mate':paths[0],'read':'R2','paired':True}]}
    assert len(units(run))==1
    run['mode']='seqkit-filter'
    assert len(units(run))==2  # independently filtered files must not claim mate synchrony
    run['mode']='fastp';run['input_pairing'][1]['mate']='/other'
    with pytest.raises(ValueError): units(run)


def test_missing_processing_dependency_and_bad_input(setup):
    from fastapi.testclient import TestClient
    from qualidock.app import create_app
    settings,root=setup;settings.fastp=str(root/'missing-executable')
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'})
        response=client.post('/api/runs',json={'mode':'fastp','paths':[str(root/'sample_R1_001.fastq')],'processing_options':{'compare_qc':False}})
        assert response.status_code==400 and 'unavailable' in response.text.lower()
        assert not client.get('/api/runs').json()
        response=client.post('/api/runs',json={'mode':'fastp','paths':[str(root/'../escape.fastq')],'processing_options':{'compare_qc':False}})
        assert response.status_code in (400,403,404)


def test_processing_cancel_and_restart(setup):
    """A deliberately sleeping command tests cancellation, not fabricated QC outputs."""
    from fastapi.testclient import TestClient
    from qualidock.app import create_app
    settings,root=setup
    executable=root/'slow-fastp'
    executable.write_text(f'#!{sys.executable}\nimport sys,time\nif "--version" in sys.argv: print("fastp 1.4.0");sys.exit(0)\ntime.sleep(30)\n')
    executable.chmod(0o700);settings.fastp=str(executable)
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'})
        response=client.post('/api/runs',json={'mode':'fastp','paths':[str(root/'sample_R1_001.fastq')],'processing_options':{'compare_qc':False}})
        assert response.status_code==201,response.text
        identity=response.json()['id']
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            run=client.get('/api/runs/'+identity).json()
            if any(entry['tool']=='fastp' and entry['exit_code'] is None for entry in run['executions']):break
            time.sleep(.03)
        else:pytest.fail('fastp did not start')
        run=client.post(f'/api/runs/{identity}/cancel').json()
        assert run['state']=='cancelled' and not run['derived_datasets']
        assert client.get(f'/api/runs/{identity}/download',params={'path':'processing/u0001/processed_R1.fastq.gz'}).status_code==403
    manifest=settings.output/identity/'manifest.json'
    saved=json.loads(manifest.read_text());saved['state']='running';saved['processing']['units'][0]['state']='running'
    manifest.write_text(json.dumps(saved))
    with TestClient(create_app(settings)) as client:
        client.headers.update({'Authorization':f'Bearer {settings.token}'})
        restored=client.get('/api/runs/'+identity).json()
        assert restored['state']=='interrupted' and not restored['derived_datasets']
        assert restored['processing']['units'][0]['state']=='interrupted'


@pytest.mark.parametrize('namespace',['processing/private','processing/u0001','fastqc/raw'])
def test_tool_namespace_rejects_symlinks_before_creating_directories(tmp_path,namespace):
    from qualidock.store import ResultStores
    from qualidock.files import PathViolation
    stores=ResultStores(tmp_path/'results',[]);stores.start()
    try:
        run_id='f'*32;root=stores.allocate(run_id)
        outside=tmp_path/'outside';outside.mkdir()
        (root/namespace.split('/')[0]).symlink_to(outside,target_is_directory=True)
        with pytest.raises(PathViolation):stores.subdirectory(run_id,namespace,exist_ok=True)
        assert list(outside.iterdir())==[]
    finally:stores.close()


def test_tool_namespace_rejects_traversal_and_preserves_collisions(tmp_path):
    from qualidock.store import ResultStores
    from qualidock.files import PathViolation
    stores=ResultStores(tmp_path/'results',[]);stores.start()
    try:
        run_id='e'*32;stores.allocate(run_id)
        for namespace in ('../outside',str(tmp_path/'outside'),'.'):
            with pytest.raises(PathViolation):stores.subdirectory(run_id,namespace)
        unit=stores.subdirectory(run_id,'processing/u0001')
        marker=unit/'existing.txt';marker.write_text('preserve')
        with pytest.raises(FileExistsError):stores.subdirectory(run_id,'processing/u0001')
        assert marker.read_text()=='preserve'
    finally:stores.close()
