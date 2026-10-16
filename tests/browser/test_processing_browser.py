"""Real processing through the production UI; no replacement QC or fabricated metrics."""
import json
import re
import os
from pathlib import Path
import secrets
import shutil
import pytest
from test_report_viewer import workspace, browser, playwright


def test_select_fastqs_process_compare_download_and_restart(workspace,browser):
    assert shutil.which('fastp') and shutil.which('seqkit'), 'Provision actual processing tools before browser acceptance'
    page=browser.new_page(viewport={'width':1480,'height':1000})
    page.goto(workspace.base+'?processing='+secrets.token_hex(4)+'#token='+workspace.settings.token)
    nav=page.get_by_role('navigation',name='Main navigation')
    for label in ('Workspace','Quality Control','Read Processing','Results'):
        playwright.expect(nav.get_by_role('button',name=label,exact=True)).to_be_visible()
    # The existing browser is used directly, without a separate form for paths.
    page.get_by_role('button',name='Files',exact=True).click()
    page.get_by_label('Select all visible input files').check()
    nav.get_by_role('button',name='Read Processing',exact=True).click()
    setup=page.get_by_role('region',name='Read processing setup')
    playwright.expect(setup.get_by_text('2 FASTQ files selected',exact=True)).to_be_visible()
    setup.get_by_text('Advanced settings',exact=True).click()
    setup.get_by_label('Analysis name (optional)').fill('Browser fastp processing')
    setup.get_by_label('Generate combined MultiQC report').check()
    setup.get_by_role('button',name='Run processing',exact=True).focus()
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/runs')) as created:
        setup.get_by_role('button',name='Run processing',exact=True).press('Enter')
    assert created.value.status==201,created.value.text()
    with workspace.api() as api:
        run=workspace.finish(api,created.value.json())
        metrics=api.get(f"api/runs/{run['id']}/metrics").json()
    assert run['processing']['options']['multiqc'] is True
    assert any(report['path']=='multiqc/multiqc_report.html' for report in run['reports'])
    # Backend completion is not proof React has received its final SSE revision.
    playwright.expect(page.locator('.analysis-detail-heading .state')).to_have_text('completed',timeout=20000)
    page.get_by_role('tab',name='QC metrics',exact=True).click()
    result=page.get_by_role('region',name='Processing results')
    playwright.expect(result.get_by_role('heading',name='Before / after processing',exact=True)).to_be_visible()
    playwright.expect(result.locator('.processing-charts .quality-chart')).to_have_count(2)
    before=run['processing']['units'][0]['fastp']['summary']['before_filtering']
    assert result.locator('tbody tr').filter(has_text='Total reads').first.locator('td').first.inner_text()==f"{before['total_reads']:,}"
    for chart in result.locator('.quality-chart').all():
        canvas=chart.locator('canvas').first
        playwright.expect(canvas).to_be_visible()
        page.wait_for_function('(element)=>element.getBoundingClientRect().width>300',arg=canvas.element_handle())
    directory=Path('validation');directory.mkdir(exist_ok=True)
    suffix=workspace.settings.prefix.replace('/','-') or '-root'
    page.screenshot(path=str(directory/f'native-processing-comparison{suffix}.png'),full_page=True)
    raw=result.locator('details.qc-raw-data').first
    raw.locator('summary').click()
    source=next(sample for sample in metrics['samples'] if sample['id']==run['processing']['units'][0]['raw_qc'][0]['report'])
    module=next(module for module in source['modules'] if module['name']=='Per base sequence quality')
    playwright.expect(raw.locator('tbody tr').first.locator('td')).to_have_text(module['rows'][0])
    with page.expect_download() as downloaded:
        result.get_by_role('link',name='Download FASTQ',exact=True).first.click()
    import hashlib
    assert hashlib.sha256(Path(downloaded.value.path()).read_bytes()).hexdigest()==run['derived_datasets'][0]['sha256']
    page.get_by_role('tab',name='Reports',exact=True).click()
    playwright.expect(page.get_by_label('Select HTML report')).to_have_value('multiqc/multiqc_report.html')
    workspace.stop();workspace.start()
    page.goto(workspace.base+'?restart='+secrets.token_hex(4)+'#token='+workspace.settings.token)
    page.get_by_role('button',name='Results',exact=True).click()
    page.get_by_role('button',name='Open Browser fastp processing',exact=True).click()
    page.get_by_role('tab',name='QC metrics',exact=True).click()
    playwright.expect(page.get_by_role('region',name='Processing results').get_by_role('link',name='Download FASTQ',exact=True)).to_have_count(2)
    playwright.expect(page.locator('.processing-charts .quality-chart')).to_have_count(2)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_function("() => [...document.querySelectorAll('.processing-charts .quality-chart canvas')].every(canvas => Math.abs(canvas.getBoundingClientRect().width-canvas.closest('.quality-chart').getBoundingClientRect().width)<2)")
    page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1',timeout=5000)
    page.screenshot(path=str(directory/f'native-processing-mobile{suffix}.png'),full_page=True)
    # Reuse registered outputs after restart through the UI, without a path field.
    page.set_viewport_size({'width':1480,'height':1000})
    result=page.get_by_role('region',name='Processing results')
    result.get_by_role('button',name='Clear output selection',exact=True).click()
    playwright.expect(result.get_by_role('button',name='Use as input',exact=True)).to_be_disabled()
    result.get_by_role('button',name='Select all outputs',exact=True).click()
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/reuse')) as reused:
        result.get_by_role('button',name='Use as input',exact=True).click()
    assert reused.value.status==200,reused.value.text()
    draft=reused.value.json()
    assert len(draft['input_datasets'])==2 and all(r['paired'] for r in draft['input_pairing'])
    page.get_by_role('button',name=re.compile('^FastQC only')).click()
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/runs')) as created:
        page.get_by_role('button',name='Run analysis',exact=True).click()
    with workspace.api() as api: downstream=workspace.finish(api,created.value.json())
    assert downstream['state']=='completed' and downstream['inputs']==draft['paths']
    assert {r['run_id'] for r in downstream['input_datasets']}=={run['id']}
    assert {r['sha256'] for r in downstream['input_provenance']}=={d['sha256'] for d in run['derived_datasets']}
    assert not list((workspace.settings.output/downstream['id']/'inputs').glob('*.fastq*'))
    playwright.expect(page.locator('.analysis-detail-heading .state')).to_have_text('completed',timeout=20000)
    page.close()


