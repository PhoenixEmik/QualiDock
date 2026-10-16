"""Actual internal streaming validation on genuine existing FASTQ fixtures."""
from test_report_viewer import browser,workspace,open_run,playwright

expect=playwright.expect


def test_full_integrity_readonly_evidence_and_download(workspace,browser):
 with browser.new_context(viewport={'width':1440,'height':1100}) as context:
  page=context.new_page();open_run(page,workspace,'Browser FastQC')
  page.get_by_role('tab',name='Overview & logs',exact=True).click()
  panel=page.get_by_role('region',name='FASTQ integrity validation',exact=True)
  expect(panel).to_contain_text('Not evaluated')
  with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/integrity')) as response:
   panel.get_by_role('button',name='Full FASTQ validation',exact=True).click()
  assert response.value.status==202,response.value.text()
  expect(panel).to_contain_text('2 of 2 files fully validated',timeout=30000)
  expect(panel.get_by_role('status')).to_contain_text('completed · passed')
  panel.get_by_text('File and mate evidence',exact=True).click()
  expect(panel.locator('tbody tr')).to_have_count(2)
  expect(panel).to_contain_text('Matching counts and identifier order')
  with page.expect_download() as download:
   panel.get_by_role('link',name='Validation JSON',exact=True).click()
  import json
  from pathlib import Path
  result=json.loads(Path(download.value.path()).read_text())
  assert result['state']=='completed' and result['result']=='passed'
  assert all(file['records_scanned']==400 and len(file['sha256'])==64 for file in result['files'])
  with workspace.api() as client:
   run=client.get(f"api/runs/{workspace.fastqc['id']}").json()
   assert run['state']=='completed'
  page.set_viewport_size({'width':390,'height':844})
  page.wait_for_function('document.documentElement.scrollWidth <= innerWidth',timeout=3000)
