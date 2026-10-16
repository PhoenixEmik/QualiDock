"""Project UI declarations are synthetic; QC/release evidence uses actual tools."""
import hashlib
import json
from pathlib import Path
import secrets
import time

from test_report_viewer import browser, workspace, playwright, INPUTS

expect = playwright.expect


def login(page, workspace):
    page.goto(workspace.base + '?project-test=' + secrets.token_hex(4) + '#token=' + workspace.settings.token)
    expect(page.get_by_role('heading', name='Workspace', exact=True)).to_be_visible()
    page.get_by_role('tab', name='Projects', exact=True).click()


def make_project(page, name):
    page.get_by_role('button', name='Create project', exact=True).click()
    form = page.get_by_role('form', name='Create project', exact=True)
    form.get_by_label('Project name', exact=True).fill(name)
    form.get_by_role('button', name='Save project', exact=True).click()
    expect(page.get_by_role('heading', name=name, exact=True)).to_be_visible()


def approve_actual_fixture(workspace):
    with workspace.api() as client:
        base = 'api/runs/' + workspace.combined['id']
        response = client.post(base + '/integrity', json={'mode': 'full'})
        assert response.status_code == 202, response.text
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            scan = client.get(base).json()['integrity']
            if scan['state'] not in {'queued', 'running'}:
                break
            time.sleep(.1)
        assert scan['state'] == 'completed' and scan['result'] == 'passed'
        assert client.post(base + '/release-policy', json={'version': 'browser-project-fixture-v1', 'assay': 'Explicit test contract; not a production recommendation', 'required_checks': ['integrity'], 'fastqc_rules': []}).status_code == 200
        ids = [row['sample_id'] for row in client.get(base + '/delivery').json()['yields']]
        value = client.post(base + '/release-review/evaluate', json={'sample_ids': ids}).json()
        assert value['readiness'] == 'ready'
        assert client.post(base + '/release-review', json={'sample_ids': ids, 'fingerprint': value['fingerprint'], 'action': 'approve', 'reason': 'Genuine fixture integrity reviewed for project browser acceptance'}).status_code == 200
        return ids


