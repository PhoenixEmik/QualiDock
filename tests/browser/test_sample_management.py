"""Create/review/rerun UI workflow using genuine FastQC fixture inputs."""
import json
from pathlib import Path
import re

from test_report_viewer import browser, workspace, open_run, playwright, INPUTS

expect=playwright.expect


def test_manual_pair_output_rename_rerun_and_group_analytics(workspace,browser):
    paths=[str(path) for path in sorted(INPUTS.glob('*.fastq.gz'))]
    with workspace.api() as client:
        config=client.get('api/config').json()
        project=next(location['path'] for location in config['output_locations'] if not location['default'])
    with browser.new_context(viewport={'width':1440,'height':1100}) as context:
        page=context.new_page()
        open_run(page,workspace,'Browser combined')
        page.get_by_role('button',name='Workspace',exact=True).click()
        page.get_by_label('Select sample coverage',exact=True).check()
        page.get_by_role('button',name='New analysis',exact=True).click()
        editor=page.get_by_role('region',name='Sample and pairing editor',exact=True)
        expect(editor).to_be_visible()
        page.get_by_label('Analysis name',exact=True).fill('Browser managed sample')
        page.get_by_role('button',name=re.compile('^FastQC only')).click()
        editor.get_by_role('button',name='Confirm pair',exact=True).click()
        expect(editor.locator('.metadata-pairs')).to_contain_text('confirmed')
        editor.get_by_role('button',name=re.compile('^Remove pairing')).click()
        editor.get_by_text('Assign or correct a pair',exact=True).click()
        editor.get_by_label('Assign R1 file',exact=True).select_option(paths[1])
        editor.get_by_label('Assign R2 file',exact=True).select_option(paths[0])
        editor.get_by_label('Pair lane',exact=True).fill('L009')
        editor.get_by_label('Pair chunk',exact=True).fill('003')
        editor.get_by_role('button',name='Assign pair',exact=True).click()
        editor.get_by_label(re.compile('^Sample name ')).first.fill('User library')
        page.get_by_label('Persistent results location',exact=True).select_option(project)
        expect(page.get_by_role('region',name='Output directory',exact=True)).to_contain_text(project)
        Path('validation').mkdir(exist_ok=True)
        page.screenshot(path='validation/native-sample-setup'+workspace.settings.prefix.replace('/','-')+'.png',full_page=True)
        with page.expect_response(lambda response:response.request.method=='POST' and response.url.split('?')[0].endswith('/api/runs')) as response:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert response.value.status==201,response.value.text()
        created=response.value.json()
        with workspace.api() as client:
            completed=workspace.finish(client,created)
        assert completed['state']=='completed'
        assert completed['output_root']==project
        assert completed['sample_groups'][0]['display_name']=='User library'
        assert all(record['source']=='manual' and record['lane']=='L009' and record['chunk']=='003' for record in completed['input_pairing'])
        assert next(record for record in completed['input_pairing'] if record['read']=='R1')['path']==paths[1]
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        groups=page.get_by_role('region',name='Saved sample groups',exact=True)
        expect(groups).to_contain_text('User library')
        page.locator('.analytics-selection summary').click()
        page.get_by_role('button',name='Clear Selection',exact=True).click()
        groups.get_by_label('Select group User library',exact=True).check()
        expect(page.locator('.analytics-selection summary')).to_contain_text('2 of 2 selected')
        groups.locator('summary').click()
        groups.get_by_role('button',name='Inspect read',exact=True).first.click()
        expect(page.get_by_label('Select FASTQ sample',exact=True)).to_be_visible()
        page.get_by_role('button',name='R1 / R2 Comparison',exact=True).click()
        expect(page.get_by_label('Select confirmed pair',exact=True)).to_contain_text('L009')
        page.get_by_role('button',name='Analyses',exact=True).click()
        page.get_by_role('button',name='Rename Browser managed sample',exact=True).click()
        page.get_by_label('Analysis display name',exact=True).fill('Renamed managed sample')
        page.get_by_role('button',name='Save name',exact=True).click()
        expect(page.get_by_role('button',name='Open Renamed managed sample',exact=True)).to_be_visible()
        page.get_by_label('Search analyses',exact=True).fill('Renamed managed')
        page.get_by_label('Filter analysis workflow',exact=True).select_option('fastqc')
        page.get_by_label('Filter exact analysis state',exact=True).select_option('completed')
        page.get_by_label('Sort analyses',exact=True).select_option('finished-desc')
        expect(page.get_by_role('region',name='Analysis list',exact=True).locator('tbody tr')).to_have_count(1)
        page.get_by_role('button',name='Rerun Renamed managed sample',exact=True).click()
        expect(page.get_by_label('Analysis name',exact=True)).to_have_value('Renamed managed sample · rerun')
        expect(page.get_by_label('Persistent results location',exact=True)).to_have_value(project)
        expect(editor).to_contain_text('manual')
        expect(editor).to_contain_text('L009')
        with page.expect_response(lambda response:response.request.method=='POST' and response.url.split('?')[0].endswith('/api/runs')) as response:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert response.value.status==201,response.value.text()
        rerun=response.value.json()
        assert rerun['id']!=created['id'] and rerun['rerun_of']==created['id']
        with workspace.api() as client:
            rerun=workspace.finish(client,rerun)
            assert rerun['state']=='completed'
            assert client.get(f"api/runs/{created['id']}").json()['name']=='Renamed managed sample'
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('document.documentElement.scrollWidth <= innerWidth',timeout=3000)
