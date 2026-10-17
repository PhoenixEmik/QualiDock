"""Shared I/O contracts; numerical values come from genuine MultiQC fixtures."""
import asyncio
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest
from qualidock import multiqc
from qualidock.metrics import parse_multiqc

FIXTURES=Path(__file__).parent/'fixtures/multiqc'


@pytest.mark.parametrize('version',['1.25.1','1.35'])
def test_summary_matches_genuine_structured_values(tmp_path,version):
    destination=tmp_path/'multiqc/multiqc_data';destination.mkdir(parents=True)
    source=FIXTURES/version/'general-stats.json'
    shutil.copyfile(source,destination/'multiqc_data.json')
    assert asyncio.run(multiqc.summary(tmp_path))==parse_multiqc(source)


def test_missing_invalid_and_symlink_structured_results(tmp_path):
    assert asyncio.run(multiqc.summary(tmp_path))['status']=='missing'
    folder=tmp_path/'multiqc/multiqc_data';folder.mkdir(parents=True)
    target=folder/'multiqc_data.json';target.write_text('not JSON')
    assert asyncio.run(multiqc.summary(tmp_path))['status']=='invalid'
    target.unlink();target.symlink_to(FIXTURES.resolve()/'1.35/general-stats.json')
    assert asyncio.run(multiqc.summary(tmp_path))['status']=='invalid'


def test_source_mapping_requires_unique_observed_name(tmp_path):
    folder=tmp_path/'multiqc/multiqc_data';folder.mkdir(parents=True)
    # Synthetic source-path metadata over unchanged genuine General Statistics.
    value=json.loads((FIXTURES/'1.35/general-stats.json').read_text())
    reports=[tmp_path/'first.json',tmp_path/'second.json']
    value['report_data_sources']={'fastp':{'all':{'coverage_R1':str(reports[0]),'coverage_R2':str(reports[1])}}}
    path=folder/'multiqc_data.json';path.write_text(json.dumps(value))
    summary=asyncio.run(multiqc.summary(tmp_path))
    assert asyncio.run(multiqc.report_names(tmp_path,reports,summary))=={'first.json':'coverage_R1','second.json':'coverage_R2'}
    value['report_data_sources']['fastp']['all']['coverage_R2']=str(reports[0]);path.write_text(json.dumps(value))
    assert asyncio.run(multiqc.report_names(tmp_path,reports,summary))=={'first.json':None,'second.json':None}


@pytest.mark.parametrize('depth',[1,3])
def test_command_preserves_workflow_options_and_literal_paths(tmp_path,depth):
    calls=[]
    class Stores:
        def subdirectory(self,identifier,name,**kwargs):(tmp_path/name).mkdir(**kwargs)
    async def command(run,tool,argv,directory):
        calls.append((tool,argv,directory));return 0  # Intentionally no output: test missing-report diagnostic, not QC.
    manager=SimpleNamespace(directory=lambda _:tmp_path,stores=Stores(),command=command,cancelled=set())
    run={'id':'test','tools':{'multiqc':{'executable':'/tools/multiqc'}}}
    report=tmp_path/'a $(literal); report.json'
    problem=asyncio.run(multiqc.execute(manager,run,[report],options=['--dirs','--dirs-depth',str(depth),'--fullnames'],config={'use_filename_as_sample_name':['fastp']}))
    assert problem=='MultiQC did not produce an HTML report.'
    tool,argv,directory=calls[0]
    assert tool=='multiqc' and directory==tmp_path and argv[0]=='/tools/multiqc'
    assert argv[argv.index('--dirs-depth')+1]==str(depth) and '--no-version-check' in argv
    assert (tmp_path/'multiqc-inputs.txt').read_text()==str(report)+'\n'
    assert json.loads(Path(argv[argv.index('--config')+1]).read_text())=={'use_filename_as_sample_name':['fastp']}
    with pytest.raises(ValueError,match='newlines'):
        asyncio.run(multiqc.execute(manager,run,[tmp_path/'unsafe\nreport.json']))


def test_execution_failure_and_cancellation_diagnostics(tmp_path):
    class Stores:
        def subdirectory(self,identifier,name,**kwargs):(tmp_path/name).mkdir(**kwargs)
    async def command(*args):return 9  # Deliberate lifecycle failure, no scientific output.
    manager=SimpleNamespace(directory=lambda _:tmp_path,stores=Stores(),command=command,cancelled=set())
    run={'id':'test','tools':{'multiqc':{'executable':'/tools/multiqc'}}}
    assert 'code 9' in asyncio.run(multiqc.execute(manager,run,[]))
    manager.cancelled.add('test')
    assert asyncio.run(multiqc.execute(manager,run,[])) is None


@pytest.mark.parametrize('value',[[], {'report_saved_raw_data':[]}, {'report_saved_raw_data':{'multiqc_rseqc_infer_experiment':[]}}])
def test_unknown_alignment_raw_schema_never_invents_sample_names(tmp_path,value):
    path=tmp_path/'multiqc/multiqc_data/multiqc_data.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps(value))
    assert asyncio.run(multiqc.alignment_sample_names(tmp_path,'rseqc-infer'))==set()
