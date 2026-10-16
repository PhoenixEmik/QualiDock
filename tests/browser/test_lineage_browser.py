"""Actual raw → fastp → exact SeqKit sampling → FastQC, after server restart."""
import hashlib
import secrets
from pathlib import Path
from test_report_viewer import workspace, browser, playwright, INPUTS


def test_genuine_chain_navigation_restart_and_missing_parent(workspace,browser):
    paths=[INPUTS/f'coverage_R{n}.fastq.gz' for n in (1,2)]
    before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    suffix=secrets.token_hex(3)
    with workspace.api() as api:
        first=workspace.finish(api,api.post('api/runs',json={'name':'Lineage fastp '+suffix,'mode':'fastp','paths':list(map(str,paths)),'processing_options':{'compare_qc':False}}))
        def next_run(parent,mode,name,options=None):
            draft=api.get(f"api/runs/{parent['id']}/datasets").json()
            body={key:draft[key] for key in ('paths','input_pairing','sample_groups')}
            body.update(name=name,mode=mode,input_datasets=[{k:row[k] for k in ('run_id','dataset_id')} for row in draft['input_datasets']])
            if options: body['processing_options']=options
            return workspace.finish(api,api.post('api/runs',json=body))
        second=next_run(first,'seqkit-sample','Lineage sampled '+suffix,{'count':7,'seed':73})
        last=next_run(second,'fastqc','Lineage QC '+suffix)
    workspace.stop();workspace.start()
    page=browser.new_page(viewport={'width':1400,'height':1000})
    def open_final():
        page.goto(workspace.base+'?lineage='+secrets.token_hex(3)+'#token='+workspace.settings.token)
        page.get_by_role('button',name='Results',exact=True).click()
        page.get_by_role('button',name='Open '+last['name'],exact=True).click()
        with page.expect_response(lambda r:r.url.endswith('/lineage')) as loaded:
            page.locator('details.processing-lineage > summary').click()
        return loaded.value.json()
    data=open_final()
    assert [n['id'] for n in data['nodes']]==[first['id'],second['id'],last['id']]
    panel=page.get_by_role('region',name='Processing Lineage',exact=True)
    playwright.expect(panel.locator('.lineage-steps > li')).to_have_count(3)
    playwright.expect(panel.locator('.lineage-steps h3')).to_have_text([first['name'],second['name'],last['name']])
    panel.get_by_text('Recorded parameters',exact=True).nth(1).click()
    assert '"count": 7' in panel.locator('pre').nth(1).inner_text()
    assert len(data['nodes'][2]['parents'])==2
    assert {r['read'] for r in data['nodes'][2]['inputs']}=={'R1','R2'}
    with page.expect_download() as downloaded:
        panel.get_by_role('link',name='Download recorded FASTQ u0001:1',exact=True).first.click()
    assert hashlib.sha256(Path(downloaded.value.path()).read_bytes()).hexdigest()==first['derived_datasets'][0]['sha256']
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_function('() => document.documentElement.scrollWidth<=innerWidth+1')
    Path('validation').mkdir(exist_ok=True)
    page.screenshot(path='validation/lineage-mobile'+(workspace.settings.prefix.replace('/','-') or '-root')+'.png',full_page=True)
    # Keyboard navigation to a recorded parent uses the existing analysis route.
    parent=panel.get_by_role('button',name='Open analysis '+second['id'],exact=True)
    parent.focus();parent.press('Enter')
    playwright.expect(page.locator('.analysis-detail-heading')).to_contain_text(second['name'])
    page.locator('details.processing-lineage > summary').click()
    page.get_by_role('button',name='View reports for '+first['name'],exact=True).click()
    playwright.expect(page.get_by_role('tab',name='Reports',exact=True)).to_have_attribute('aria-selected','true')
    playwright.expect(page.get_by_label('Select HTML report')).to_be_visible()
    # Missing manifest is a partial historical view, never a guessed source edge.
    workspace.stop()
    manifest=workspace.settings.output/first['id']/'manifest.json'
    saved=manifest.with_name('manifest.test-backup')
    manifest.rename(saved)
    try:
        workspace.start()
        data=open_final()
        assert len(data['nodes'])==2
        assert all(edge['integrity']=='missing_parent' for edge in data['nodes'][0]['parents'])
        playwright.expect(page.get_by_role('region',name='Processing Lineage')).to_contain_text('missing parent')
    finally:
        workspace.stop();saved.rename(manifest);workspace.start()
    assert before==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    page.close()
