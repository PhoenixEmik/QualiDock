"""Genuine alignment setup/results using the same browser/authentication app."""
import hashlib
import importlib.util
from pathlib import Path
import secrets
import shutil
from test_report_viewer import workspace, browser, playwright, INPUTS, ROOT

spec=importlib.util.spec_from_file_location('prepare_alignment', ROOT/'scripts/prepare-alignment-test.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def test_alignment_selection_stats_reports_reference_and_restart(workspace,browser):
    tool=shutil.which('samtools');assert tool,'Actual SAMtools required'
    # Explicit test fixture construction; application must never convert or index.
    directory=INPUTS/('alignment-'+secrets.token_hex(4))
    bam,cram,ref=fixture.prepare(directory,tool)
    # Root listing is deliberately flat here to exercise ordinary file selection.
    label=directory.name
    standalone=INPUTS/(label+'.bam');shutil.copyfile(bam,standalone)
    standalone_cram=INPUTS/(label+'.cram');shutil.copyfile(cram,standalone_cram)
    digest=hashlib.sha256(standalone.read_bytes()).hexdigest()
    cram_digest=hashlib.sha256(standalone_cram.read_bytes()).hexdigest()
    workspace.settings.alignment_references={label:str(ref.resolve())}
    page=browser.new_page(viewport={'width':1400,'height':1000})
    try:
        page.goto(workspace.base+'?alignment='+secrets.token_hex(4)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Files',exact=True).click()
        page.get_by_label('Select file '+standalone.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        playwright.expect(page.get_by_role('button',name='SAMtools alignment QC',exact=False)).to_have_attribute('aria-pressed','true')
        assert not page.get_by_text('Review read relationships (optional)',exact=True).is_visible()
        page.get_by_label('Generate MultiQC',exact=True).check()
        name='Alignment '+secrets.token_hex(3)
        page.get_by_label('Analysis name',exact=True).fill(name)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created.value.status==201
        with workspace.api() as api:
            run=workspace.finish(api,created.value.json())
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='SAMtools QC results',exact=True)
        playwright.expect(panel.get_by_role('rowheader',name='mapped (85.71% : 100.00%)',exact=True)).to_be_visible()
        playwright.expect(panel.get_by_text('quickcheck checks the header',exact=False)).to_be_visible()
        with page.expect_download() as downloaded:
            panel.get_by_role('link',name='Download original flagstat',exact=True).click()
        assert downloaded.value.suggested_filename.endswith('.flagstat.txt')
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
        suffix=workspace.settings.prefix.replace('/','-') or '-root'
        page.screenshot(path='validation/alignment-native'+suffix+'.png',full_page=True)
        page.get_by_role('tab',name='Overview & logs',exact=False).click()
        assert not page.get_by_role('region',name='FASTQ integrity validation').is_visible()
        page.get_by_role('tab',name='Reports',exact=True).click()
        playwright.expect(page.get_by_label('Select HTML report',exact=True)).to_have_value('multiqc/multiqc_report.html')
        workspace.stop();workspace.start()
        page.goto(workspace.base+'?alignment-restored='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+name,exact=True).click()
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        playwright.expect(page.get_by_role('region',name='SAMtools QC results').get_by_role('rowheader',name='primary',exact=True)).to_be_visible()
        assert hashlib.sha256(standalone.read_bytes()).hexdigest()==digest
        page.get_by_role('button',name='Workspace',exact=True).click()
        page.get_by_role('button',name='Files',exact=True).click()
        page.get_by_label('Select file '+standalone_cram.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        playwright.expect(page.get_by_role('button',name='Run analysis',exact=True)).to_be_disabled()
        page.get_by_label('Local CRAM reference',exact=True).select_option(label)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created_cram:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created_cram.value.status==201
        with workspace.api() as api:
            cram_run=workspace.finish(api,created_cram.value.json())
            assert cram_run['qc']['reference']['id']==label
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        playwright.expect(page.get_by_role('region',name='SAMtools QC results').get_by_text('CRAM · quickcheck: passed (header/EOF only)',exact=True)).to_be_visible()
        assert hashlib.sha256(standalone_cram.read_bytes()).hexdigest()==cram_digest
    finally:
        page.close();standalone.unlink(missing_ok=True);standalone_cram.unlink(missing_ok=True);shutil.rmtree(directory)
