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
  page.get_by_text('Delivery manifest & yield',exact=True).click()
  delivery=page.get_by_role('region',name='Delivery manifest and yield',exact=True)
  expect(delivery.get_by_text('400 read pairs',exact=True)).to_be_visible()
  delivery.get_by_label('Target unit for coverage',exact=True).select_option('read_pairs')
  delivery.get_by_label('Minimum quantity for coverage',exact=True).fill('500')
  delivery.get_by_role('button',name='Save quantity targets',exact=True).click()
  expect(delivery.get_by_text('below target',exact=True)).to_be_visible()
  delivery.get_by_text('Expected delivery reconciliation',exact=False).first.click()
  delivery.get_by_label('Expected delivery manifest file',exact=True).set_input_files({'name':'expected.csv','mimeType':'text/csv','buffer':b'filename,expected_reads\ncoverage_R1.fastq.gz,400\ncoverage_R2.fastq.gz,400\nmissing_L002_R1.fastq.gz,400\n'})
  delivery.get_by_role('button',name='Import expected manifest',exact=True).click()
  expect(delivery.get_by_text('2 matched · 1 missing',exact=False)).to_be_visible()
  # Expected-manifest import also refreshes the parent analysis over REST/SSE.
  # Wait for the rendered source inventory to settle before clicking its link,
  # and check the real attachment response rather than treating a timeout as
  # evidence that the backend served a successful download.
  expect(delivery.get_by_text('Refreshing source metadata…',exact=True)).not_to_be_visible()
  manifest_link=delivery.get_by_role('link',name='Manifest JSON',exact=True)
  # A download navigation can be reported as aborted by the browser protocol;
  # inspect headers through the same authenticated context separately, while
  # retaining the original real click/download/content assertions below.
  attachment=page.request.get(manifest_link.get_attribute('href'))
  print('Manifest attachment response:',attachment.status,attachment.headers.get('content-type'),attachment.headers.get('content-disposition'))
  assert attachment.status==200
  assert attachment.headers.get('content-disposition','').startswith('attachment;')
  with page.expect_download() as manifest:
   manifest_link.click()
  exported=json.loads(Path(manifest.value.path()).read_text())
  assert exported==attachment.json()
  assert exported['yields'][0]['totals']['read_pairs']==400
  assert exported['yields'][0]['target_state']=='below_target'
  assert len(exported['reconciliation']['missing'])==1
  assert str(workspace.settings.output) not in json.dumps(exported)
  delivery.get_by_text('Illumina demultiplexing evidence · Not evaluated',exact=True).click()
  upstream=delivery.get_by_role('region',name='Illumina demultiplexing evidence',exact=True)
  fixture_dir=Path(__file__).resolve().parents[2]/'backend/tests/fixtures/demultiplex'
  upstream.get_by_label('Illumina evidence CSV files',exact=True).set_input_files([str(fixture_dir/name) for name in ['SampleSheet.csv','Demultiplex_Stats.csv','Index_Hopping_Counts.csv']])
  upstream.get_by_role('button',name='Import Illumina evidence',exact=True).click()
  expect(upstream.get_by_role('status')).to_contain_text('Sample-sheet reconciliation: matched')
  expect(upstream).to_contain_text('210615_A00302_0309_AHY3CLDSXY')
  upstream.get_by_text('Reported index-hopping metrics · 4 rows',exact=True).click()
  expect(upstream).to_contain_text('Not reported')
  delivery.get_by_text('Release review & reference bundle',exact=True).click()
  release=delivery.get_by_role('region',name='Release review and export',exact=True)
  release.get_by_text('Versioned assay / project policy',exact=True).click()
  release.get_by_label('Release policy version',exact=True).fill('browser-contract-1')
  release.get_by_label('Release policy assay',exact=True).fill('Genuine fixture browser acceptance')
  release.get_by_role('button',name='Save release policy',exact=True).click()
  expect(release.get_by_text('Readiness: blocked · review: pending',exact=True)).to_be_visible()
  release.get_by_text('Record reviewer decision / exception',exact=True).click()
  release.get_by_label('Release review action',exact=True).select_option('waive')
  for rule,reason in [('expected_delivery','Missing synthetic expectation reviewed for this fixture-only acceptance'),('quantity','Explicit pilot yield exception accepted for this genuine fixture')]:
   release.get_by_label('Release waiver rule',exact=True).select_option(rule)
   release.get_by_label('Release review reason',exact=True).fill(reason)
   release.get_by_role('button',name='Record release review',exact=True).click()
   expect(release.get_by_text('Waived: '+reason,exact=True)).to_be_visible()
  expect(release.get_by_text('Readiness: ready · review: pending',exact=True)).to_be_visible()
  release.get_by_label('Release review action',exact=True).select_option('approve')
  release.get_by_label('Release review reason',exact=True).fill('Full source validation and documented exceptions reviewed')
  release.get_by_role('button',name='Record release review',exact=True).click()
  expect(release.get_by_text('Readiness: ready · review: approved',exact=True)).to_be_visible()
  release.get_by_text('Export selected reference bundle',exact=True).click()
  release.get_by_role('button',name='Export reference bundle (approved)',exact=True).click()
  download_link=release.get_by_role('link',name='Download approved reference bundle',exact=True)
  expect(download_link).to_be_visible(timeout=30000)
  with page.expect_download() as bundle:
   download_link.click()
  import zipfile
  with zipfile.ZipFile(bundle.value.path()) as archive:
   packaged=json.loads(archive.read('manifest.json'))
   assert packaged['release_status']=='approved'
   assert packaged['yields'][0]['target_state']=='below_target'
   assert packaged['yields'][0]['totals']['read_pairs']==400
   review=json.loads(archive.read('release-review.json'))
   assert len(review['active_waivers'])==2 and review['review_state']=='approved'
  Path('validation').mkdir(exist_ok=True)
  page.screenshot(path='validation/native-release'+workspace.settings.prefix.replace('/','-')+'.png',full_page=True)
  page.screenshot(path='validation/native-delivery'+workspace.settings.prefix.replace('/','-')+'.png',full_page=True)
  page.set_viewport_size({'width':390,'height':844})
  page.wait_for_function('() => document.documentElement.scrollWidth <= innerWidth',timeout=3000)


