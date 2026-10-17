"""Actual RSeQC setup, original fractions/blocks, downloads and restart."""
import hashlib
import importlib.util
from pathlib import Path
import secrets
import shutil
from test_report_viewer import workspace,browser,playwright,INPUTS,ROOT

spec=importlib.util.spec_from_file_location('prepare_rna',ROOT/'scripts/prepare-rna-test.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def test_rseqc_original_values_accessible_setup_downloads_and_restart(workspace,browser):
    samtools=shutil.which('samtools')
    assert samtools and shutil.which('infer_experiment.py') and shutil.which('read_distribution.py'),'Actual RSeQC required'
    label='rna-'+secrets.token_hex(4)
    directory=INPUTS/label;bam,bed=fixture.prepare(directory,samtools)
    source=INPUTS/(label+' <img onerror=alert(1)>.bam');shutil.copyfile(bam,source)
    originals=[source,bed,bam]
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    workspace.settings.rna_annotations={label:str(bed.resolve())}
    page=browser.new_page(viewport={'width':1400,'height':1000});dialogs=[]
    page.on('dialog',lambda dialog:(dialogs.append(dialog.message),dialog.dismiss()))
    try:
        page.goto(workspace.base+'?rna='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Files',exact=True).click()
        page.get_by_label('Select file '+source.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        page.get_by_role('button',name='RSeQC RNA-seq QC',exact=False).click()
        playwright.expect(page.get_by_role('button',name='Run analysis',exact=True)).to_be_disabled()
        assert not page.get_by_text('Review read relationships (optional)',exact=True).is_visible()
        page.get_by_label('Gene annotation (BED12)',exact=True).select_option(label)
        page.get_by_label('Aggregate original RSeQC reports with MultiQC',exact=True).check()
        page.get_by_text('Strandedness settings (optional)',exact=True).click()
        page.get_by_label('Maximum usable alignments',exact=False).fill('1000')
        name='RNA '+secrets.token_hex(3)
        page.get_by_label('Analysis name',exact=True).fill(name)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created.value.status==201
        with workspace.api() as api:run=workspace.finish(api,created.value.json())
        assert run['qc']['options']['sample_size']==1000
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='RSeQC results',exact=True)
        playwright.expect(panel.get_by_role('row',name='Fraction of reads failed to determine 0.2000',exact=True)).to_be_visible()
        playwright.expect(panel.get_by_role('row',name='Fraction of reads explained by "1++,1--,2+-,2-+" 0.6000',exact=True)).to_be_visible()
        with page.expect_download() as downloaded:
            panel.get_by_role('link',name='Download stdout',exact=True).click()
        assert b'This is PairEnd Data' in Path(downloaded.value.path()).read_bytes()
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
        suffix=workspace.settings.prefix.replace('/','-') or '-root'
        page.screenshot(path='validation/rna-strandedness'+suffix+'.png',full_page=True)
        page.set_viewport_size({'width':1400,'height':1000})
        page.get_by_role('tab',name='Reports',exact=True).click()
        frame=page.locator('.report-preview[aria-busy=false] iframe').content_frame
        frame.locator('a[href="#rseqc-infer_experiment"]').first.click()
        frame.locator('#rseqc_infer_experiment_plot .main-svg').first.wait_for(timeout=30000)
        page.get_by_role('button',name='Rerun',exact=True).click()
        playwright.expect(page.get_by_label('Aggregate original RSeQC reports with MultiQC',exact=True)).to_be_checked()
        playwright.expect(page.get_by_label('Gene annotation (BED12)',exact=True)).to_have_value(label)
        playwright.expect(page.get_by_label('Maximum usable alignments',exact=False)).to_have_value('1000')
        page.get_by_label('RSeQC operation',exact=True).select_option('rseqc-distribution')
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as distribution:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert distribution.value.status==201
        with workspace.api() as api:drun=workspace.finish(api,distribution.value.json())
        assert drun['qc']['options']=={'annotation':label,'multiqc':True}
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='RSeQC results',exact=True)
        playwright.expect(panel.get_by_role('row',name='CDS_Exons 3000 7 2.33',exact=True)).to_be_visible()
        playwright.expect(panel.get_by_role('row',name='Introns 6000 4 0.67',exact=True)).to_be_visible()
        page.screenshot(path='validation/rna-distribution'+suffix+'.png',full_page=True)
        workspace.stop();workspace.start()
        page.goto(workspace.base+'?rna-restored='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+name,exact=True).first.click()
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        playwright.expect(page.get_by_role('region',name='RSeQC results',exact=True)).to_be_visible()
        assert hashes=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
        assert not dialogs and page.locator('img[onerror]').count()==0
    finally:
        page.close();source.unlink(missing_ok=True);shutil.rmtree(directory)
