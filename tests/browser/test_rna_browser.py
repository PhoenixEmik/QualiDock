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
        # MultiQC collapses a single section into its module anchor.
        frame.locator('a[href="#rseqc"]').first.click()
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


def test_gene_body_native_curve_exports_original_plot_and_restart(workspace,browser):
    import subprocess
    tool=shutil.which('geneBody_coverage.py');samtools=shutil.which('samtools')
    assert tool and samtools,'Genuine RSeQC gene-body and SAMtools are required'
    label='genebody-'+secrets.token_hex(4)
    directory=INPUTS/label;bam,bed=fixture.prepare(directory,samtools)
    source=directory/(label+' comma, <img onerror=alert(1)>.bam');shutil.copyfile(bam,source)
    subprocess.run([samtools,'index',str(source)],check=True)
    index=Path(str(source)+'.bai')
    originals={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,index,bed)}
    workspace.settings.rna_annotations={label:str(bed.resolve())}
    page=browser.new_page(viewport={'width':1400,'height':1000});dialogs=[]
    page.on('dialog',lambda d:(dialogs.append(d.message),d.dismiss()))
    try:
        page.goto(workspace.base+'?gene-body='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Files',exact=True).click()
        page.get_by_role('button',name=label,exact=True).click()
        page.get_by_label('Select file '+source.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        page.get_by_role('button',name='RSeQC RNA-seq QC',exact=False).click()
        page.get_by_label('RSeQC operation',exact=True).select_option('rseqc-genebody')
        page.get_by_label('Gene annotation (BED12)',exact=True).select_option(label)
        page.get_by_text('Gene-body settings (optional)',exact=True).click()
        page.get_by_label('Minimum exonic transcript length (bp)',exact=False).fill('99')
        playwright.expect(page.get_by_role('button',name='Run analysis',exact=True)).to_be_disabled()
        page.get_by_label('Minimum exonic transcript length (bp)',exact=False).fill('100')
        page.get_by_label('Generate original PNG using installed Rscript',exact=True).check()
        name='Gene-body '+secrets.token_hex(3);page.get_by_label('Analysis name').fill(name)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created.value.status==201,created.value.text()
        with workspace.api() as api:run=workspace.finish(api,created.value.json())
        row=run['qc']['results'][0];data=row['rseqc']
        assert run['qc']['options']['original_plot'] is True and run['qc']['options']['minimum_length']==100
        assert data['status']=='available' and data['plot']['status']=='completed'
        assert max(float(v) for _,v in data['rows'])==2
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        chart=page.get_by_role('img',name='Gene-body coverage for ',exact=False)
        playwright.expect(chart).to_be_visible()
        panel=page.get_by_role('region',name='RSeQC results',exact=True)
        panel.get_by_text('Original RSeQC values (100 reported rows)',exact=True).click()
        playwright.expect(panel.get_by_role('row',name='100 0.0',exact=True)).to_be_visible()
        panel.get_by_text('Original RSeQC values (100 reported rows)',exact=True).click()
        with page.expect_download() as exported:panel.get_by_role('button',name='Export SVG',exact=True).click()
        assert '<svg' in Path(exported.value.path()).read_text()
        with page.expect_download() as original:panel.get_by_role('link',name='Download percentile table',exact=True).click()
        assert Path(original.value.path()).read_text().startswith('Percentile\t1\t2')
        with page.expect_download() as image:panel.get_by_role('link',name='Download original png',exact=True).click()
        assert Path(image.value.path()).read_bytes().startswith(b'\x89PNG')
        suffix=workspace.settings.prefix.replace('/','-') or '-root'
        page.screenshot(path='validation/rna-genebody'+suffix+'.png',full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path='validation/rna-genebody-mobile'+suffix+'.png',full_page=True)
        workspace.stop();workspace.start()
        page.goto(workspace.base+'?genebody-restored='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+name,exact=True).first.click()
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        playwright.expect(page.get_by_role('img',name='Gene-body coverage for ',exact=False)).to_be_visible()
        page.get_by_role('button',name='Rerun',exact=True).click()
        playwright.expect(page.get_by_label('RSeQC operation',exact=True)).to_have_value('rseqc-genebody')
        playwright.expect(page.get_by_label('Gene annotation (BED12)',exact=True)).to_have_value(label)
        assert originals=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
        assert not dialogs and page.locator('img[onerror]').count()==0
    finally:
        page.close();source.unlink(missing_ok=True);index.unlink(missing_ok=True);shutil.rmtree(directory)
