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
            form.get_by_text('Optional metadata', exact=True).click()
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
        form.get_by_text('Optional metadata', exact=True).click()
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
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path='validation/native-project-workspace' + workspace.settings.prefix.replace('/', '-') + '.png', full_page=True)
        panel.get_by_role('button', name='Inspect read QC', exact=True).first.click()
        expect(page.get_by_label('Select FASTQ sample', exact=True)).to_have_value(inventory['files'][0]['report_id'])
        page.get_by_role('tab', name='Reports', exact=True).click()
        page.locator('.report-preview[aria-busy=false] iframe').wait_for()
        expect(page.get_by_label('Select HTML report', exact=True)).to_contain_text('MultiQC')
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
        page.evaluate('window.scrollTo(0,0)')
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


def test_project_batch_preview_execution_sources_and_restart(workspace, browser):
    # Synthetic explicit project identities; real existing FastQC and source fixtures.
    with workspace.api() as client:
        project = client.post('api/projects', json={'fields': {'display_name': 'Browser batch cohort'}}).json()
        base = 'api/projects/' + project['id']
        sample = client.post(base + '/samples', json={'fields': {'display_name': 'Declared batch sample'}}).json()
        runs = [client.post(base + '/sequencing-runs', json={'fields': {'display_name': f'Declared batch run {i}', 'input_stage': 'raw_fastq'}}).json() for i in [1, 2]]
        files = client.get('api/runs/' + workspace.fastqc['id'] + '/delivery').json()['files']
        assert len(files) == 2
        assignments = [{'file_id': file['file_id'], 'sample_id': sample['id'], 'sequencing_run_id': run['id'], 'read': 'unpaired'} for file, run in zip(files, runs)]
        response = client.post(base + '/analyses', json={'analysis_id': workspace.fastqc['id'], 'assignments': assignments})
        assert response.status_code == 201, response.text
    before_sources = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in INPUTS.glob('*.fastq.gz')}
    manifest = workspace.settings.output / workspace.fastqc['id'] / 'manifest.json'
    before_manifest = manifest.read_bytes()
    with browser.new_context(viewport={'width': 1440, 'height': 1100}) as context:
        page = context.new_page(); login(page, workspace)
        page.get_by_role('table', name='project records', exact=True).locator('tbody tr').filter(has_text='Browser batch cohort').get_by_role('button', name='Open project', exact=True).click()
        page.get_by_role('tab', name='Batch QC', exact=True).click()
        page.get_by_role('button', name='Choose samples', exact=True).click()
        samples = page.get_by_role('region', name='Choose batch samples', exact=True)
        samples.get_by_role('button', name='Select this page', exact=True).click()
        expect(samples).to_contain_text('1 selected')
        samples.get_by_role('button', name='Clear selection', exact=True).click()
        page.get_by_role('button', name='Preview batch plan', exact=True).click()
        expect(page.get_by_role('alert')).to_contain_text('Select at least one')
        samples.get_by_role('button', name='Select this page', exact=True).click()
        page.get_by_role('button', name='Choose sequencing runs', exact=True).click()
        sequencing = page.get_by_role('region', name='Choose batch sequencing runs', exact=True)
        sequencing.get_by_role('button', name='Select this page', exact=True).click()
        expect(sequencing).to_contain_text('2 selected')
        page.get_by_text('QC options', exact=False).click()
        page.get_by_label('Batch QC mode', exact=True).select_option('fastqc')
        page.get_by_role('button', name='Preview batch plan', exact=True).click()
        preview_panel = page.get_by_role('region', name='Batch plan preview', exact=True)
        expect(preview_panel).to_contain_text('2 FASTQs · 2 run/chunk units')
        expect(preview_panel).to_contain_text('fastqc 0.13.0')
        expect(preview_panel).to_contain_text('Run new QC')
        page.get_by_role('button', name='Confirm and queue batch', exact=True).click()
        status = page.get_by_role('region', name='Batch execution status', exact=True)
        expect(status.get_by_role('heading', name='Batch completed', exact=True)).to_be_visible(timeout=120000)
        expect(status).to_contain_text('Release: not evaluated')
        expect(status.get_by_role('table')).to_have_count(2)
        for table in status.get_by_role('table').all():
            expect(table).to_contain_text('completed · passed')
            expect(table).to_contain_text('target not evaluated')
        with workspace.api() as client:
            record = client.get(base + '/batches').json()['items'][0]
            actual = client.get(base + '/batches/' + record['id']).json()
            assert len(actual['units']) == 2 and all(unit['owned'] for unit in actual['units'])
            assert all(unit['stages']['qc']['state'] == unit['stages']['integrity']['state'] == 'completed' for unit in actual['units'])
        Path('validation').mkdir(exist_ok=True)
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path='validation/native-project-batch' + workspace.settings.prefix.replace('/', '-') + '.png', full_page=True)
        status.get_by_role('button', name='QC metrics', exact=True).first.click()
        expect(page.get_by_role('tab', name='QC metrics', exact=True)).to_have_attribute('aria-selected', 'true')
        workspace.stop(); workspace.start(); login(page, workspace)
        page.get_by_role('table', name='project records', exact=True).locator('tbody tr').filter(has_text='Browser batch cohort').get_by_role('button', name='Open project', exact=True).click()
        page.get_by_role('tab', name='Batch QC', exact=True).click()
        page.get_by_role('button', name='Open batch attempt', exact=True).first.click()
        expect(page.get_by_role('region', name='Batch execution status', exact=True)).to_contain_text(record['id'])
        page.set_viewport_size({'width': 390, 'height': 844})
        page.wait_for_function('() => document.documentElement.scrollWidth <= innerWidth', timeout=3000)
    assert before_manifest == manifest.read_bytes()
    assert before_sources == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before_sources}


