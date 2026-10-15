"""Native multi-sample analytics against genuine persisted FastQC and MultiQC output."""
import csv
import io
from pathlib import Path
import re

from test_report_viewer import browser, workspace, open_run, playwright

expect = playwright.expect


def test_statistics_selection_status_navigation_comparison_and_exports(workspace, browser):
    with workspace.api() as client:
        before = client.get(f"api/runs/{workspace.combined['id']}").json()
        metrics = client.get(f"api/runs/{workspace.combined['id']}/metrics").json()
    with browser.new_context(viewport={"width": 1440, "height": 1000}) as context:
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        open_run(page, workspace, 'Browser combined')
        page.get_by_role('tab', name='QC metrics', exact=True).click()
        table = page.get_by_role('region', name='General Statistics table', exact=True)
        expect(table.locator('tbody tr')).to_have_count(2)
        expect(table.get_by_role('button', name=re.compile('Seqs.*reads'))).to_be_visible()
        page.get_by_label('Search statistics', exact=True).fill('coverage_R2')
        expect(table.locator('tbody tr')).to_have_count(1)
        page.get_by_label('Search statistics', exact=True).fill('')
        table.get_by_role('button', name=re.compile('Seqs')).click()
        table.get_by_role('button', name=re.compile('GC')).click(modifiers=['Shift'])
        page.locator('.analytics-columns summary').click()
        page.locator('.analytics-columns').get_by_label('FastQC · GC', exact=True).uncheck()
        expect(table.get_by_role('button', name=re.compile('^GC'))).to_have_count(0)
        page.locator('.analytics-columns').get_by_label('FastQC · GC', exact=True).check()
        for ext, delim in [('CSV', ','), ('TSV', '\t')]:
            with page.expect_download() as download:
                page.get_by_role('button', name='Export statistics '+ext, exact=True).click()
            rows = list(csv.reader(io.StringIO(Path(download.value.path()).read_text()), delimiter=delim))
            assert len(rows) == 3
            count_index = next(i for i, value in enumerate(rows[0]) if '[total_sequences]' in value)
            assert all(float(row[count_index]) == 400 for row in rows[1:])
        page.locator('.analytics-selection summary').click()
        page.get_by_role('button', name='Clear Selection', exact=True).click()
        checks = table.locator('tbody input[type=checkbox]')
        checks.first.check()
        expect(checks.first).to_be_checked()
        expect(page.locator('.analytics-selection summary')).to_contain_text('1 of 2 selected')
        page.get_by_role('button', name='Compare Samples', exact=True).click()
        expect(page.locator('.analytics-plot')).to_have_count(1)
        page.get_by_role('button', name='Select All', exact=True).click()
        page.locator('.analytics-series summary').click()
        series = page.locator('.analytics-series input[type=checkbox]')
        expect(series).to_have_count(2)
        series.first.uncheck()
        expect(series.first).not_to_be_checked()
        series.first.check()
        for metric in ['Per base sequence quality','Per sequence quality scores','Per sequence GC content','Sequence Duplication Levels','Adapter Content','Sequence Length Distribution']:
            page.get_by_label('Multi-sample metric', exact=True).select_option(metric)
            expect(page.locator('.analytics-plot canvas')).to_be_visible()
        page.get_by_label('Multi-sample metric', exact=True).select_option('Per sequence quality scores')
        page.get_by_label('Normalize to reported Total Sequences (%)', exact=True).check()
        expect(page.locator('.analytics-plot')).to_contain_text('Sequences (%)')
        for ext in ['PNG', 'SVG']:
            with page.expect_download() as download:
                page.get_by_role('button', name='Export '+ext, exact=True).click()
            content = Path(download.value.path()).read_bytes()
            assert content.startswith(b'\x89PNG') if ext == 'PNG' else b'<svg' in content
        with page.expect_download() as download:
            page.get_by_role('button', name='Export source TSV', exact=True).click()
        rows = list(csv.DictReader(io.StringIO(Path(download.value.path()).read_text()), delimiter='\t'))
        sample = metrics['samples'][0]
        original = next(m for m in sample['modules'] if m['name'] == 'Per sequence quality scores')
        for row_index, original_row in enumerate(original['rows'], 1):
            for col, value in zip(original['columns'], original_row):
                assert any(r['Report identity'] == sample['id'] and r['Row'] == str(row_index) and r['Original column'] == col and r['Reported value'] == value for r in rows)
        page.get_by_role('button', name='Overview', exact=True).click()
        page.get_by_label('Filter QC status', exact=True).select_option('fail')
        page.get_by_label('Sort QC samples', exact=True).select_option('fail')
        cell = page.locator('.qc-status-cell.fail').first
        label = cell.get_attribute('aria-label')
        cell.focus()
        cell.press('Enter')
        expect(page.get_by_role('button', name='Sample Details', exact=True)).to_have_attribute('aria-pressed','true')
        expect(page.locator('#qc-metric-heading')).to_be_focused()
        assert page.locator('#qc-metric-heading').inner_text() in label
        page.get_by_role('button', name='Compare Samples', exact=True).click()
        page.set_viewport_size({'width':390,'height':844})
        expect(page.locator('.quality-chart')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        Path('validation').mkdir(exist_ok=True)
        page.screenshot(path='validation/native-compare'+workspace.settings.prefix.replace('/','-')+'.png', full_page=True)
        assert not errors
    with workspace.api() as client:
        assert client.get(f"api/runs/{workspace.combined['id']}").json()['executions'] == before['executions']


def test_historical_and_fastqc_only_overview(workspace, browser):
    with browser.new_context() as context:
        page=context.new_page()
        for name in ['Browser historical', workspace.fastqc['name']]:
            open_run(page,workspace,name)
            page.get_by_role('tab',name='QC metrics',exact=True).click()
            expect(page.get_by_role('region',name='QC module status table',exact=True).locator('tbody tr')).to_have_count(2)
            page.get_by_role('button',name='Compare Samples',exact=True).click()
            expect(page.locator('.analytics-plot canvas')).to_be_visible()