def test_project_sample_run_assignment_review_report_navigation_and_restart(workspace, browser):
    scope = approve_actual_fixture(workspace)
    before_inputs = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in INPUTS.glob('*.fastq.gz')}
    before_manifest = (workspace.settings.output / workspace.combined['id'] / 'manifest.json').read_bytes()
    with browser.new_context(viewport={'width': 1440, 'height': 1100}) as context:
        page = context.new_page()
        login(page, workspace)
        make_project(page, 'Browser project')
        page.get_by_role('button', name='Edit project metadata', exact=True).click()
        project_form = page.get_by_role('form', name='Edit project', exact=True)
        project_form.get_by_label('Notes', exact=True).fill('Declared project metadata reviewed in browser acceptance')
        project_form.get_by_role('button', name='Save project', exact=True).click()
        expect(project_form).not_to_be_visible()
        for identifier in ['SM1', 'SM2']:
            page.get_by_role('button', name='Create sample', exact=True).click()
            form = page.get_by_role('form', name='Create sample', exact=True)
            form.get_by_label('Sample name', exact=True).fill('Same sample label')
            form.get_by_label('Declared identifier', exact=True).fill(identifier)
            form.get_by_label('Assay / protocol', exact=True).fill('RNA-seq fixture declaration')
            form.get_by_label('Expected yield minimum', exact=True).fill('0')
            form.get_by_role('button', name='Save sample', exact=True).click()
            expect(form).not_to_be_visible()
        expect(page.get_by_role('table', name='sample records', exact=True).locator('tbody tr')).to_have_count(2)
        expect(page.get_by_role('table', name='sample records', exact=True)).to_contain_text('0 reads (declared)')
        page.get_by_role('tab', name='Sequencing runs', exact=True).click()
        page.get_by_role('button', name='Create sequencing run', exact=True).click()
        form = page.get_by_role('form', name='Create sequencing run', exact=True)
        form.get_by_label('Sequencing run name', exact=True).fill('Declared run A')
        form.get_by_label('Platform (declared)', exact=True).fill('Illumina fixture declaration')
        form.get_by_label('Sequencing date (declared)', exact=True).fill('2026-10-16')
        form.get_by_label('Input stage (declared)', exact=True).select_option('raw_fastq')
        form.get_by_role('button', name='Save sequencing run', exact=True).click()
        expect(form).not_to_be_visible()
        with workspace.api() as client:
            project = next(item for item in client.get('api/projects').json()['items'] if item['declared']['display_name'] == 'Browser project')
            base = 'api/projects/' + project['id']
            samples = client.get(base + '/samples').json()['items']
            first = next(item for item in samples if item['declared']['declared_identifier'] == 'SM1')
            second = next(item for item in samples if item['declared']['declared_identifier'] == 'SM2')
            sequencing = client.get(base + '/sequencing-runs').json()['items'][0]
        page.get_by_role('tab', name='Analyses & evidence', exact=True).click()
        page.get_by_role('button', name='Attach existing analysis', exact=True).click()
        page.get_by_label('Unassigned analysis', exact=True).select_option(workspace.combined['id'])
        page.get_by_role('button', name='Confirm analysis attachment', exact=True).click()
        row = page.get_by_role('table', name='Project linked analyses', exact=True).locator('tbody tr').filter(has_text='Browser combined')
        expect(row).to_be_visible()
        row.get_by_role('button', name='Assign / inspect files', exact=True).click()
        panel = page.get_by_role('region', name='Project file assignments', exact=True)
        panel.get_by_label('Select all visible unassigned FASTQs', exact=True).check()
        panel.get_by_label('Confirmed sample identity', exact=True).select_option(first['id'])
        panel.get_by_label('Confirmed sequencing run identity', exact=True).select_option(sequencing['id'])
        panel.get_by_role('button', name='Confirm file assignments', exact=True).click()
        expect(panel).to_contain_text('2 FASTQ references · 2 assigned · 0 unresolved')
        panel.get_by_role('button', name='Correct association', exact=True).first.click()
        panel.get_by_label('Confirmed sample identity', exact=True).select_option(second['id'])
        panel.get_by_label('Association correction reason', exact=True).fill('Explicit project metadata correction in browser acceptance')
        panel.get_by_role('button', name='Save reasoned correction', exact=True).click()
        expect(panel).to_contain_text('Revision 2')
        row.get_by_role('button', name='Capture evidence', exact=True).click()
        capture = page.get_by_role('form', name='Capture project evidence', exact=True)
        capture.get_by_label('Project evidence scope', exact=True).select_option(index=1)
        capture.get_by_role('button', name='Capture immutable snapshot', exact=True).click()
        expect(page.get_by_role('table', name='Project evidence snapshots', exact=True)).to_contain_text('approved · ready')
        expect(page.get_by_role('region', name='Project workspace detail', exact=True)).to_contain_text('Project QC/release readiness: unknown')
        with workspace.api() as client:
            link = client.get(base + '/analyses').json()['items'][0]
            inventory = client.get(base + '/analyses/' + link['id'] + '/inventory').json()
            assert {item['sample_id'] for item in inventory['associations']} == {first['id'], second['id']}
            assert client.get(base + '/evidence').json()['items'][0]['summary']['review_state'] == 'approved'
        Path('validation').mkdir(exist_ok=True)
        page.screenshot(path='validation/native-project-workspace' + workspace.settings.prefix.replace('/', '-') + '.png', full_page=True)
        panel.get_by_role('button', name='Inspect read QC', exact=True).first.click()
        expect(page.get_by_label('Select FASTQ sample', exact=True)).to_have_value(inventory['files'][0]['report_id'])
        page.get_by_role('tab', name='Reports', exact=True).click()
        page.locator('.report-preview[aria-busy=false] iframe').wait_for()
        expect(page.get_by_label('Official HTML report', exact=True)).to_contain_text('MultiQC')
        workspace.stop(); workspace.start()
        login(page, workspace)
        page.get_by_role('table', name='project records', exact=True).locator('tbody tr').filter(has_text='Browser project').get_by_role('button', name='Open project', exact=True).click()
        expect(page.get_by_role('table', name='sample records', exact=True).locator('tbody tr')).to_have_count(2)
        page.get_by_role('tab', name='Analyses & evidence', exact=True).click()
        expect(page.get_by_role('table', name='Project evidence snapshots', exact=True)).to_contain_text('approved · ready')
    assert before_inputs == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in INPUTS.glob('*.fastq.gz')}
    assert before_manifest == (workspace.settings.output / workspace.combined['id'] / 'manifest.json').read_bytes()