def test_seqkit_statistics_and_subsampling_from_shared_selection(workspace,browser):
    page=browser.new_page()
    page.goto(workspace.base+'?seqkit='+secrets.token_hex(4)+'#token='+workspace.settings.token)
    page.get_by_role('button',name='Files',exact=True).click()
    page.get_by_label('Select all visible input files').check()
    page.get_by_role('button',name='Read Processing',exact=True).click()
    page.get_by_label('Operation',exact=True).select_option('seqkit-stats')
    page.get_by_role('button',name='Browse & select FASTQs',exact=True).click()
    playwright.expect(page.get_by_role('region',name='Read processing setup')).not_to_be_visible()
    page.get_by_role('button',name='Read Processing',exact=True).click()
    playwright.expect(page.get_by_label('Operation',exact=True)).to_have_value('seqkit-stats')
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/runs')) as created:
        page.get_by_role('button',name='Run processing',exact=True).click()
    with workspace.api() as api:run=workspace.finish(api,created.value.json())
    assert all(unit['statistics'][0]['num_seqs']=='400' for unit in run['processing']['units'])
    page.get_by_role('tab',name='QC metrics',exact=True).click()
    playwright.expect(page.get_by_text('Original SeqKit statistics (reported values)',exact=True)).to_be_visible()
    page.get_by_role('button',name='Rerun',exact=True).click()
    playwright.expect(page.get_by_label('Operation',exact=True)).to_have_value('seqkit-stats')
    page.get_by_label('Operation',exact=True).select_option('seqkit-sample')
    page.get_by_label('Sampling fraction',exact=True).fill('0.25')
    page.get_by_text('Review read relationships (optional)',exact=True).click()
    playwright.expect(page.get_by_role('region',name='Sample and pairing editor')).to_be_visible()
    page.get_by_role('button',name='Confirm pair',exact=True).click()
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/runs')) as created:
        page.get_by_role('button',name='Run processing',exact=True).click()
    with workspace.api() as api:sampled=workspace.finish(api,created.value.json())
    assert all(row['source']=='confirmed' for row in sampled['input_pairing'])
    assert len(sampled['derived_datasets'])==2 and all(entry['paired'] for entry in sampled['derived_datasets'])
    assert sampled['processing']['units'][0]['output_validation']['pairs'][0]['state']=='passed'
    page.close()


