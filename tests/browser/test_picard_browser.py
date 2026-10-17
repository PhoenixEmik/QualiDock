"""Actual Picard/R PDF and native metrics, isolated downloads and history."""
import hashlib
import importlib.util
from pathlib import Path
import secrets
import shutil
from test_report_viewer import workspace,browser,playwright,INPUTS,ROOT

spec=importlib.util.spec_from_file_location('prepare_insert',ROOT/'scripts/prepare-insert-test.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def test_native_insert_metrics_original_histogram_pdf_and_restart(workspace,browser):
    samtools=shutil.which('samtools');assert samtools and shutil.which('Rscript'),'Actual SAMtools and R required'
    label='picard-'+secrets.token_hex(4)
    directory=INPUTS/label;bam=fixture.prepare(directory,samtools)
    source=INPUTS/(label+' <img onerror=alert(1)>.bam');shutil.copyfile(bam,source)
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    page=browser.new_page(viewport={'width':1400,'height':1000});dialogs=[]
    page.on('dialog',lambda dialog:(dialogs.append(dialog.message),dialog.dismiss()))
    try:
        page.goto(workspace.base+'?picard='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Files',exact=True).click()
        page.get_by_label('Select file '+source.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        page.get_by_role('button',name='Picard insert-size QC',exact=False).click()
        assert not page.get_by_text('Review read relationships (optional)',exact=True).is_visible()
        page.get_by_label('Aggregate original insert-size reports with MultiQC',exact=True).check()
        page.get_by_text('Insert-size settings (optional)',exact=True).click()
        option=page.get_by_label('Generate original PDF histogram (Rscript)',exact=True)
        option.focus();page.keyboard.press('Space');playwright.expect(option).to_be_checked()
        name='Insert '+secrets.token_hex(3)
        page.get_by_label('Analysis name',exact=True).fill(name)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created.value.status==201
        with workspace.api() as api:run=workspace.finish(api,created.value.json())
        assert run['qc']['options']['histogram_pdf']
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='Picard insert-size results',exact=True)
        summary=panel.get_by_role('region',name='Insert-size summary',exact=True)
        playwright.expect(summary.get_by_role('row',name='FR 3 250 250 100 All reads',exact=True)).to_be_visible()
        playwright.expect(summary.get_by_role('row',name='RF 2 250 250 70.710678 All reads',exact=True)).to_be_visible()
        playwright.expect(summary.get_by_role('row',name='TANDEM 1 400 400 Unavailable All reads',exact=True)).to_be_visible()
        with page.expect_download() as downloaded:
            panel.get_by_role('link',name='Download histogram pdf',exact=True).click()
        pdf=Path(downloaded.value.path()).read_bytes()
        assert pdf.startswith(b'%PDF-') and b'%%EOF' in pdf[-1024:]
        playwright.expect(page.locator('.state.completed')).to_be_visible(timeout=10000)
        panel.get_by_text('Original metrics and histogram data',exact=True).click()
        histogram=panel.get_by_role('region',name='Original insert-size histogram',exact=True)
        playwright.expect(histogram.get_by_role('row',name='150 1 0 0',exact=True)).to_be_visible()
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
        suffix=workspace.settings.prefix.replace('/','-') or '-root'
        page.screenshot(path='validation/picard-native'+suffix+'.png',full_page=True)
        page.set_viewport_size({'width':1400,'height':1000})
        page.get_by_role('tab',name='Reports',exact=True).click()
        frame=page.locator('.report-preview[aria-busy=false] iframe').content_frame
        frame.locator('#picard_insert_size').scroll_into_view_if_needed()
        frame.locator('#picard_insert_size .main-svg').first.wait_for(timeout=30000)
        workspace.stop();workspace.start()
        page.goto(workspace.base+'?insert-restored='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+name,exact=True).click()
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='Picard insert-size results',exact=True)
        playwright.expect(panel.get_by_role('region',name='Insert-size summary',exact=True).get_by_role('rowheader',name='TANDEM',exact=True)).to_be_visible()
        page.get_by_role('button',name='Rerun',exact=True).click()
        playwright.expect(page.get_by_label('Generate original PDF histogram (Rscript)',exact=True)).to_be_checked()
        playwright.expect(page.get_by_label('Aggregate original insert-size reports with MultiQC',exact=True)).to_be_checked()
        assert hashlib.sha256(source.read_bytes()).hexdigest()==original
        assert not Path(str(source)+'.bai').exists() and not dialogs and page.locator('img[onerror]').count()==0
    finally:
        page.close();source.unlink(missing_ok=True);shutil.rmtree(directory)