def test_large_sample_import_search_edit_keyboard_mobile_and_distinct_projects(workspace, browser):
    with browser.new_context(viewport={'width': 1360, 'height': 1000}) as context:
        page = context.new_page(); login(page, workspace)
        make_project(page, 'Browser large project')
        page.get_by_text('Import sample metadata', exact=True).click()
        metadata = 'display_name,declared_identifier,assay,expected_yield_metric,expected_yield_minimum\n' + '\n'.join(f'Synthetic sample {i:03},IMPORT{i:03},RNA-seq,reads,{i}' for i in range(120))
        page.get_by_label('Metadata content', exact=True).fill(metadata)
        page.get_by_role('button', name='Preview metadata import', exact=True).click()
        expect(page.get_by_role('table', name='Sample import preview', exact=True).locator('tbody tr')).to_have_count(100)
        page.get_by_role('button', name='Confirm import of 120 samples', exact=True).click()
        expect(page.get_by_role('table', name='sample records', exact=True).locator('tbody tr')).to_have_count(25)
        expect(page.get_by_role('region', name='sample records', exact=True)).to_contain_text('1–25 of 120')
        page.get_by_role('button', name='Next samples', exact=True).click()
        expect(page.get_by_role('region', name='sample records', exact=True)).to_contain_text('26–50 of 120')
        page.get_by_label('Search sample metadata', exact=True).fill('Synthetic sample 119')
        table = page.get_by_role('table', name='sample records', exact=True)
        expect(table.locator('tbody tr')).to_have_count(1)
        table.locator('tbody tr').get_by_role('button', name='Edit sample', exact=False).click()
        form = page.get_by_role('form', name='Edit sample', exact=True)
        form.get_by_label('Notes', exact=True).fill('Literal <script> metadata; not executable HTML')
        form.get_by_role('button', name='Save sample', exact=True).click()
        expect(form).not_to_be_visible()
        tab = page.get_by_role('tab', name='Samples', exact=True)
        tab.focus(); tab.press('ArrowRight')
        expect(page.get_by_role('tab', name='Sequencing runs', exact=True)).to_be_focused()
        expect(page.get_by_role('tab', name='Sequencing runs', exact=True)).to_have_attribute('aria-selected', 'true')
        page.get_by_role('tab', name='Sequencing runs', exact=True).press('Home')
        expect(page.get_by_role('tab', name='Samples', exact=True)).to_be_focused()
        page.set_viewport_size({'width': 390, 'height': 844})
        page.wait_for_function('() => document.documentElement.scrollWidth <= innerWidth', timeout=3000)
        Path('validation').mkdir(exist_ok=True)
        page.screenshot(path='validation/native-project-mobile' + workspace.settings.prefix.replace('/', '-') + '.png', full_page=True)
        with workspace.api() as client:
            projects = client.get('api/projects').json()['items']
            large = next(item for item in projects if item['declared']['display_name'] == 'Browser large project')
            sample = client.get('api/projects/' + large['id'] + '/samples', params={'search': 'Synthetic sample 119'}).json()['items'][0]
            assert sample['declared']['notes'] == 'Literal <script> metadata; not executable HTML'
            other = client.post('api/projects', json={'fields': {'display_name': 'Same labels, another project'}}).json()
            second = client.post('api/projects/' + other['id'] + '/samples', json={'fields': sample['declared']}).json()
            assert second['id'] != sample['id'] and second['project_id'] != sample['project_id']
        assert not page.locator('script').filter(has_text='Literal <script> metadata').count()