def test_project_browse_first_requires_only_name_and_bulk_selects_fastqs(workspace, browser):
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in INPUTS.glob('*.fastq.gz')}
    with browser.new_context(viewport={'width': 1440, 'height': 1100}) as context:
        page = context.new_page(); login(page, workspace)
        page.get_by_role('button', name='Create project', exact=True).click()
        form = page.get_by_role('form', name='Create project', exact=True)
        expect(form.get_by_label('Declared identifier', exact=True)).not_to_be_visible()
        form.get_by_label('Project name', exact=True).fill('Browse-first project')
        form.get_by_role('button', name='Save project', exact=True).click()
        page.get_by_role('button', name='Browse & select FASTQs', exact=True).click()
        expect(page.get_by_role('region', name='Add FASTQs to project', exact=True)).to_contain_text('Browse-first project')
        page.get_by_label('Directory path', exact=True).fill(str(INPUTS))
        page.get_by_role('button', name='Go', exact=True).click()
        page.get_by_label('Select all visible samples and reports', exact=True).check()
        page.get_by_role('button', name='Configure analysis', exact=True).click()
        # Existing grouping/pair review is reused; no sample/run metadata forms.
        expect(page.get_by_role('heading', name='New analysis', exact=True)).to_be_visible()
        assert page.get_by_role('form', name='Create sample', exact=True).count() == 0
        page.get_by_role('button', name='FastQC only', exact=False).click()
        with page.expect_response(lambda response: '/start-analysis' in response.url and response.request.method == 'POST') as started:
            page.get_by_role('button', name='Run analysis', exact=True).click()
        assert started.value.status == 201, started.value.text()
        with workspace.api() as qc_client:
            child = workspace.finish(qc_client, started.value.json())
        with workspace.api() as client:
            project = next(row for row in client.get('api/projects').json()['items'] if row['declared']['display_name'] == 'Browse-first project')
            detail = client.get('api/projects/' + project['id']).json()
            assert detail['counts'] == {'sample': 1, 'sequencing_run': 1, 'analyses': 1, 'associations': 2}
            sample = client.get('api/projects/' + project['id'] + '/samples').json()['items'][0]
            assert 'assay' not in sample['declared'] and 'expected_yield' not in sample['declared']
            rows = client.get('api/projects/' + project['id'] + '/associations').json()['items']
            assert all(row['current_report_id'] for row in rows)
        assert child['project_intake']['state'] == 'registered'
        page.get_by_role('button', name='Workspace', exact=True).click()
        page.get_by_role('tab', name='Projects', exact=True).click()
        expect(page.get_by_role('heading', name='Browse-first project', exact=True)).to_be_visible()
        Path('validation').mkdir(exist_ok=True)
        page.evaluate('window.scrollTo(0,0)')
        expect(page.get_by_role('table', name='sample records', exact=True).locator('tbody tr')).to_have_count(1)
        page.screenshot(path='validation/native-project-browse-first' + workspace.settings.prefix.replace('/', '-') + '.png', full_page=True)
        # Rerun is a separate existing workflow, not an accidental new intake.
        page.get_by_role('button', name='Browse & select FASTQs', exact=True).click()
        page.get_by_role('button', name='Analyses', exact=True).click()
        page.get_by_role('button', name='Rerun Browser FastQC', exact=True).click()
        expect(page.get_by_role('heading', name='New analysis', exact=True)).to_be_visible()
        expect(page.get_by_role('region', name='Add FASTQs to project', exact=True)).not_to_be_visible()

    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}


