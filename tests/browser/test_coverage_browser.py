"""Real mosdepth; native CDF, region denominators and authenticated artifacts."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
import secrets
import shutil
import subprocess
from test_report_viewer import workspace,browser,playwright,INPUTS,ROOT

spec=importlib.util.spec_from_file_location('prepare_coverage',ROOT/'scripts/prepare-alignment-test.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def test_native_coverage_cdf_regions_downloads_cram_and_restart(workspace,browser):
    samtools=shutil.which('samtools');assert samtools and shutil.which('mosdepth'),'Actual SAMtools and mosdepth required'
    label='coverage-'+secrets.token_hex(4)
    directory=INPUTS/label
    bam,cram,ref=fixture.prepare(directory,samtools)
    bed=directory/'panel.bed';shutil.copyfile(ROOT/'backend/tests/fixtures/mosdepth-0.3.14/panel.bed',bed)
    source=INPUTS/(label+'.bam');source_cram=INPUTS/(label+'.cram')
    shutil.copyfile(bam,source);shutil.copyfile(cram,source_cram)
    # Test-only construction of existing input indexes. App must never do this.
    subprocess.run([samtools,'index','-c',str(source)],check=True,capture_output=True)
    subprocess.run([samtools,'index',str(source_cram)],check=True,capture_output=True)
    index=Path(str(source)+'.csi');cram_index=Path(str(source_cram)+'.crai')
    originals=[source,source_cram,index,cram_index,ref,Path(str(ref)+'.fai'),bed]
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    workspace.settings.coverage_panels={label:str(bed.resolve())}
    workspace.settings.alignment_references={label:str(ref.resolve())}
    page=browser.new_page(viewport={'width':1400,'height':1000})
    try:
        page.goto(workspace.base+'?coverage='+secrets.token_hex(4)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Files',exact=True).click()
        page.get_by_label('Select file '+source.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        page.get_by_role('button',name='mosdepth coverage QC',exact=False).click()
        assert not page.get_by_text('Review read relationships (optional)',exact=True).is_visible()
        page.get_by_label('Target regions (optional)',exact=True).select_option(label)
        name='Coverage '+secrets.token_hex(3)
        page.get_by_label('Analysis name',exact=True).fill(name)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created.value.status==201
        with workspace.api() as api:
            run=workspace.finish(api,created.value.json())
            assert run['qc']['results'][0]['mosdepth']['index']['path'].endswith('.csi')
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        panel=page.get_by_role('region',name='mosdepth coverage results',exact=True)
        playwright.expect(panel.get_by_text('CDF denominator: 100 mosdepth-reported reference bases.',exact=True)).to_be_visible()
        playwright.expect(panel.locator('.tool-warning')).to_contain_text('chr2')
        playwright.expect(panel.get_by_text('Alignment header contains 150 reference bases.',exact=False)).to_be_visible()
        plot=panel.get_by_role('img',name='mosdepth cumulative coverage:',exact=False)
        playwright.expect(plot).to_be_visible()
        thresholds=panel.get_by_role('region',name='Original region thresholds',exact=True)
        playwright.expect(thresholds.get_by_role('rowheader',name='chr2',exact=True)).to_be_visible()
        panel.get_by_text('Series visibility (1)',exact=True).click()
        series=panel.get_by_label('Show Reported global CDF',exact=True)
        series.uncheck();series.check()
        with page.expect_download() as downloaded:
            panel.get_by_role('link',name='Download thresholds',exact=True).click()
        assert b'chr1\t0\t15\tpair\t15\t0\t0\t0' in gzip.decompress(Path(downloaded.value.path()).read_bytes())
        with page.expect_download() as image:
            panel.get_by_role('button',name='Export SVG',exact=True).click()
        svg=Path(image.value.path()).read_text()
        assert '<svg' in svg and 'NaN' not in svg
        panel.get_by_role('button',name='Reset zoom',exact=True).focus();page.keyboard.press('Enter')
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
        suffix=workspace.settings.prefix.replace('/','-') or '-root'
        page.screenshot(path='validation/coverage-native'+suffix+'.png',full_page=True)
        workspace.stop();workspace.start()
        page.goto(workspace.base+'?coverage-restored='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+name,exact=True).click()
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        playwright.expect(page.get_by_role('region',name='mosdepth coverage results').get_by_text('CDF denominator: 100 mosdepth-reported reference bases.',exact=True)).to_be_visible()
        page.get_by_role('button',name='Rerun',exact=True).click()
        playwright.expect(page.get_by_label('Target regions (optional)',exact=True)).to_have_value(label)
        page.get_by_label('Workspace',exact=True).click()
        page.get_by_role('button',name='Clear selection',exact=True).click()
        page.get_by_role('button',name='Files',exact=True).click()
        page.get_by_label('Select file '+source_cram.name,exact=True).check()
        page.get_by_role('button',name='Configure analysis',exact=True).click()
        page.get_by_role('button',name='mosdepth coverage QC',exact=False).click()
        playwright.expect(page.get_by_role('button',name='Run analysis',exact=True)).to_be_disabled()
        page.get_by_label('Local CRAM reference',exact=True).select_option(label)
        with page.expect_response(lambda r:r.url.endswith('/api/runs') and r.request.method=='POST') as created_cram:
            page.get_by_role('button',name='Run analysis',exact=True).click()
        assert created_cram.value.status==201
        with workspace.api() as api:
            crun=workspace.finish(api,created_cram.value.json())
            assert crun['qc']['reference']['id']==label
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        playwright.expect(page.get_by_role('region',name='mosdepth coverage results').get_by_text('CDF denominator: 100 mosdepth-reported reference bases.',exact=True)).to_be_visible()
        assert hashes=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    finally:
        page.close()
        for path in (source,source_cram,index,cram_index):path.unlink(missing_ok=True)
        shutil.rmtree(directory)
