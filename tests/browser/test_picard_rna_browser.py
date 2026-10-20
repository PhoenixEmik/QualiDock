"""Genuine production RNA workflow, original PDF, normalized plot and rerun."""
import hashlib
import importlib.util
from pathlib import Path
import secrets
import shutil
import subprocess
from test_report_viewer import workspace,browser,playwright,INPUTS,ROOT

spec=importlib.util.spec_from_file_location('rna_study',ROOT/'scripts/qualify-picard-rna.py')
study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)


def test_picard_rna_explicit_contract_native_metrics_reports_and_restart(workspace,browser):
    samtools=shutil.which('samtools');assert samtools and shutil.which('Rscript')
    label='picard-rna-'+secrets.token_hex(4)
    directory=INPUTS/label;bam=study.fixture(directory,'bias-plus')
    subprocess.run([samtools,'view','-b','-o',str(bam),str(bam.with_suffix('.sam'))],check=True,capture_output=True)
    source=INPUTS/(label+' <img onerror=alert(1)>.bam');shutil.copyfile(bam,source)
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    old_ref,old_rrna=workspace.settings.rna_refflat_annotations,workspace.settings.rrna_intervals
    workspace.settings.rna_refflat_annotations={'rna-model':str(directory/'genes.refFlat')}
    workspace.settings.rrna_intervals={'ribosomal':str(directory/'rrna.interval_list')}
    page=browser.new_page(viewport={'width':1400,'height':1000});dialogs=[]
    page.on('dialog',lambda d:(dialogs.append(d.message),d.dismiss()))
    try:
        page.goto(workspace.base+'?rna='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Files',exact=True).click()
        page.get_by_label('Select file '+source.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        page.get_by_role('button',name='Picard RNA-seq metrics',exact=False).click()
        start=page.get_by_role('button',name='Run analysis',exact=True)
        playwright.expect(start).to_be_disabled()
        page.get_by_label('Approved native refFlat annotation',exact=True).select_option('rna-model')
        playwright.expect(start).to_be_disabled()
        page.get_by_label('Picard strand specificity',exact=True).select_option('SECOND_READ_TRANSCRIPTION_STRAND')
        page.get_by_label('Approved rRNA intervals (optional)',exact=True).select_option('ribosomal')
        page.get_by_label('Aggregate original RNA metrics with MultiQC',exact=True).check()
        page.get_by_text('RNA metrics settings (optional)',exact=True).click()
        pdf=page.get_by_label('Generate original RNA coverage PDF (Rscript)',exact=True)
        pdf.focus();page.keyboard.press('Space');playwright.expect(pdf).to_be_checked()
        name='RNA metrics '+secrets.token_hex(3);page.get_by_label('Analysis name',exact=True).fill(name)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:start.click()
        assert created.value.status==201
        with workspace.api() as api:run=workspace.finish(api,created.value.json())
        assert run['qc']['options']['strand']=='SECOND_READ_TRANSCRIPTION_STRAND'
        assert run['qc']['multiqc_status']=='available'
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='Picard RNA-seq results',exact=True)
        summary=panel.get_by_role('region',name='RNA metrics summary',exact=True)
        playwright.expect(summary.get_by_role('row',name='Median 5′ / 3′ bias 2 ratio; eligible transcripts only',exact=True)).to_be_visible()
        playwright.expect(panel.locator('canvas')).to_be_visible()
        with page.expect_download() as downloaded:panel.get_by_role('button',name='Export SVG',exact=True).click()
        assert b'<svg' in Path(downloaded.value.path()).read_bytes()
        panel.get_by_text('Original Picard normalized coverage (101 reported rows)',exact=True).click()
        raw=panel.get_by_role('region',name='Original Picard normalized coverage',exact=True)
        playwright.expect(raw.get_by_role('rowheader',name='0',exact=True)).to_be_visible()
        playwright.expect(raw.get_by_role('rowheader',name='100',exact=True)).to_be_visible()
        with page.expect_download() as downloaded:panel.get_by_role('link',name='Download coverage pdf',exact=True).click()
        content=Path(downloaded.value.path()).read_bytes()
        assert content.startswith(b'%PDF-') and b'%%EOF' in content[-1024:]
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
        suffix=workspace.settings.prefix.replace('/','-') or '-root'
        page.screenshot(path='validation/picard-rna-native'+suffix+'.png',full_page=True)
        page.set_viewport_size({'width':1400,'height':1000})
        workspace.stop();workspace.start()
        page.goto(workspace.base+'?restored-rna='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+name,exact=True).click()
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        playwright.expect(page.get_by_role('region',name='RNA metrics summary',exact=True)).to_be_visible()
        page.get_by_role('button',name='Rerun',exact=True).click()
        playwright.expect(page.get_by_label('Approved native refFlat annotation',exact=True)).to_have_value('rna-model')
        playwright.expect(page.get_by_label('Picard strand specificity',exact=True)).to_have_value('SECOND_READ_TRANSCRIPTION_STRAND')
        playwright.expect(page.get_by_label('Approved rRNA intervals (optional)',exact=True)).to_have_value('ribosomal')
        assert hashlib.sha256(source.read_bytes()).hexdigest()==original
        assert not Path(str(source)+'.bai').exists() and not dialogs and page.locator('img[onerror]').count()==0
    finally:
        page.close();source.unlink(missing_ok=True);shutil.rmtree(directory)
        workspace.settings.rna_refflat_annotations,workspace.settings.rrna_intervals=old_ref,old_rrna
