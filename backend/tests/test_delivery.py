"""Synthetic organizational metadata plus genuine read-level validation fixtures."""
from copy import deepcopy
import csv
import gzip
import io
import json
from pathlib import Path
import pytest
from qualidock.delivery import inventory,reconcile,yields,parse_expected,export_data,csv_export
from qualidock.files import FileAccess
from qualidock.sample_metadata import validate_configuration
from qualidock.integrity import scan_file,compare_pairs,snapshot
from qualidock.metrics import parse_report


def genuine():
 root=(Path(__file__).parent/'fixtures/fastqc-0.13.0').resolve()
 paths=sorted(root.glob('*.fastq.gz'))
 pairing=FileAccess([root]).pairing(paths);config=validate_configuration(paths,pairing)
 samples=[parse_report(root/f'coverage_R{read}_fastqc',f'fastqc/coverage_R{read}_fastqc.zip') for read in [1,2]]
 run={'id':'genuine','name':'Actual fixture data','mode':'fastqc','inputs':list(map(str,paths)),
      **config,'input_metadata':[{'path':str(path),**snapshot(path.stat())} for path in paths],
      'report_input_map':{sample['id']:{'path':str(path),'id':f'i_{index}'} for index,(sample,path) in enumerate(zip(samples,paths))}}
 current={str(path):{'snapshot':snapshot(path.stat())} for path in paths}
 return run,{'samples':samples},current


def test_genuine_variable_lengths_are_not_guessed_and_full_scan_yields_are_exact():
 run,metrics,current=genuine()
 before=inventory(run,metrics,current)
 assert all(row['reads']==400 and row['bases'] is None and row['q30_bases'] is None for row in before['files'])
 assert yields(before['files'],run,[])[0]['totals']['read_pairs'] is None
 scans=[];independent_bases=0;independent_q30=0
 for path in map(Path,run['inputs']):
  scans.append(scan_file({'id':path.stem,'path':str(path),'snapshot':snapshot(path.stat()),'phred_offset':33,'encoding_source':'Genuine FastQC Sanger / Illumina 1.9'}))
  with gzip.open(path,'rb') as stream:
   while stream.readline():
    independent_bases+=len(stream.readline().rstrip(b'\r\n'));stream.readline()
    independent_q30+=sum(quality>=63 for quality in stream.readline().rstrip(b'\r\n'))
 pairs=[{'id':run['input_pairing'][0]['pair_key'],'r1':run['inputs'][0],'r2':run['inputs'][1]}]
 run['integrity']={'state':'completed','result':'passed','files':scans,'pairs':compare_pairs(pairs,scans)}
 data=inventory(run,metrics,current)
 actual=yields(data['files'],run,[{'sample_id':data['files'][0]['sample_id'],'metric':'read_pairs','minimum':500}])[0]
 assert actual['totals']['reads']==800 and actual['totals']['read_pairs']==400
 assert actual['totals']['bases']==independent_bases
 assert actual['totals']['q30_bases']==independent_q30
 assert actual['target_state']=='below_target'
 assert actual['totals']['q30_percent']==100*independent_q30/independent_bases


def test_scoped_expectations_ambiguous_basenames_missing_extra_and_duplicates():
 run,metrics,current=genuine();files=inventory(run,metrics,current)['files']
 rows=[{'file_id':file['file_id'],'filename':file['filename'],'expected_reads':400} for file in files]
 assert reconcile(files,rows)['status']=='matched'
 missing=reconcile(files,[*rows,{'filename':'missing_L002_R1.fastq.gz'}])
 assert missing['status']=='review_required' and missing['missing']
 assert reconcile(files,rows[:1])['extra']==[files[1]['file_id']]
 assert reconcile(files,[rows[0],rows[0]])['duplicates']
 copies=[files[0],{**files[0],'file_id':'second-file','path':'/other/'+files[0]['filename'],'sample_id':'other-sample'}]
 assert reconcile(copies,[{'filename':files[0]['filename']}])['ambiguous']
 scoped=reconcile(copies,[{'filename':file['filename'],'sample_id':file['sample_id']} for file in copies])
 assert scoped['status']=='matched'
 assert reconcile(files,[{'file_id':files[0]['file_id'],'sha256':'0'*64}])['unavailable']
 assert reconcile(files,None)['status']=='not_evaluated'
 assert reconcile([],[])['status']=='not_evaluated'