def test_imported_fastp_native_statistics_without_fake_fastqc(workspace,browser):
 import shutil
 from pathlib import Path
 folder=workspace.settings.output/'fastp-import-example';folder.mkdir(exist_ok=True)
 source=Path(__file__).resolve().parents[2]/'backend/tests/fixtures/imported-qc/fastp/HG001.fastp.json'
 target=folder/source.name;shutil.copyfile(source,target)
 with workspace.api() as client:
  run=workspace.finish(client,client.post('api/runs',json={'name':'Imported fastp upstream','mode':'multiqc','paths':[str(target)]}))
  metrics=client.get(f"api/runs/{run['id']}/metrics").json()
  assert not metrics['samples'] and len(metrics['multiqc']['rows'])==1
 with browser.new_context(viewport={'width':1440,'height':1100}) as context:
  page=context.new_page();open_run(page,workspace,'Imported fastp upstream')
  page.get_by_role('tab',name='QC metrics',exact=True).click()
  expect(page.get_by_role('region',name='MultiQC General Statistics',exact=True)).to_contain_text('HG001.fastp.json')
  page.get_by_role('button',name='Sample Details',exact=True).click()
  expect(page.get_by_text('No FastQC module data',exact=True)).to_be_visible()


def test_optional_offline_screening_uses_real_tool_and_preserved_native_evidence(workspace,browser):
 import os
 import pytest
 if not os.environ.get('QUALIDOCK_REQUIRE_SCREENING_TESTS'):
  pytest.skip('Optional real-screening browser acceptance requires the explicitly provisioned offline fixture')
 with workspace.api() as client:
  detected=client.get('api/screening').json()
  assert detected['tool']['compatible'] and detected['tool']['version']=='2.17.1'
 with browser.new_context(viewport={'width':1440,'height':1100}) as context:
  page=context.new_page();open_run(page,workspace,'Browser FastQC')
  page.get_by_role('tab',name='Overview & logs',exact=True).click()
  page.get_by_text('Delivery manifest & yield',exact=True).click()
  page.get_by_text('Optional offline screening · Not evaluated',exact=True).click()
  panel=page.get_by_role('region',name='Optional offline screening',exact=True)
  panel.get_by_label('Offline screening reference',exact=True).select_option('official-viral-test')
  panel.get_by_label('Screening assay context',exact=True).fill('Offline fixture evidence only; limited viral reference')
  panel.get_by_label('Expected screening taxonomy IDs',exact=True).fill('4932')
  panel.get_by_role('button',name='Start offline screening',exact=True).click()
  expect(panel.get_by_text('Screening: completed',exact=False)).to_be_visible(timeout=30000)
  expect(panel.get_by_role('table',name='Kraken2 taxonomic assignments',exact=True)).to_be_visible()
  expect(panel).to_contain_text('Not explicitly listed')
  expect(panel).to_contain_text('400 / 400')
  with page.expect_download() as download:
   panel.get_by_role('button',name='Export screening TSV',exact=True).click()
  from pathlib import Path
  assert 'Clade read records' in Path(download.value.path()).read_text()
  with workspace.api() as client:
   selected=panel.get_by_label('Screening read-file evidence',exact=True).input_value()
   official=client.get(f"api/runs/{workspace.fastqc['id']}/screening-metrics",params={'file_id':selected}).json()
  taxon=official['rows'][0]
  panel.get_by_label('Search screening taxon',exact=True).fill(taxon['taxid'])
  expect(panel.get_by_role('table',name='Kraken2 taxonomic assignments',exact=True)).to_contain_text(taxon['name'].strip())
  Path('validation').mkdir(exist_ok=True)
  page.screenshot(path='validation/native-screening'+workspace.settings.prefix.replace('/','-')+'.png',full_page=True)
  page.set_viewport_size({'width':390,'height':844})
  page.wait_for_function('() => document.documentElement.scrollWidth <= innerWidth',timeout=3000)
