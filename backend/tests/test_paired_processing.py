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
@pytest.mark.parametrize('mode',['seqkit-filter','seqkit-extract'])
def test_mismatched_or_malformed_sources_never_publish(tmp_path,change,mode):
    config=settings(tmp_path);paths,content=paired(tmp_path,compressed=False)
    if change=='order':paths[1].write_bytes(b''.join(reversed(content[1])))
    elif change=='missing':paths[1].write_bytes(b''.join(content[1][:-1]))
    else:paths[1].write_bytes(b'@bad/2\nACGT\n+\nI\n')
    with authenticated(config) as client:
        value={'preserve_pairs':True,'min_length':1}
        if mode=='seqkit-extract':value['identifiers']=['read0']
        result=run(client,paths,value,mode=mode)
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


def test_exact_command_and_capability_validation():
    from qualidock.processing import options,seqkit_command,check_features
    value=options('seqkit-sample',{'count':7,'seed':73})
    argv=seqkit_command('/tools/seqkit','seqkit-sample',Path('/input x.fastq.gz'),Path('/output.fastq.gz'),1,value,Path('/ids'))
    assert argv[:2]==['/tools/seqkit','sample2'] and '--two-pass' in argv and '--proportion' not in argv
    assert argv[argv.index('--number')+1]=='7' and argv[argv.index('--rand-seed')+1]=='73'
    assert argv[argv.index('--line-width')+1]=='0'  # sample2 otherwise wraps FASTQ in SeqKit 2.14
    assert argv[-1]=='/input x.fastq.gz'
    for bad in (0,-1,True,1.5,9007199254740992):
        with pytest.raises(ValueError):options('seqkit-sample',{'count':bad})
    with pytest.raises(ValueError):options('seqkit-filter',{'count':3})
    with pytest.raises(ValueError,match='2.14'):check_features('seqkit-sample',value,{'seqkit':{'version':'2.12.0'}})
    check_features('seqkit-sample',value,{'seqkit':{'version':'2.14.0'}})


# Every test below invokes the genuine externally provisioned SeqKit binary.
import json
import os
import shutil
SEQKIT=shutil.which(os.environ.get('QUALIDOCK_SEQKIT','seqkit'))


@pytest.mark.skipif(not SEQKIT,reason='Actual SeqKit 2.14 required')
@pytest.mark.parametrize('paired_input',[False,True])
def test_exact_count_matches_independent_reservoir_indices(tmp_path,paired_input):
    from dataclasses import replace
    config=replace(settings(tmp_path),seqkit=SEQKIT)
    paths=sorted(FIXTURE.resolve().glob('*.fastq.gz'))[:2 if paired_input else 1]
    original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    records=[]
    for p in paths:
        lines=gzip.decompress(p.read_bytes()).splitlines(keepends=True)
        records.append([b''.join(lines[n:n+4]) for n in range(0,len(lines),4)])
    expected=json.loads((Path(__file__).parent/'fixtures/paired-processing/exact-sampling.json').read_text())
    with authenticated(config) as client:
        for case in expected:
            result=run(client,paths,{'count':case['count'],'seed':case['seed']},mode='seqkit-sample')
            assert result['state']=='completed',result.get('error')
            assert all(output(config,result,m)==b''.join(records[m][i] for i in case['indices']) for m in range(len(paths)))
            selected=result['processing']['units'][0]['selection']
            assert selected['retained_records']==case['count'] and selected['removed_records']==400-case['count']
            assert selected['record_unit']==('read_pairs' if paired_input else 'reads')
            assert all(d['paired']==paired_input for d in result['derived_datasets'])
        again=run(client,paths,{'count':7,'seed':73},mode='seqkit-sample')
        assert all(output(config,again,m)==b''.join(records[m][i] for i in expected[1]['indices']) for m in range(len(paths)))
        full=run(client,paths,{'count':400,'gzip':False},mode='seqkit-sample')
        assert full['state']=='completed' and all(output(config,full,m)==b''.join(records[m]) for m in range(len(paths)))
        over=run(client,paths,{'count':401},mode='seqkit-sample')
        assert over['state']=='failed' and not over['derived_datasets']
        assert 'only 400' in over['error'] and not any(e['tool']=='seqkit' for e in over['executions'])
    assert original=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


@pytest.mark.skipif(not SEQKIT,reason='Actual SeqKit 2.14 required')
def test_exact_count_partial_failure_and_empty_input(tmp_path):
    from dataclasses import replace
    config=replace(settings(tmp_path),seqkit=SEQKIT)
    paths,content=paired(tmp_path,compressed=False)
    single=tmp_path/'independent.fastq';single.write_bytes(content[0][0])
    with authenticated(config) as client:
        result=run(client,[*paths,single],{'count':2},mode='seqkit-sample')
        assert result['state']=='partial' and len(result['derived_datasets'])==2
        assert all(d['paired'] and d['records']==2 for d in result['derived_datasets'])
        assert 'only 1' in result['error']
        single.write_bytes(b'')
        empty=run(client,[single],{'count':1},mode='seqkit-sample')
        assert empty['state']=='failed' and not empty['derived_datasets'] and 'only 0' in empty['error']