def test_pair_preserving_operations_exact_count_and_missing_ids(workspace,browser):
    import gzip
    import hashlib
    page=browser.new_page(viewport={'width':1280,'height':900})
    page.goto(workspace.base+'?paired='+secrets.token_hex(4)+'#token='+workspace.settings.token)
    page.get_by_role('button',name='Files',exact=True).click()
    page.get_by_label('Select all visible input files').check()
    page.get_by_role('button',name='Read Processing',exact=True).click()
    page.get_by_label('Operation',exact=True).select_option('seqkit-filter')
    setup=page.get_by_role('region',name='Read processing setup')
    playwright.expect(setup.get_by_label('Keep R1/R2 pairs together',exact=True)).to_be_checked()
    setup.get_by_label('Keep R1/R2 pairs together',exact=True).uncheck()
    playwright.expect(setup.get_by_text('Process each file independently; outputs are explicitly unpaired.',exact=True)).to_be_visible()
    setup.get_by_label('Keep R1/R2 pairs together',exact=True).check()
    setup.get_by_label('Minimum read length (bp)',exact=True).fill('151')
    setup.get_by_label('Maximum read length (optional)',exact=True).fill('151')
    originals=sorted(workspace.settings.roots[0].glob('*.fastq.gz'))
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in originals]
    records=[]
    for path in originals:
        lines=gzip.decompress(path.read_bytes()).splitlines(keepends=True)
        records.append([b''.join(lines[n:n+4]) for n in range(0,len(lines),4)])
    expected=[i for i,reads in enumerate(zip(*records)) if all(len(r.splitlines()[1])==151 for r in reads)]
    assert len(expected)>7
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/runs')) as created:
        setup.get_by_role('button',name='Run processing',exact=True).click()
    assert created.value.status==201,created.value.text()
    with workspace.api() as api:filtered=workspace.finish(api,created.value.json())
    assert filtered['processing']['options']['preserve_pairs'] is True
    assert all(d['paired'] and d['records']==len(expected) for d in filtered['derived_datasets'])
    for mate,dataset in enumerate(filtered['derived_datasets']):
        content=gzip.decompress((Path(filtered['output_directory'])/dataset['path']).read_bytes())
        assert content==b''.join(records[mate][i] for i in expected)
    playwright.expect(page.locator('.analysis-detail-heading .state')).to_have_text('completed',timeout=20000)
    page.get_by_role('tab',name='QC metrics',exact=True).click()
    result=page.get_by_role('region',name='Processing results')
    playwright.expect(result.get_by_label('Read selection summary')).to_contain_text(f'{len(expected):,} of 400 read pairs retained')
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/reuse')) as reused:
        result.get_by_role('button',name='Use as input',exact=True).click()
    assert reused.value.status==200,reused.value.text()
    page.get_by_role('button',name='Read Processing',exact=True).click()
    page.get_by_label('Operation',exact=True).select_option('seqkit-sample')
    page.get_by_label('Sampling method',exact=True).select_option('count')
    page.get_by_label('Exact count',exact=True).fill('7')
    page.get_by_label('Random seed',exact=True).fill('73')
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
    directory=Path('validation');directory.mkdir(exist_ok=True)
    suffix=workspace.settings.prefix.replace('/','-') or '-root'
    page.screenshot(path=str(directory/f'paired-processing-setup{suffix}.png'),full_page=True)
    page.get_by_role('button',name='Run processing',exact=True).focus()
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/runs')) as created:
        page.get_by_role('button',name='Run processing',exact=True).press('Enter')
    assert created.value.status==201,created.value.text()
    with workspace.api() as api:sampled=workspace.finish(api,created.value.json())
    assert sampled['processing']['units'][0]['selection']['retained_records']==7
    assert {r['run_id'] for r in sampled['input_datasets']}=={filtered['id']}
    assert sampled['processing']['units'][0]['output_validation']['pairs'][0]['state']=='passed'
    playwright.expect(page.locator('.analysis-detail-heading .state')).to_have_text('completed',timeout=20000)
    page.get_by_role('button',name='Rerun',exact=True).click()
    playwright.expect(page.get_by_label('Exact count',exact=True)).to_have_value('7')
    playwright.expect(page.get_by_label('Random seed',exact=True)).to_have_value('73')
    page.get_by_label('Operation',exact=True).select_option('seqkit-extract')
    identifier=records[0][expected[0]].splitlines()[0].split()[0][1:].decode()
    normalized=re.sub(r'/[12]$','',identifier)
    page.get_by_label('Exact read identifiers (one per line)',exact=True).fill(normalized+'/1\n'+normalized+'/2\nmissing-read')
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/runs')) as created:
        page.get_by_role('button',name='Run processing',exact=True).click()
    assert created.value.status==201,created.value.text()
    with workspace.api() as api:extracted=workspace.finish(api,created.value.json())
    selection=extracted['processing']['units'][0]['selection']
    assert selection['retained_records']==1 and selection['missing_identifiers']==['missing-read']
    for mate,dataset in enumerate(extracted['derived_datasets']):
        assert gzip.decompress((Path(extracted['output_directory'])/dataset['path']).read_bytes())==records[mate][expected[0]]
    playwright.expect(page.locator('.analysis-detail-heading .state')).to_have_text('completed',timeout=20000)
    page.get_by_role('tab',name='QC metrics',exact=True).click()
    result=page.get_by_role('region',name='Processing results')
    result.get_by_text('Missing requested identifiers (1)',exact=True).click()
    playwright.expect(result.get_by_text('missing-read',exact=True)).to_be_visible()
    with page.expect_download() as download:
        result.get_by_role('link',name='Selection details (JSON)',exact=True).click()
    assert json.loads(Path(download.value.path()).read_text())['missing_identifiers']==['missing-read']
    assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in originals]
    page.close()
