"""Genuine BCFtools + official MultiQC with duplicate basenames and sample IDs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from test_variant_real import TOOL, inputs, auth, hashes
from test_workspace import wait

MULTIQC=shutil.which(os.environ.get('QUALIDOCK_MULTIQC','multiqc'))
if os.environ.get('QUALIDOCK_REQUIRE_VARIANT_TESTS')=='1' and not (TOOL and MULTIQC):raise RuntimeError('Actual BCFtools and MultiQC required')
pytestmark=pytest.mark.skipif(not TOOL or not MULTIQC,reason='Genuine BCFtools + MultiQC required')


@pytest.mark.parametrize('per_sample',[False,True])
def test_official_mapping_values_and_unmodified_sources(inputs,per_sample):
    from dataclasses import replace
    settings,paths=inputs;settings=replace(settings,multiqc=MULTIQC)
    copies=[]
    for group in ['first','second']:
        target=paths['mixed'].parent/group/'same.vcf';target.parent.mkdir();target.write_bytes(paths['multisample'].read_bytes());copies.append(target)
    before=hashes(paths['mixed'].parent)
    with TestClient(create_app(settings)) as c:
        auth(c,settings)
        response=c.post('/api/runs',json={'mode':'bcftools','paths':list(map(str,copies)),'qc_options':{'multiqc':True,'per_sample':per_sample}})
        assert response.status_code==201,response.text
        run=wait(c,response.json()['id'],timeout=120)
        assert run['state']=='completed',run['error']
        assert run['qc']['multiqc_status']=='available'
        mapped=[run['report_input_map'][r['report']]['multiqc_name'] for r in run['qc']['results']]
        assert len(set(mapped))==2
        assert all(r['id'] in n for r,n in zip(run['qc']['results'],mapped))
        root=settings.output/run['id']
        structured=json.loads((root/'multiqc/multiqc_data/multiqc_data.json').read_text())
        raw=structured['report_saved_raw_data']['multiqc_bcftools_stats']
        for r in run['qc']['results']:
            name=run['report_input_map'][r['report']]['multiqc_name']
            assert raw[name]['number_of_samples']==2 and raw[name]['number_of_records']==4
            original=c.get(f'/api/runs/{run["id"]}/download',params={'path':r['report']})
            assert hashlib.sha256(original.content).hexdigest()==r['variant']['report_sha256']
            assert original.content==(root/r['report']).read_bytes()
        if per_sample:
            plot=structured['report_plot_data']['bcftools-stats-sequencing-depth']
            # Print bounded schema evidence if a qualified historical schema differs.
            observed={s for d in plot['datasets'] for s in d['samples']}
            expected={r['id']+' | '+s for r in run['qc']['results'] for s in ['alpha','beta']}
            assert observed==expected,(observed,expected)
        assert any(r['path']=='multiqc/multiqc_report.html' for r in run['reports'])
        evidence=Path('validation/variant-qualification')/('multiqc-'+run['tools']['multiqc']['version'])/str(per_sample)
        evidence.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/'multiqc/multiqc_data/multiqc_data.json',evidence/'genuine-data.json')
        (evidence/'provenance.json').write_text(json.dumps({'tools':run['tools'],'executions':run['executions'],'mapping':run['report_input_map'],'results':run['qc']['results']},indent=2))
    assert hashes(paths['mixed'].parent)==before


def test_failed_aggregation_retains_native_success_and_quarantines_html(inputs):
    from dataclasses import replace
    settings,paths=inputs
    wrapper=settings.output.parent/'failing-multiqc'
    wrapper.write_text(f'#!{sys.executable}\nimport os,sys\nif "--version" in sys.argv:os.execv({MULTIQC!r},[{MULTIQC!r},*sys.argv[1:]])\nfrom pathlib import Path\np=Path(sys.argv[sys.argv.index("--outdir")+1]);p.mkdir(exist_ok=True);(p/"multiqc_report.html").write_text("incomplete")\nsys.exit(1)\n');wrapper.chmod(0o700)
    settings=replace(settings,multiqc=str(wrapper))
    with TestClient(create_app(settings)) as c:
        auth(c,settings)
        response=c.post('/api/runs',json={'mode':'bcftools','paths':[str(paths['mixed'])],'qc_options':{'multiqc':True}})
        run=wait(c,response.json()['id'],timeout=120)
        assert run['state']=='partial' and run['sample_count']==1
        assert run['qc']['results'][0]['state']=='completed'
        assert not any(r['path'].startswith('multiqc/') for r in run['reports'])
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':run['qc']['results'][0]['report']}).status_code==200
        assert c.get(f'/api/runs/{run["id"]}/download',params={'path':'multiqc/multiqc_report.html'}).status_code==403
