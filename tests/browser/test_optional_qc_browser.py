"""Real optional QC through existing setup, results, downloads and restart."""
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
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


def test_screen_native_panel_mapping_reports_and_restart(workspace, browser, tmp_path):
    assert shutil.which('fastq_screen') and shutil.which('bowtie2'), 'Actual screening tools required'
    references=tmp_path/'references'
    subprocess.run([sys.executable,str(ROOT/'scripts/prepare-screen-test.py'),'--output',str(references)],check=True,capture_output=True)
    workspace.settings.screen_panels['browser-panel']=str(references/'panel.conf')
    token=secrets.token_hex(4);sources=[]
    for read in (1,2):
        source=INPUTS/f'screen-{token}_R{read}.fastq.gz'
        shutil.copyfile(ROOT/'backend/tests/fixtures/fastq-screen-0.16.0/reads.fastq.gz',source);sources.append(source)
    hashes=[hashlib.sha256(source.read_bytes()).hexdigest() for source in sources]
    page=browser.new_page(viewport={'width':1400,'height':1000})
    try:
        page.goto(workspace.base+'?screen='+token+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Files',exact=True).click()
        for source in sources:page.get_by_label('Select file '+source.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        page.get_by_role('button',name='FastQ Screen',exact=False).click()
        page.get_by_label('Reference panel',exact=True).select_option('browser-panel')
        page.get_by_text('Screening settings (optional)',exact=True).click()
        page.get_by_label('Target subset size (reads per file)',exact=True).fill('10')
        page.get_by_label('Generate MultiQC',exact=True).check()
        name='Screen '+token;page.get_by_label('Analysis name',exact=True).fill(name)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created.value.status==201
        with workspace.api() as api:
            run=workspace.finish(api,created.value.json())
            assert run['sample_count']==2 and all(row['screen']['processed_reads']==20 for row in run['qc']['results'])
            assert len({v['multiqc_name'] for v in run['report_input_map'].values()})==2
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='FastQ Screen results',exact=True)
        playwright.expect(panel.get_by_role('rowheader',name='alpha',exact=True)).to_have_count(2)
        playwright.expect(panel.get_by_text('20 reads screened · 10.00% hit no reference in this panel.',exact=True)).to_have_count(2)
        panel.get_by_text('Reference provenance',exact=True).click()
        playwright.expect(panel.get_by_text('Configuration SHA-256:',exact=False)).to_be_visible()
        page.get_by_role('tab',name='Reports',exact=True).click()
        individual=run['qc']['results'][0]['report'].replace('.txt','.html')
        page.get_by_label('Select HTML report',exact=True).select_option(individual)
        frame=page.frame_locator('iframe[title^="Official QC report:"]')
        playwright.expect(frame.locator('#myGraph .main-svg').first).to_be_visible(timeout=30000)
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
        table=panel.get_by_role('region',name='Reference mapping summary '+sources[0].name,exact=True)
        table.focus();table.press('ArrowRight')
        page.wait_for_function('(element) => element.scrollLeft>0',arg=table.element_handle())
        page.screenshot(path='validation/screen'+(workspace.settings.prefix.replace('/','-') or '-root')+'.png',full_page=True)
        workspace.stop();workspace.start()
        page.goto(workspace.base+'?screen-restart='+token+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+name,exact=True).click()
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        playwright.expect(page.get_by_role('region',name='FastQ Screen results',exact=True)).to_be_visible()
        assert hashes==[hashlib.sha256(source.read_bytes()).hexdigest() for source in sources]
    finally:
        page.close()
        for source in sources:source.unlink(missing_ok=True)
        workspace.settings.screen_panels.pop('browser-panel',None)