def test_cross_run_comparison_actual_q30_declared_rule_exports_reports_and_restart(workspace, browser):
    import gzip
    import csv
    import io
    # Separate, explicitly synthetic low-quality fixture copies; original reads stay unchanged.
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in INPUTS.glob('*.fastq.gz')}
    expected_bases = {}
    for original in before:
        with gzip.open(original, 'rb') as source:
            expected_bases[original.name] = sum(len(line.rstrip(b'\r\n')) for index, line in enumerate(source) if index % 4 == 3)
    with workspace.api() as client:
        project = client.post('api/projects', json={'fields': {'display_name': 'Browser comparable runs'}}).json()
        base = 'api/projects/' + project['id']
        sample = client.post(base + '/samples', json={'fields': {'display_name': 'Declared comparison sample', 'assay': 'RNA-seq fixture', 'library_type': 'Synthetic fixture'}}).json()
        for label in ['Baseline', 'Intentional low-Q30 synthetic']:
            directory = workspace.settings.output / ('comparison-input-' + secrets.token_hex(4)); directory.mkdir()
            paths = []
            for original in sorted(INPUTS.glob('*.fastq.gz')):
                path = directory / original.name
                if label == 'Baseline':
                    path.write_bytes(original.read_bytes())
                else:
                    with gzip.open(original, 'rb') as source, gzip.open(path, 'wb') as destination:
                        for index, line in enumerate(source):
                            destination.write(b'5' * len(line.rstrip(b'\r\n')) + b'\n' if index % 4 == 3 else line)
                paths.append(str(path))
            analysis = workspace.finish(client, client.post('api/runs', json={'name': label + ' actual QC', 'mode': 'fastqc', 'paths': paths}))
            sequencing = client.post(base + '/sequencing-runs', json={'fields': {'display_name': label, 'input_stage': 'raw_fastq', 'platform': 'Declared Illumina', 'sequenced_at': '2026-10-16'}}).json()
            files = client.get('api/runs/' + analysis['id'] + '/delivery').json()['files']
            assigned = client.post(base + '/analyses', json={'analysis_id': analysis['id'], 'assignments': [{'file_id': file['file_id'], 'sample_id': sample['id'], 'sequencing_run_id': sequencing['id'], 'read': file['read'], 'lane': 'L001', 'chunk': '001', 'source': 'user_confirmed'} for file in files]})
            assert assigned.status_code == 201, assigned.text
            assert client.post('api/runs/' + analysis['id'] + '/integrity', json={'mode': 'full'}).status_code == 202
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                scan = client.get('api/runs/' + analysis['id']).json()['integrity']
                if scan['state'] not in {'queued', 'running'}: break
                time.sleep(.1)
            assert scan['state'] == 'completed' and scan['result'] == 'passed'
    with browser.new_context(viewport={'width': 1440, 'height': 1100}, accept_downloads=True) as context:
        page = context.new_page(); login(page, workspace)
        page.get_by_role('table', name='project records', exact=True).locator('tbody tr').filter(has_text='Browser comparable runs').get_by_role('button', name='Open project', exact=True).click()
        page.get_by_role('tab', name='Compare runs', exact=True).click()
        table = page.get_by_role('table', name='Cohort metric values', exact=True)
        expect(table.locator('tbody tr')).to_have_count(4)
        page.get_by_text('Context filters & optional review reference', exact=True).click()
        page.get_by_label('Optional Q30 minimum (%)', exact=True).fill('50')
        page.get_by_role('button', name='Apply comparison', exact=True).click()
        expect(table.get_by_text('Review: below declared reference', exact=True)).to_have_count(2)
        expect(table).to_contain_text(f'0 / {expected_bases["coverage_R1.fastq.gz"]} quality bases')
        expect(page.get_by_role('img', name='Cross-run Q30 bases; exact source values and denominators available in the provenance table and CSV/TSV', exact=True)).to_be_visible()
        with page.expect_download() as event:
            page.get_by_role('button', name='Export cohort CSV', exact=True).click()
        downloaded = event.value
        rows = list(csv.DictReader(io.StringIO(Path(downloaded.path()).read_text())))
        assert len(rows) == 4 and sum(row['rule_result'] == 'review' for row in rows) == 2
        assert all(row['unit'] == '%' and int(row['denominator']) == expected_bases[json.loads(row['source_provenance'])[0]['filename']] for row in rows)
        with page.expect_download() as event:
            page.get_by_role('button', name='Export SVG', exact=True).click()
        assert '<svg' in Path(event.value.path()).read_text()
        page.get_by_label('Comparison metric', exact=True).select_option('gc_percent')
        page.get_by_role('button', name='Apply comparison', exact=True).click()
        expect(page.get_by_role('region', name='Cohort comparison result', exact=True).get_by_role('heading', name='GC content (FastQC reported)', exact=True)).to_be_visible()
        expect(table.locator('tbody tr')).to_have_count(4)
        Path('validation').mkdir(exist_ok=True)
        page.screenshot(path='validation/native-project-comparison' + workspace.settings.prefix.replace('/', '-') + '.png', full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.wait_for_function('() => document.documentElement.scrollWidth <= innerWidth', timeout=3000)
        table.get_by_text('Sources (1)', exact=True).first.click()
        table.get_by_role('button', name='Original reports', exact=True).first.click()
        expect(page.get_by_label('Select HTML report', exact=True)).to_be_visible()
        workspace.stop(); workspace.start()
        login(page, workspace)
        page.get_by_role('table', name='project records', exact=True).locator('tbody tr').filter(has_text='Browser comparable runs').get_by_role('button', name='Open project', exact=True).click()
        page.get_by_role('tab', name='Compare runs', exact=True).click()
        expect(page.get_by_role('table', name='Cohort metric values', exact=True).locator('tbody tr')).to_have_count(4)
        # An explicit stage change produces separate compatible groups, not a mixed overlay.
        with workspace.api() as client:
            run = client.get(base + '/sequencing-runs').json()['items'][0]
            assert client.patch(base + '/sequencing-runs/' + run['id'], json={'revision': run['revision'], 'fields': {'input_stage': 'upstream_processed'}}).status_code == 200
        page.get_by_role('button', name='Apply comparison', exact=True).click()
        expect(page.get_by_label('Compatible definition', exact=True).locator('option')).to_have_count(2)
        expect(page.get_by_role('table', name='Cohort metric values', exact=True).locator('tbody tr')).to_have_count(2)
        page.get_by_text('Unavailable & incompatible evidence (2)', exact=True).click()
        expect(page.get_by_role('table', name='Excluded cohort evidence', exact=True)).to_contain_text('Different metric definition/tool version/stage/context')
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
