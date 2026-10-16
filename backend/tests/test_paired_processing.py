"""Real FASTQ content through the synchronized selector and shared lifecycle.

Small synthetic record metadata covers edge cases; scientific engine reports are
never manufactured. The committed FastQC input fixture is also processed directly.
"""
import gzip
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from qualidock.app import create_app
from qualidock.config import Settings
from test_workspace import wait

FIXTURE = Path(__file__).parent/'fixtures/fastqc-0.13.0'


def settings(tmp_path):
    return Settings(roots=[tmp_path.resolve(),FIXTURE.resolve()], output=tmp_path/'results',
                    frontend=tmp_path/'frontend', token='paired-test',cpus=1,memory_mb=2048,
                    seqkit='missing-seqkit',fastqc='missing-fastqc',multiqc='missing-multiqc',allow_root=True)


def authenticated(config):
    client=TestClient(create_app(config));client.headers.update({'Authorization':f'Bearer {config.token}','X-QualiDock-Request':'1'})
    return client


def run(client, paths, options, mode='seqkit-filter'):
    response=client.post('/api/runs',json={'mode':mode,'paths':list(map(str,paths)), 'processing_options':options})
    assert response.status_code==201,response.text
    result=wait(client,response.json()['id'],timeout=30)
    return result


def paired(tmp_path, lengths=((4,4),(8,3),(3,8),(8,8)), ids=None, compressed=True):
    ids=ids or [f'read{i}' for i in range(len(lengths))]
    paths=[];content=[[],[]]
    for mate in (0,1):
        path=tmp_path/f'library_R{mate+1}.fastq'
        if compressed:path=Path(str(path)+'.gz')
        for identifier,values in zip(ids,lengths):
            sequence=b'ACGT'*(values[mate]//4)+b'ACGT'[:values[mate]%4]
            content[mate].append(b'@'+identifier.encode()+f'/{mate+1} description\n'.encode()+sequence+b'\n+\n'+b'I'*len(sequence)+b'\n')
        data=b''.join(content[mate]);path.write_bytes(gzip.compress(data,mtime=0) if compressed else data);paths.append(path)
    return paths,content


def output(config,result,index):
    path=config.output/result['id']/result['derived_datasets'][index]['path']
    return gzip.decompress(path.read_bytes()) if path.name.endswith('.gz') else path.read_bytes()


@pytest.mark.parametrize('compressed',[False,True])
@pytest.mark.parametrize('minimum,maximum,indices',[(4,8,[0,3]),(5,None,[3]),(9,None,[]),(1,3,[])])
def test_length_filter_both_mates_and_exact_original_bytes(tmp_path,compressed,minimum,maximum,indices):
    config=settings(tmp_path);paths,content=paired(tmp_path,compressed=compressed)
    original={p:p.read_bytes() for p in paths}
    with authenticated(config) as client:
        result=run(client,paths,{'preserve_pairs':True,'min_length':minimum,'max_length':maximum,'gzip':compressed})
        assert result['state']=='completed',result.get('error')
        unit=result['processing']['units'][0]
        assert unit['selection']['record_unit']=='read_pairs'
        assert (unit['selection']['input_records'],unit['selection']['retained_records'],unit['selection']['removed_records'])==(4,len(indices),4-len(indices))
        assert unit['output_validation']['pairs'][0]['state']=='passed'
        assert len(result['derived_datasets'])==2 and all(d['paired'] and d['records']==len(indices) for d in result['derived_datasets'])
        for mate in range(2):assert output(config,result,mate)==b''.join(content[mate][i] for i in indices)
        assert unit['selection']['input_bytes_read']==[p.stat().st_size for p in paths]
        assert all(e['tool']!='seqkit' for e in result['executions'])
    assert original=={p:p.read_bytes() for p in paths}


def test_existing_fastqc_input_fixture_filter_and_reuse_restart(tmp_path):
    config=settings(tmp_path);paths=sorted(FIXTURE.resolve().glob('*.fastq.gz'))
    original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    records=[]
    for path in paths:
        lines=gzip.decompress(path.read_bytes()).splitlines(keepends=True)
        records.append([b''.join(lines[n:n+4]) for n in range(0,len(lines),4)])
    indices=[n for n,reads in enumerate(zip(*records)) if all(len(r.splitlines()[1])>=151 for r in reads)]
    with authenticated(config) as client:
        result=run(client,paths,{'preserve_pairs':True,'min_length':151})
        assert result['state']=='completed',result.get('error')
        assert result['processing']['units'][0]['selection']['retained_records']==len(indices)
        assert all(output(config,result,mate)==b''.join(records[mate][n] for n in indices) for mate in (0,1))
    with authenticated(config) as client:
        base=f"/api/runs/{result['id']}"
        draft=client.get(base+'/datasets').json()
        assert len(draft['input_datasets'])==2 and all(p['paired'] for p in draft['input_pairing'])
        config_saved=client.get(base+'/configuration').json()
        assert config_saved['processing_options']['preserve_pairs'] is True
        response=client.post('/api/runs',json=config_saved);assert response.status_code==201,response.text
        rerun=wait(client,response.json()['id'],timeout=30)
        assert rerun['state']=='completed' and rerun['id']!=result['id']
        assert all(output(config,rerun,mate)==output(config,result,mate) for mate in (0,1))
    assert original=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


@pytest.mark.parametrize('change',['order','missing','corrupt'])
def test_mismatched_or_malformed_sources_never_publish(tmp_path,change):
    config=settings(tmp_path);paths,content=paired(tmp_path,compressed=False)
    if change=='order':paths[1].write_bytes(b''.join(reversed(content[1])))
    elif change=='missing':paths[1].write_bytes(b''.join(content[1][:-1]))
    else:paths[1].write_bytes(b'@bad/2\nACGT\n+\nI\n')
    with authenticated(config) as client:
        result=run(client,paths,{'preserve_pairs':True,'min_length':1})
        assert result['state']=='failed' and result['derived_datasets']==[]
        assert not any(e['tool']=='QualiDock synchronized FASTQ selector' for e in result['executions'])
        assert client.get(f"/api/runs/{result['id']}/download",params={'path':'processing/u0001/processed_R1.fastq.gz'}).status_code==403


@pytest.mark.parametrize('identifiers,indices,missing',[
    (['read3/2','read0/1','read0/2','read0'],[0,3],[]),
    (['read1','absent'],[1],['absent']),
    (['read','READ0','read00'],[],['read','READ0','read00']),
])
def test_identifier_extraction_normalizes_suffixes_without_fuzzy_matches(tmp_path,identifiers,indices,missing):
    config=settings(tmp_path);paths,content=paired(tmp_path)
    original={p:p.read_bytes() for p in paths}
    with authenticated(config) as client:
        result=run(client,paths,{'preserve_pairs':True,'identifiers':identifiers},mode='seqkit-extract')
        assert result['state']=='completed',result.get('error')
        selected=result['processing']['units'][0]['selection']
        assert selected['retained_records']==len(indices) and selected['missing_identifiers']==missing
        assert selected['matched_identifiers']==len(indices)
        assert all(output(config,result,mate)==b''.join(content[mate][n] for n in indices) for mate in (0,1))
        assert bool(result['warnings'])==bool(missing)
        assert result['processing']['units'][0]['output_validation']['pairs'][0]['state']=='passed'
    assert original=={p:p.read_bytes() for p in paths}


def test_duplicate_matching_source_identifiers_fail_instead_of_publishing_duplicates(tmp_path):
    config=settings(tmp_path);paths,_=paired(tmp_path,ids=['dup','other','dup','unique'])
    with authenticated(config) as client:
        result=run(client,paths,{'preserve_pairs':True,'identifiers':['dup/1','dup/2']},mode='seqkit-extract')
        assert result['state']=='failed' and result['derived_datasets']==[]
        assert 'ambiguous' in result['error']
        assert 'more than once' in result['processing']['units'][0]['error']
        assert not any(p['path'].startswith('processing/u0001/') for p in result['reports'])


def test_wrapped_records_and_literal_special_identifiers_are_preserved(tmp_path):
    config=settings(tmp_path);paths,content=paired(tmp_path,ids=['x.+[a]','other','third','fourth'])
    for mate,path in enumerate(paths):
        content[mate][0]=content[mate][0].replace(b'ACGT\n+\nIIII',b'AC\nGT\n+\nII\nII')
        path.write_bytes(gzip.compress(b''.join(content[mate]),mtime=0))
    with authenticated(config) as client:
        result=run(client,paths,{'preserve_pairs':True,'identifiers':['x.+[a]/2']},mode='seqkit-extract')
        assert result['state']=='completed',result.get('error')
        assert all(output(config,result,mate)==content[mate][0] for mate in (0,1))