def test_changed_or_absent_sources_do_not_reuse_current_counts_or_integrity():
 run,metrics,current=genuine();key=run['inputs'][0]
 current[key]={'error':'missing source'}
 data=inventory(run,metrics,current)
 assert not data['files'][0]['input_available'] and data['files'][0]['reads'] is None
 current[key]={'snapshot':{**current[run['inputs'][1]]['snapshot'],'mtime_ns':0}}
 assert inventory(run,metrics,current)['files'][0]['reads'] is None
 imported={**run,'mode':'multiqc','sample_input_paths':[]}
 assert inventory(imported,metrics,{})['source_kind']=='reports_only'
 assert not inventory(imported,metrics,{})['files']


def test_expected_csv_json_preserve_identity_and_zero_and_reject_unknown_schema():
 content='filename,sample_name,expected_reads,read\r\n" forward reads.fastq",C15,0,R1\r\n'
 actual=parse_expected(content,'csv')
 assert actual[0]['filename']==' forward reads.fastq' and actual[0]['expected_reads']==0
 assert parse_expected(json.dumps({'schema_version':1,'files':actual}),'json')==actual
 for malformed,format in [('filename,unknown\nx,y','csv'),('filename,filename\nx,y','csv'),('{"schema_version":2,"files":[]}', 'json'),('[{"filename":"x","expected_reads":-1}]','json')]:
  with pytest.raises(ValueError):parse_expected(malformed,format)


def test_manifest_exports_do_not_leak_absolute_paths_and_safe_csv_protects_names():
 run,metrics,current=genuine();data=inventory(run,metrics,current)
 data.update(analysis_id=run['id'],name=run['name'],reconciliation=reconcile(data['files'],[{'path':run['inputs'][0]}]),yields=[],input_stage='unknown',processing_notes='',tool_versions={'fastqc':'0.13.0'})
 data['files'][0]['sample_name']='=HYPERLINK("bad")'
 private=str(Path(run['inputs'][0]).parent)
 assert private not in json.dumps(export_data(data))
 assert private not in csv_export(data,'spreadsheet')
 assert private in csv_export(data,'verbatim',True)
 rows=list(csv.DictReader(io.StringIO(csv_export(data,'spreadsheet'))))
 assert rows[0]['sample_name']=='\t=HYPERLINK("bad")'
 assert rows[0]['reads']=='400'
 raw=list(csv.DictReader(io.StringIO(csv_export(data,'verbatim'))))
 assert raw[0]['sample_name']=='=HYPERLINK("bad")'


def test_zero_yield_and_incomplete_pairs_are_not_double_counted():
 run,metrics,current=genuine();files=inventory(run,metrics,current)['files']
 for file in files:file.update(reads=0,bases=0,q20_bases=0,q30_bases=0,quality_bases=0)
 group=files[0]['sample_id'];record=yields(files,run,[{'sample_id':group,'metric':'reads','minimum':1}])[0]
 assert record['totals']['reads']==0 and record['target_state']=='below_target'
 assert record['totals']['q30_percent'] is None and record['totals']['read_pairs'] is None


def test_multilane_chunks_use_distinct_file_ids_and_sum_only_additive_quantities():
 run,metrics,current=genuine();pair=inventory(run,metrics,current)['files']
 rows=[];evidence=[]
 for lane,chunk in [('L001','001'),('L002','001'),('L002','002')]:
  key=lane+'-'+chunk
  for index,file in enumerate(pair):
   rows.append({**file,'file_id':key+f'-R{index+1}','lane':lane,'chunk':chunk,'pair_id':key,'reads':400,'bases':40000,'q20_bases':39000,'q30_bases':38000,'quality_bases':40000,'integrity_state':'passed'})
  evidence.append({'id':key,'state':'passed'})
 run['integrity']={'pairs':evidence}
 actual=yields(rows,run,[{'sample_id':rows[0]['sample_id'],'metric':'read_pairs','minimum':1300}])[0]
 assert actual['totals']['reads']==2400 and actual['totals']['read_pairs']==1200 and actual['totals']['bases']==240000
 assert actual['totals']['q30_percent']==95 and actual['target_state']=='below_target'
 rows[-1]['bases']=None
 assert yields(rows,run,[])[0]['totals']['bases'] is None
