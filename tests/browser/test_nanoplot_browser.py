"""Actual original NanoPlot HTML under the existing opaque report sandbox."""
import hashlib
import secrets
import shutil
from pathlib import Path
from test_report_viewer import workspace, browser, playwright, INPUTS, ROOT


def test_original_nanoplot_setup_report_stats_and_restart(workspace,browser):
    assert shutil.which('NanoPlot'), 'Actual NanoPlot required'
    source=INPUTS/('nanoplot-'+secrets.token_hex(4)+'.fastq.gz')
    shutil.copyfile(ROOT/'backend/tests/fixtures/nanoq-0.10.0/ont.fastq.gz',source)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    page=browser.new_page(viewport={'width':1400,'height':1000})
    try:
        page.goto(workspace.base+'?nanoplot='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Files',exact=True).click()
        page.get_by_label('Select file '+source.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        page.get_by_role('button',name='NanoPlot long-read QC',exact=False).click()
        page.get_by_text('Plot settings (optional)',exact=True).click()
        page.get_by_label('Additional logarithmic length plots',exact=True).check()
        page.get_by_label('Save individual interactive plot HTML',exact=True).check()
        name='NanoPlot '+secrets.token_hex(3)
        page.get_by_label('Analysis name',exact=True).fill(name)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created.value.status==201
        with workspace.api() as api:
            run=workspace.finish(api,created.value.json())
            row=run['qc']['results'][0]
            assert row['nanoplot']['plots'] and run['qc']['options']['loglength']
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='NanoPlot QC results',exact=True)
        playwright.expect(panel.get_by_role('cell',name='1475.0',exact=True)).to_be_visible()
        playwright.expect(panel.get_by_text('Time/channel activity',exact=False)).to_be_visible()
        with page.expect_download() as downloaded:
            panel.get_by_role('link',name='Download original NanoStats',exact=True).click()
        assert downloaded.value.suggested_filename=='NanoStats.txt'
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
        Path('validation').mkdir(exist_ok=True)
        suffix=workspace.settings.prefix.replace('/','-') or '-root'
        page.screenshot(path='validation/nanoplot-native'+suffix+'.png',full_page=True)
        page.get_by_role('tab',name='Reports',exact=True).click()
        playwright.expect(page.get_by_label('Select HTML report',exact=True)).to_have_value(row['nanoplot']['html'])
        frame=page.frame_locator('iframe[title^="Official QC report:"]')
        playwright.expect(frame.locator('.plotly-graph-div .main-svg').first).to_be_visible(timeout=30000)
        assert frame.locator('body').evaluate('() => {try {void parent.document.body;return false;}catch(e){return e.name==="SecurityError";}}')
        assert frame.locator('body').evaluate('async () => {try {await fetch("'+workspace.base+'api/config",{credentials:"include"});return false;}catch(e){return e.name==="TypeError";}}')
        page.screenshot(path='validation/nanoplot-report'+suffix+'.png',full_page=True)
        workspace.stop();workspace.start()
        page.goto(workspace.base+'?nanoplot-restored='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+name,exact=True).click()
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        playwright.expect(page.get_by_role('region',name='NanoPlot QC results').get_by_role('cell',name='1475.0',exact=True)).to_be_visible()
        assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    finally:
        page.close();source.unlink(missing_ok=True)
