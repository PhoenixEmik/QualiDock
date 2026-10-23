"""Genuine VCF/BCF workflow through the existing UI, both browser engines."""
import hashlib
import importlib.util
import secrets
import shutil
from test_report_viewer import workspace, browser, playwright, INPUTS, ROOT

spec=importlib.util.spec_from_file_location('prepare_variant',ROOT/'scripts/prepare-variant-test.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def test_variant_selection_statistics_original_reports_history_and_rerun(workspace,browser):
    tool=shutil.which('bcftools');assert tool,'Genuine BCFtools 1.24 required'
    directory=INPUTS/('variant-'+secrets.token_hex(4));paths=fixture.prepare(directory,tool)
    vcf=INPUTS/(directory.name+'.vcf');bcf=INPUTS/(directory.name+'.bcf')
    vcf.write_bytes(paths['multisample'].read_bytes());bcf.write_bytes(paths['bcf'].read_bytes())
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [vcf,bcf]}
    page=browser.new_page(viewport={'width':1400,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto(workspace.base+'?variant='+secrets.token_hex(4)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Files',exact=True).click()
        for p in [vcf,bcf]:page.get_by_label('Select file '+p.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        playwright.expect(page.get_by_role('button',name='BCFtools variant QC',exact=False)).to_have_attribute('aria-pressed','true')
        assert not page.get_by_text('Review read relationships (optional)',exact=True).is_visible()
        page.get_by_label('Generate MultiQC',exact=True).check()
        name='Variant '+secrets.token_hex(3);page.get_by_label('Analysis name',exact=True).fill(name)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created.value.status==201
        with workspace.api() as api:run=workspace.finish(api,created.value.json())
        assert run['state']=='completed',run['error']
        overview=page.get_by_role('region',name='Variant overview',exact=True)
        playwright.expect(overview.get_by_text('4 reported records',exact=True)).to_be_visible()
        assert not page.get_by_role('region',name='FASTQ integrity validation').is_visible()
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='BCFtools variant results',exact=True)
        playwright.expect(panel.get_by_role('region',name='Original record summary',exact=True)).to_be_visible()
        playwright.expect(panel.get_by_role('rowheader',name='number of records:',exact=True)).to_be_visible()
        with page.expect_download() as downloaded:panel.get_by_role('link',name='Download original BCFtools stats',exact=True).click()
        saved=downloaded.value.path()
        assert hashlib.sha256(saved.read_bytes()).hexdigest()==run['qc']['results'][0]['variant']['report_sha256']
        bcf_row=next(r for r in run['qc']['results'] if r['path']==str(bcf))
        page.get_by_label('Variant input file',exact=True).select_option(bcf_row['id'])
        playwright.expect(panel.get_by_text('Unavailable (no transversions)',exact=False)).to_be_visible()
        playwright.expect(panel.get_by_text('Depth chart unavailable:',exact=False)).to_be_visible()
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
        suffix=workspace.settings.prefix.replace('/','-') or '-root'
        page.screenshot(path='validation/variant-native'+suffix+'.png',full_page=True)
        page.get_by_role('tab',name='Reports',exact=True).click()
        playwright.expect(page.get_by_label('Select HTML report',exact=True)).to_have_value('multiqc/multiqc_report.html')
        workspace.stop();workspace.start()
        page.goto(workspace.base+'?variant-restored='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+name,exact=True).click()
        page.get_by_role('button',name='Rerun',exact=True).click()
        playwright.expect(page.get_by_label('Generate MultiQC',exact=True)).to_be_checked()
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as rerun:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert rerun.value.status==201
        with workspace.api() as api:restored=workspace.finish(api,rerun.value.json())
        assert restored['state']=='completed' and restored['rerun_of']==run['id']
        assert not errors
        assert all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in before.items())
    finally:
        page.close();vcf.unlink(missing_ok=True);bcf.unlink(missing_ok=True);shutil.rmtree(directory)
