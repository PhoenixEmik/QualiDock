"""Genuine compressed/raw/derived preview through the unchanged workspace workflow."""
import gzip
import hashlib
import secrets
from pathlib import Path
from test_report_viewer import workspace, browser, playwright, INPUTS


def test_bounded_inspector_raw_pair_derived_restart(workspace,browser):
    sources=[INPUTS/f'coverage_R{n}.fastq.gz' for n in (1,2)]
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in sources]
    page=browser.new_page(viewport={'width':1400,'height':1000})
    page.goto(workspace.base+'?inspector='+secrets.token_hex(3)+'#token='+workspace.settings.token)
    page.get_by_role('button',name='Files',exact=True).click()
    page.get_by_label('Select all visible input files').check()
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/inspector')) as response:
        page.get_by_role('button',name='Inspect FASTQ',exact=True).click()
    assert response.value.status==200
    data=response.value.json()
    panel=page.get_by_role('region',name='FASTQ Inspector',exact=True)
    playwright.expect(panel.locator('.inspector-record')).to_have_count(10)
    assert len(data['files'][0]['records'])==5 and not data['paired']
    with gzip.open(sources[0],'rt') as stream:
        original=[stream.readline().rstrip() for _ in range(4)]
    first=panel.locator('.inspector-record').first
    playwright.expect(first.locator('dd code')).to_have_text([original[0][1:],original[1],original[3]])
    panel.get_by_label('I confirm the displayed order is R1 then R2').check()
    panel.get_by_label('Preview records').fill('20')
    with page.expect_response(lambda r:r.url.endswith('/api/inspector')) as compared:
        panel.get_by_role('button',name='Refresh preview').click()
    assert all(p['status']=='match' for p in compared.value.json()['pairs'])
    playwright.expect(panel.locator('.inspector-record')).to_have_count(40)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
    Path('validation').mkdir(exist_ok=True)
    page.screenshot(path='validation/inspector-mobile'+(workspace.settings.prefix.replace('/','-') or '-root')+'.png',full_page=True)
    panel.get_by_role('button',name='Close Inspector').click()
    playwright.expect(page.get_by_role('button',name='Inspect FASTQ')).to_be_focused()
    # Actual uncompressed bytes, including text that must stay escaped in React.
    plain=INPUTS/('inspector-'+secrets.token_hex(4)+'.fastq')
    malformed=INPUTS/('inspector-broken-'+secrets.token_hex(4)+'.fastq.gz')
    try:
        plain.write_bytes(b'@<img src=x onerror=alert(1)>\nACGT\n+\nI!J#\n')
        malformed.write_bytes(gzip.compress(b'@broken\nACGT\n+\nI\n'))
        for path,status in [(plain,'available'),(malformed,'unavailable')]:
            page.get_by_role('button',name='Clear selection',exact=True).click()
            page.get_by_role('button',name='Refresh directory',exact=True).click()
            page.get_by_label('Select file '+path.name,exact=True).check()
            with page.expect_response(lambda r:r.url.endswith('/api/inspector')) as viewed:
                page.get_by_role('button',name='Inspect FASTQ',exact=True).click()
            assert viewed.value.json()['files'][0]['status']==status
            if path==plain:
                playwright.expect(page.locator('.inspector-record dd').first).to_have_text('<img src=x onerror=alert(1)>')
                assert page.locator('.inspector-record img').count()==0
            page.get_by_role('button',name='Close Inspector',exact=True).click()
    finally:
        plain.unlink(missing_ok=True);malformed.unlink(missing_ok=True)
    with workspace.api() as api:
        run=workspace.finish(api,api.post('api/runs',json={'name':'Inspector derived '+secrets.token_hex(3),'mode':'fastp','paths':list(map(str,sources)),'processing_options':{'compare_qc':False}}))
    workspace.stop();workspace.start()
    page.goto(workspace.base+'?inspector-restart='+secrets.token_hex(3)+'#token='+workspace.settings.token)
    page.get_by_role('button',name='Results',exact=True).click()
    page.get_by_role('button',name='Open '+run['name'],exact=True).click()
    page.get_by_role('tab',name='QC metrics',exact=True).click()
    with page.expect_response(lambda r:r.url.endswith('/api/inspector')) as derived:
        page.get_by_role('button',name='Inspect FASTQ',exact=True).click()
    assert derived.value.status==200 and all(f['status']=='available' for f in derived.value.json()['files'])
    payload=derived.value.request.post_data_json
    assert len(payload['input_datasets'])==2
    assert all(ref['run_id']==run['id'] for ref in payload['input_datasets'])
    forbidden=page.request.post(workspace.base+'api/inspector',headers={'X-QualiDock-Request':'1'},data={'paths':['/etc/passwd']})
    assert forbidden.status==403
    assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in sources]
    page.close()
