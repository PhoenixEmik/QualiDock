"""Real processing through the production UI; no replacement QC or fabricated metrics."""
import json
import os
from pathlib import Path
import secrets
import shutil
import pytest
from test_report_viewer import workspace, browser, playwright


def test_select_fastqs_process_compare_download_and_restart(workspace,browser):
    assert shutil.which('fastp') and shutil.which('seqkit'), 'Provision actual processing tools before browser acceptance'
    page=browser.new_page(viewport={'width':1480,'height':1000})
    page.goto(workspace.base+'?processing='+secrets.token_hex(4)+'#token='+workspace.settings.token)
    nav=page.get_by_role('navigation',name='Main navigation')
    for label in ('Workspace','QC & Analysis','Read Processing','Results'):
        playwright.expect(nav.get_by_role('button',name=label,exact=True)).to_be_visible()
    # The existing browser is used directly, without a separate form for paths.
    page.get_by_role('button',name='Files',exact=True).click()
    page.get_by_label('Select all visible input files').check()
    nav.get_by_role('button',name='Read Processing',exact=True).click()
    setup=page.get_by_role('region',name='Read processing setup')
    playwright.expect(setup.get_by_text('2 FASTQ files selected',exact=True)).to_be_visible()
    setup.get_by_text('Advanced settings',exact=True).click()
    setup.get_by_label('Analysis name (optional)').fill('Browser fastp processing')
    setup.get_by_label('Generate combined MultiQC report').check()
    setup.get_by_role('button',name='Run processing',exact=True).focus()
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/runs')) as created:
        setup.get_by_role('button',name='Run processing',exact=True).press('Enter')
    assert created.value.status==201,created.value.text()
    with workspace.api() as api:
        run=workspace.finish(api,created.value.json())
        metrics=api.get(f"api/runs/{run['id']}/metrics").json()
    assert run['processing']['options']['multiqc'] is True
    assert any(report['path']=='multiqc/multiqc_report.html' for report in run['reports'])
    # Backend completion is not proof React has received its final SSE revision.
    playwright.expect(page.locator('.analysis-detail-heading .state')).to_have_text('completed',timeout=20000)
    page.get_by_role('tab',name='QC metrics',exact=True).click()
    result=page.get_by_role('region',name='Processing results')
    playwright.expect(result.get_by_role('heading',name='Before / after processing',exact=True)).to_be_visible()
    playwright.expect(result.locator('.processing-charts .quality-chart')).to_have_count(2)
    before=run['processing']['units'][0]['fastp']['summary']['before_filtering']
    assert result.locator('tbody tr').filter(has_text='Total reads').first.locator('td').first.inner_text()==f"{before['total_reads']:,}"
    for chart in result.locator('.quality-chart').all():
        canvas=chart.locator('canvas').first
        playwright.expect(canvas).to_be_visible()
        page.wait_for_function('(element)=>element.getBoundingClientRect().width>300',arg=canvas.element_handle())
    directory=Path('validation');directory.mkdir(exist_ok=True)
    suffix=workspace.settings.prefix.replace('/','-') or '-root'
    page.screenshot(path=str(directory/f'native-processing-comparison{suffix}.png'),full_page=True)
    raw=result.locator('details.qc-raw-data').first
    raw.locator('summary').click()
    source=next(sample for sample in metrics['samples'] if sample['id']==run['processing']['units'][0]['raw_qc'][0]['report'])
    module=next(module for module in source['modules'] if module['name']=='Per base sequence quality')
    playwright.expect(raw.locator('tbody tr').first.locator('td')).to_have_text(module['rows'][0])
    with page.expect_download() as downloaded:
        result.get_by_role('link',name='Download FASTQ',exact=True).first.click()
    import hashlib
    assert hashlib.sha256(Path(downloaded.value.path()).read_bytes()).hexdigest()==run['derived_datasets'][0]['sha256']
    page.get_by_role('tab',name='Reports',exact=True).click()
    playwright.expect(page.get_by_label('Select HTML report')).to_have_value('multiqc/multiqc_report.html')
    workspace.stop();workspace.start()
    page.goto(workspace.base+'?restart='+secrets.token_hex(4)+'#token='+workspace.settings.token)
    page.get_by_role('button',name='Results',exact=True).click()
    page.get_by_role('button',name='Open Browser fastp processing',exact=True).click()
    page.get_by_role('tab',name='QC metrics',exact=True).click()
    playwright.expect(page.get_by_role('region',name='Processing results').get_by_role('link',name='Download FASTQ',exact=True)).to_have_count(2)
    page.set_viewport_size({'width':740,'height':1000})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(directory/f'native-processing-mobile{suffix}.png'),full_page=True)
    page.close()


def test_seqkit_statistics_and_subsampling_from_shared_selection(workspace,browser):
    page=browser.new_page()
    page.goto(workspace.base+'?seqkit='+secrets.token_hex(4)+'#token='+workspace.settings.token)
    page.get_by_role('button',name='Files',exact=True).click()
    page.get_by_label('Select all visible input files').check()
    page.get_by_role('button',name='Read Processing',exact=True).click()
    page.get_by_label('Operation',exact=True).select_option('seqkit-stats')
    page.get_by_role('button',name='Browse & select FASTQs',exact=True).click()
    playwright.expect(page.get_by_role('region',name='Read processing setup')).not_to_be_visible()
    page.get_by_role('button',name='Read Processing',exact=True).click()
    playwright.expect(page.get_by_label('Operation',exact=True)).to_have_value('seqkit-stats')
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/runs')) as created:
        page.get_by_role('button',name='Run processing',exact=True).click()
    with workspace.api() as api:run=workspace.finish(api,created.value.json())
    assert all(unit['statistics'][0]['num_seqs']=='400' for unit in run['processing']['units'])
    page.get_by_role('tab',name='QC metrics',exact=True).click()
    playwright.expect(page.get_by_text('Original SeqKit statistics (reported values)',exact=True)).to_be_visible()
    page.get_by_role('button',name='Rerun',exact=True).click()
    playwright.expect(page.get_by_label('Operation',exact=True)).to_have_value('seqkit-stats')
    page.get_by_label('Operation',exact=True).select_option('seqkit-sample')
    page.get_by_label('Sampling fraction',exact=True).fill('0.25')
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/runs')) as created:
        page.get_by_role('button',name='Run processing',exact=True).click()
    with workspace.api() as api:sampled=workspace.finish(api,created.value.json())
    assert len(sampled['derived_datasets'])==2 and all(not entry['paired'] for entry in sampled['derived_datasets'])
    page.close()
