"""Read actual bounded FASTQ bytes and enforce the existing authorization boundary."""
import gzip
import hashlib
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.inspector import MAX_RECORD, MAX_DECOMPRESSED, MAX_COMPRESSED, MAX_RESPONSE
from test_processing_real import FASTP, FIXTURE, settings, auth, submit


def inspect(client, paths, **options):
    return client.post('/api/inspector',json={'paths':list(map(str,paths)),**options})


@pytest.mark.parametrize('compressed',[False,True])
def test_actual_reads_and_bounds(client,setup,compressed):
    _,root=setup
    path=root/('reads.fq.gz' if compressed else 'reads.fq')
    content=b'@read/1 description\nACG\nTN\n+\nI!J\n#K\n'*25
    path.write_bytes(gzip.compress(content) if compressed else content)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    for count in (1,5,20):
        response=inspect(client,[path],count=count)
        assert response.status_code==200 and len(response.content)<=MAX_RESPONSE
        data=response.json(); file=data['files'][0]
        assert len(file['records'])==count and file['quality_encoding']=='not_inferred'
        assert file['records'][0]=={'ordinal':1,'identifier':'read/1 description','length':5,'sequence':'ACGTN','quality':'I!J#K'}
        assert file['compressed_bytes_read']<=MAX_COMPRESSED and file['decompressed_bytes_read']<=MAX_DECOMPRESSED
    for count in (0,21,True,1.5): assert inspect(client,[path],count=count).status_code==422
    assert inspect(client,[path,path]).status_code==400
    assert before==hashlib.sha256(path.read_bytes()).hexdigest()
    assert client.get('/api/runs').json()==[]


@pytest.mark.parametrize('content,status',[(b'','empty'),(b'@a\nAC\n+\nI\n','unavailable'),(b'@a\n!C\n+\nII\n','unavailable'),
    (b'@a\n'+b'A'*(MAX_RECORD+1)+b'\n+\n','record_too_large'),(b'@a\n'+b'\n'*(MAX_RECORD+1),'record_too_large')])
def test_malformed_and_gzip_bombs(client,setup,content,status):
    _,root=setup; path=root/'inspect.fastq.gz'; path.write_bytes(gzip.compress(content))
    response=inspect(client,[path]); assert response.status_code==200
    assert response.json()['files'][0]['status']==status
    assert response.json()['files'][0]['records']==[]


def test_preview_mates_are_not_full_validation(client,setup):
    _,root=setup; left=root/'sample_R1_001.fastq';right=root/'sample_R2_001.fastq'
    left.write_text('@read/1\nAC\n+\nII\n@later/1\nAC\n+\nII\n')
    right.write_text('@read/2\nAC\n+\nII\n@different/2\nAC\n+\nII\n')
    result=inspect(client,[left,right],paired=True,count=1).json()
    assert result['pairs']==[{'ordinal':1,'status':'match'}]
    assert 'never whole-file' in result['pairing_scope']
    assert inspect(client,[left,right],paired=True).json()['pairs'][1]['status']=='mismatch'
    assert inspect(client,[left],paired=True).status_code==400
    assert inspect(client,[left,right]).json()['pairs']==[]


def test_access_and_no_read_data_logging(client,setup,tmp_path):
    config,root=setup; path=root/'sample_R1_001.fastq'
    assert inspect(client,[root/'../secret.fastq']).status_code==403
    outside=tmp_path/'outside.fastq';outside.write_text('@private_identifier\nAC\n+\nII\n')
    link=root/'link.fastq';link.symlink_to(outside)
    assert inspect(client,[link]).status_code==403
    link.unlink();link.symlink_to(path)
    assert inspect(client,[link]).status_code==403
    assert inspect(client,[outside]).status_code==403
    assert inspect(client,[root/'missing.fastq']).status_code==403
    assert inspect(client,[root]).status_code==403
    assert inspect(client,[path],input_datasets=[{'run_id':'a'*32,'dataset_id':'forged'}]).status_code==404
    client.headers.pop('Authorization')
    assert inspect(client,[path]).status_code==401
    client.headers['Authorization']='Bearer '+config.token
    client.headers.pop('X-QualiDock-Request')
    assert inspect(client,[path]).status_code==403
    assert not list(config.output.rglob('analysis.log'))


@pytest.mark.skipif(not FASTP,reason='Genuine fastp required')
def test_registered_derived_only_and_restart(tmp_path):
    config=settings(tmp_path)
    with TestClient(create_app(config)) as client:
        auth(client,config)
        run=submit(client,'fastp',sorted(FIXTURE.glob('*.fastq.gz')),{'compare_qc':False})
    # Only configured fixture roots, not the output's parent.
    config.roots=[FIXTURE.resolve()]
    with TestClient(create_app(config)) as client:
        auth(client,config)
        paths=[config.output/run['id']/d['path'] for d in run['derived_datasets']]
        refs=[{'run_id':run['id'],'dataset_id':d['id']} for d in run['derived_datasets']]
        before=(config.output/run['id']/'manifest.json').read_bytes()
        assert inspect(client,paths).status_code==403
        response=inspect(client,paths,input_datasets=refs,paired=True)
        assert response.status_code==200 and all(r['status']=='match' for r in response.json()['pairs'])
        assert all(len(f['records'])==5 for f in response.json()['files'])
        sibling=paths[0].parent/'unregistered.fastq';sibling.write_text('@secret\nAC\n+\nII\n')
        assert inspect(client,[sibling],input_datasets=[refs[0]]).status_code in {400,403}
        assert before==(config.output/run['id']/'manifest.json').read_bytes()
        paths[0].write_bytes(b'changed')
        assert inspect(client,[paths[0]],input_datasets=[refs[0]]).status_code==403
