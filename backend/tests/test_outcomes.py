"""Synthetic file metadata/tool doubles; genuine collision execution is tested separately."""
import json
from pathlib import Path
import time
from fastapi.testclient import TestClient
from qualidock.app import create_app
from test_workspace import wait, start


def test_same_basename_inputs_keep_separate_artifacts_and_source_mapping(client,setup):
    settings,root=setup
    paths=[]
    for folder in ['study a','study b']:
        directory=root/folder;directory.mkdir()
        for read in [1,2]:
            path=directory/f'sample_R{read}_001.fastq';path.write_text('@read\nACGT\n+\nIIII\n');paths.append(path)
    run=wait(client,start(client,root,paths=list(map(str,paths)))['id'])
    assert run['state']=='completed',run['error']
    records=run['input_outcomes']
    assert len(records)==4 and all(record['state']=='completed' for record in records)
    assert len({record['report'] for record in records})==4
    metrics=client.get(f"/api/runs/{run['id']}/metrics").json()
    assert len(metrics['samples'])==4
    for sample in metrics['samples']:
        mapped=run['report_input_map'][sample['id']]
        assert mapped['path'] in list(map(str,paths))
        assert Path(mapped['path']).name==sample['name']
        assert client.get(f"/api/runs/{run['id']}/download",params={'path':sample['id']}).status_code==200
    assert '--dirs' in run['executions'][-1]['argv']
    draft=client.get(f"/api/runs/{run['id']}/configuration").json()
    rerun=client.post('/api/runs',json={key:draft[key] for key in ['paths','mode','input_pairing','sample_groups','output_root','rerun_of']})
    assert rerun.status_code==201
    rerun=wait(client,rerun.json()['id'])
    assert [r['id'] for r in rerun['input_outcomes']]==[r['id'] for r in records]
    assert rerun['id']!=run['id']


def test_mixed_failures_have_actionable_per_input_states(client,setup):
    _,root=setup
    broken=root/'broken.fastq';broken.write_text('invalid')
    run=wait(client,start(client,root)['id'])
    assert run['state']=='partial'
    results={Path(record['path']).name:record for record in run['input_outcomes']}
    assert results['broken.fastq']['state']=='failed'
    assert results['broken.fastq']['error'] and results['broken.fastq']['exit_code']==1
    assert all(results[f'sample_R{read}_001.fastq']['state']=='completed' for read in [1,2])


def test_cancel_preserves_completed_batches_and_marks_unfinished_inputs(client,setup):
    _,root=setup
    paths=[]
    for name in [*[f'good_{n}.fastq' for n in range(8)],'slow.fastq']:
        path=root/name;path.write_text('@r\nACGT\n+\nIIII\n');paths.append(str(path))
    run=start(client,root,mode='fastqc',paths=paths)
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        current=client.get(f"/api/runs/{run['id']}").json()
        if sum(record['state']=='completed' for record in current['input_outcomes'])==8:break
        time.sleep(.02)
    else:raise AssertionError(current)
    client.post(f"/api/runs/{run['id']}/cancel")
    run=wait(client,run['id'])
    assert sum(r['state']=='completed' for r in run['input_outcomes'])==8
    assert run['input_outcomes'][-1]['state']=='cancelled'
    assert len(client.get(f"/api/runs/{run['id']}/metrics").json()['samples'])==8


def test_restart_marks_only_unfinished_file_outcomes_interrupted(setup):
    settings,root=setup
    headers={'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'}
    with TestClient(create_app(settings),headers=headers) as client:
        run=wait(client,start(client,root,mode='fastqc')['id'])
    path=settings.output/run['id']/'manifest.json';saved=json.loads(path.read_text())
    saved['state']='running';saved['input_outcomes'][1]['state']='unknown';path.write_text(json.dumps(saved))
    with TestClient(create_app(settings),headers=headers) as client:
        restored=client.get(f"/api/runs/{run['id']}").json()
        assert restored['state']=='interrupted'
        assert [r['state'] for r in restored['input_outcomes']]==['completed','interrupted']
