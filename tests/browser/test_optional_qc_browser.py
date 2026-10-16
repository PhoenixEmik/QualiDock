"""Real optional QC through existing setup, results, downloads and restart."""
import hashlib
import os
from pathlib import Path
import secrets
import shutil
from test_report_viewer import workspace, browser, playwright, INPUTS, ROOT


def test_nanoq_native_setup_and_restart(workspace, browser):
    assert shutil.which(os.environ.get('QUALIDOCK_NANOQ','nanoq')), 'Actual nanoq required'
    source=INPUTS/('ont-'+secrets.token_hex(4)+'.fastq.gz')
    shutil.copyfile(ROOT/'backend/tests/fixtures/nanoq-0.10.0/ont.fastq.gz',source)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    page=browser.new_page(viewport={'width':1400,'height':1000})
    try:
        page.goto(workspace.base+'?optional='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Files',exact=True).click()
        page.get_by_label('Select file '+source.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        page.get_by_role('button',name='nanoq long-read QC',exact=False).click()
        name='Native nanoq '+secrets.token_hex(3)
        page.get_by_label('Analysis name',exact=True).fill(name)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created.value.status==201
        with workspace.api() as api:
            run=workspace.finish(api,created.value.json())
            report=run['qc']['results'][0]['report']
            official=api.get(f'api/runs/{run["id"]}/download',params={'path':report})
            assert official.status_code==200 and official.json()['n50']==1475
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='nanoq QC results',exact=True)
        playwright.expect(panel.get_by_role('cell',name='1475',exact=True)).to_be_visible()
        panel.get_by_text('Reported threshold counts',exact=True).click()
        playwright.expect(panel.get_by_text('Read quality (Phred)',exact=True)).to_be_visible()
        playwright.expect(panel.get_by_role('link',name='Download original JSON')).to_be_visible()
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
        Path('validation').mkdir(exist_ok=True)
        page.screenshot(path='validation/nanoq'+(workspace.settings.prefix.replace('/','-') or '-root')+'.png',full_page=True)
        workspace.stop();workspace.start()
        page.goto(workspace.base+'?optional-restart='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+name,exact=True).click()
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        playwright.expect(page.get_by_role('region',name='nanoq QC results').get_by_role('cell',name='1475',exact=True)).to_be_visible()
        assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    finally:
        page.close();source.unlink(missing_ok=True)