def test_partial_extraction_publishes_only_unambiguous_pair(tmp_path):
    config=settings(tmp_path)
    bad=tmp_path/'bad';good=tmp_path/'good';bad.mkdir();good.mkdir()
    paths,_=paired(bad,ids=['dup','other','dup','unique'])
    valid,content=paired(good,ids=['dup','other','third','unique'])
    with authenticated(config) as client:
        result=run(client,[*paths,*valid],{'preserve_pairs':True,'identifiers':['dup']},mode='seqkit-extract')
        assert result['state']=='partial' and len(result['derived_datasets'])==2
        assert all(d['source'] in list(map(str,valid)) for d in result['derived_datasets'])
        assert all(output(config,result,m)==content[m][0] for m in (0,1))
        assert not any(r['path'].startswith('processing/u0001/') for r in result['reports'])


def test_selector_rejects_replaced_sources_existing_outputs_and_symlink_parents(tmp_path):
    from qualidock.paired_reads import execute
    from qualidock.integrity import snapshot
    paths,_=paired(tmp_path,compressed=False)
    original={p:p.read_bytes() for p in paths}
    target=tmp_path/'target';target.mkdir()
    config={'inputs':list(map(str,paths)), 'snapshots':[snapshot(p.stat()) for p in paths],
            'outputs':[str(target/f'mate{m}.fastq') for m in (1,2)],
            'gzip':False,'min_length':1,'max_length':None,'result':str(target/'selection.json')}
    # Writing to an existing file, including a source itself, must never truncate it.
    for candidate in (paths[0],target/'already.fastq'):
        if candidate not in paths:candidate.write_bytes(b'keep')
        before=candidate.read_bytes()
        with pytest.raises((ValueError,FileExistsError)):
            execute({**config,'outputs':[str(candidate),config['outputs'][1]]})
        assert candidate.read_bytes()==before
    alias=tmp_path/'alias';alias.symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'):
        execute({**config,'outputs':[str(alias/'left.fastq'),str(alias/'right.fastq')]})
    saved=config['snapshots'][0]
    config['snapshots'][0]={**saved,'size':saved['size']+1}
    with pytest.raises(ValueError,match='changed after full validation'):execute(config)
    assert original=={p:p.read_bytes() for p in paths}
    assert not (target/'mate1.fastq').exists()


def test_cancel_actual_synchronized_selector_never_publishes(tmp_path):
    import time
    config=settings(tmp_path)
    # Synthetic lifecycle stress input, not a scientific result or performance benchmark.
    paths,_=paired(tmp_path,lengths=[(10000,10000)]*200,compressed=False)
    original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with authenticated(config) as client:
        response=client.post('/api/runs',json={'mode':'seqkit-filter','paths':list(map(str,paths)),
                                              'processing_options':{'preserve_pairs':True,'min_length':1}})
        assert response.status_code==201,response.text
        identifier=response.json()['id'];deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            result=client.get(f'/api/runs/{identifier}').json()
            commands=result.get('executions',[])
            if commands and commands[-1]['tool']=='QualiDock synchronized FASTQ selector' and commands[-1].get('exit_code') is None and identifier in client.app.state.manager.executor.processes:
                break
            assert result['state'] in {'queued','running'},result
            time.sleep(.005)
        else:raise AssertionError('The actual selector did not start')
        assert client.post(f'/api/runs/{identifier}/cancel').status_code==200
        result=wait(client,identifier,timeout=30)
        assert result['state']=='cancelled' and not result['derived_datasets']
        assert client.get(f'/api/runs/{identifier}/download',params={'path':'processing/u0001/processed_R1.fastq.gz'}).status_code==403
    with authenticated(config) as client:
        restored=client.get(f'/api/runs/{identifier}').json()
        assert restored['state']=='cancelled' and not restored['derived_datasets']
    assert original=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def test_record_capture_is_bounded_even_with_excessive_empty_wrapping(monkeypatch):
    import io
    from qualidock import integrity
    # Small injected support bound exercises the same byte limit without a large fixture.
    monkeypatch.setattr(integrity,'MAX_CAPTURE',64)
    data=b'@wrapped/1\n'+b'\n'*100+b'ACGT\n+\nIIII\n'
    with pytest.raises(integrity.Unsupported,match='representation'):
        integrity.record(io.BytesIO(data),raw=[])
    assert integrity.record(io.BytesIO(data))[1]==4  # read-only scanner contract is unchanged
