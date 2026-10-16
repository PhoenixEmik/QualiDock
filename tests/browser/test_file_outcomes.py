"""Genuine same-basename source mapping and per-file evidence in the existing UI."""
import shutil
from pathlib import Path
from test_report_viewer import browser, workspace, open_run, playwright, INPUTS

expect=playwright.expect


def test_duplicate_file_identity_outcomes_pairs_and_multiqc(workspace,browser):
    paths=[]
    for study in ['duplicate-study-a','duplicate-study-b']:
        directory=workspace.settings.output/study;directory.mkdir(exist_ok=True)
        for original in sorted(INPUTS.glob('*.fastq.gz')):
            target=directory/original.name;shutil.copyfile(original,target);paths.append(str(target))
    with workspace.api() as client:
        created=client.post('api/runs',json={'name':'Browser duplicate filenames','mode':'both','paths':paths})
        completed=workspace.finish(client,created)
        assert len(completed['input_outcomes'])==4
    with browser.new_context(viewport={'width':1440,'height':1100}) as context:
        page=context.new_page();open_run(page,workspace,'Browser duplicate filenames')
        page.get_by_role('tab',name='Overview & logs',exact=True).click()
        panel=page.get_by_role('region',name='FASTQ execution outcomes',exact=True)
        expect(panel).to_contain_text('4 of 4 inputs completed')
        panel.locator('summary').click()
        expect(panel.locator('tbody tr')).to_have_count(4)
        assert panel.locator('tbody').inner_text().count('Parsed FastQC result')==4
        with page.expect_download() as download:
            panel.get_by_role('link',name='ZIP',exact=True).first.click()
        assert Path(download.value.path()).read_bytes().startswith(b'PK')
        page.get_by_role('tab',name='QC metrics',exact=True).click()
        table=page.get_by_role('region',name='General Statistics table',exact=True)
        expect(table.locator('tbody tr')).to_have_count(4)
        page.get_by_role('button',name='Sample Details',exact=True).click()
        sample_selector=page.get_by_label('Select FASTQ sample',exact=True)
        labels=sample_selector.locator('option').all_text_contents()
        assert len(labels)==len(set(labels))==4
        page.get_by_role('button',name='R1 / R2 Comparison',exact=True).click()
        expect(page.get_by_label('Select confirmed pair',exact=True).locator('option')).to_have_count(2)
        page.get_by_role('tab',name='Reports',exact=True).click()
        expect(page.locator('.report-preview[aria-busy=false] iframe')).to_be_visible()
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_function('document.documentElement.scrollWidth <= innerWidth',timeout=3000)
