"""Synthetic history metadata exercises pagination and actual SSE recovery, not scientific QC."""
import json
from pathlib import Path
import secrets
import uuid
from test_report_viewer import browser, workspace, playwright

expect=playwright.expect


def test_bounded_history_pagination_polling_reconnect_and_selected_detail(workspace,browser):
    # Deliberately synthetic history. No scientific results or artifacts are invented.
    for n in range(35):
        identifier=uuid.uuid4().hex;directory=workspace.settings.output/identifier;directory.mkdir()
        record={'id':identifier,'name':f'Synthetic history {n:02d}','mode':'fastqc','state':'completed','stage':'Synthetic history benchmark only','created_at':f'2099-01-{n%28+1:02d}T00:00:00Z','updated_at':'2099-01-01T00:00:00Z','finished_at':None,'started_at':None,'threads':1,'inputs':[f'/synthetic/project-{n}/input-{i}.fastq.gz' for i in range(250)],'reports':[],'sample_count':0,'error':None}
        (directory/'manifest.json').write_text(json.dumps(record))
    workspace.stop();workspace.start()
    with browser.new_context(viewport={'width':1440,'height':1000}) as context:
        page=context.new_page();requests=[]
        page.on('request',lambda request:requests.append((request.method,request.url)))
        page.route('**/api/events?format=invalidation',lambda route:route.abort())
        page.goto(workspace.base+'?test-history='+secrets.token_hex(4)+'#token='+workspace.settings.token)
        page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Results',exact=True).click()
        table=page.get_by_role('region',name='Analysis list',exact=True)
        expect(table.locator('tbody tr')).to_have_count(25)
        expect(page.get_by_text('Updates polling every 5s',exact=True)).to_be_visible()
        page.get_by_role('button',name='Next analyses',exact=True).click()
        expect(table.locator('tbody tr')).to_have_count(16)
        page.get_by_role('button',name='Previous analyses',exact=True).click()
        expect(table.locator('tbody tr')).to_have_count(25)
        page.get_by_role('button',name='Next analyses',exact=True).click()
        expect(table.locator('tbody tr')).to_have_count(16)
        filter_start=len(requests)
        page.get_by_label('Search analyses',exact=True).fill('Browser FastQC')
        page.get_by_label('Filter analysis workflow',exact=True).select_option('fastqc')
        expect(table.locator('tbody tr')).to_have_count(1)
        from urllib.parse import urlparse,parse_qs
        filtered_requests=[parse_qs(urlparse(url).query) for method,url in requests[filter_start:] if method=='GET' and urlparse(url).path.endswith('/api/history') and 'Browser+FastQC' in url]
        assert filtered_requests and all(query['offset']==['0'] for query in filtered_requests)
        page.get_by_label('Search analyses',exact=True).fill('Polling renamed')
        with workspace.api() as client:
            assert client.patch(f"api/runs/{workspace.fastqc['id']}",json={'name':'Polling renamed'}).status_code==200
        expect(page.get_by_role('button',name='Open Polling renamed',exact=True)).to_be_visible(timeout=15000)
        page.unroute('**/api/events?format=invalidation')
        expect(page.get_by_text('Live updates connected',exact=True)).to_be_visible(timeout=30000)
        page.get_by_role('button',name='Open Polling renamed',exact=True).click()
        expect(page.get_by_role('region',name='FASTQ execution outcomes',exact=True)).to_contain_text('2 of 2 inputs completed')
        assert not any(method=='GET' and url.split('?')[0].endswith('/api/runs') for method,url in requests)
        # Compare actual browser request + parse cost using the compatibility endpoint.
        measured=page.evaluate('''async () => {
          const results={synthetic:true,runs:41,inputs_per_synthetic_run:250};
          for (const [name,path] of [['legacy','api/runs'],['summary','api/history?limit=25']]) {
            const start=performance.now(),response=await fetch(path),text=await response.text(),parse=performance.now();
            JSON.parse(text);results[name]={bytes:new TextEncoder().encode(text).length,request_ms:parse-start,json_parse_ms:performance.now()-parse};
          }
          return results;
        }''')
        Path('validation').mkdir(exist_ok=True)
        Path('validation/history-browser'+workspace.settings.prefix.replace('/','-')+'.json').write_text(json.dumps(measured,indent=2)+'\n')
        assert measured['summary']['bytes']<measured['legacy']['bytes']/10
        page.set_viewport_size({'width':390,'height':844})
        page.get_by_role('navigation',name='Main navigation').get_by_role('button',name='Results',exact=True).click()
        page.screenshot(path='validation/native-history-mobile'+workspace.settings.prefix.replace('/','-')+'.png',full_page=True)
        overflow=page.evaluate("""() => [...document.querySelectorAll('body *')].filter(el=>el.getBoundingClientRect().right>innerWidth+1).map(el=>({tag:el.tagName,cls:el.className,right:el.getBoundingClientRect().right,width:el.getBoundingClientRect().width})).slice(0,30)""")
        print('Mobile history overflow diagnostics:',json.dumps(overflow))
        page.wait_for_function('() => document.documentElement.scrollWidth <= innerWidth',timeout=3000)
