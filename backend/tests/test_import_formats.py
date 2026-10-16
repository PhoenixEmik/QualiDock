"""Read-only import adapters using unmodified upstream tool reports."""
import hashlib
import json
from pathlib import Path
import pytest
from qualidock.files import FileAccess,PathViolation
from qualidock.reports import discover
from qualidock.import_formats import fastp_metadata,source_mappings

ROOT=Path(__file__).parent/'fixtures/imported-qc/fastp'


def test_genuine_fastp_schema_versions_and_exact_counts():
 modern=fastp_metadata(ROOT/'HG001.fastp.json')
 raw=json.loads((ROOT/'HG001.fastp.json').read_text())
 assert modern['version']=='0.23.4'
 assert modern['before_filtering']==raw['summary']['before_filtering']
 assert modern['after_filtering']==raw['summary']['after_filtering']
 assert fastp_metadata(ROOT/'fastp.json')['version'] is None
 assert fastp_metadata(ROOT/'single.fastp.json')['before_filtering']['total_reads']==32598659


def test_discovery_allowlist_exclusions_explicit_errors_and_source_immutability(tmp_path):
 import shutil
 target=tmp_path/'report.fastp.json';shutil.copyfile(ROOT/'HG001.fastp.json',target)
 before=hashlib.sha256(target.read_bytes()).hexdigest()
 (tmp_path/'unknown.json').write_text('{"arbitrary":"data"}')
 (tmp_path/'other.txt').write_text('unsupported report')
 summary={};records=discover([tmp_path],FileAccess([tmp_path]),summary)
 assert len(records)==1 and records[0]['kind']=='fastp' and records[0]['version']=='0.23.4'
 assert summary['unsupported_files']==2 and summary['supported_reports']==1
 assert before==hashlib.sha256(target.read_bytes()).hexdigest()
 with pytest.raises(ValueError,match='Unsupported report'):discover([tmp_path/'unknown.json'],FileAccess([tmp_path]))
 outside=tmp_path.parent/'outside.json';outside.write_text('{}')
 (tmp_path/'escaped.fastp.json').symlink_to(outside)
 with pytest.raises(PathViolation):discover([tmp_path],FileAccess([tmp_path]))


def test_unknown_and_nonfinite_schemas_do_not_become_fastp(tmp_path):
 for text in ['[]','{"summary":{}}','{"summary":NaN}','{"summary":{},"summary":{}}']:
  path=tmp_path/'fastp.json';path.write_text(text)
  with pytest.raises(ValueError):fastp_metadata(path)


def test_source_mapping_supports_only_verified_shapes(tmp_path):
 path=tmp_path/'mqc.json'
 path.write_text(json.dumps({'report_data_sources':{'fastp':{'all_sections':{'A':'/owned/a.fastp.json'}},'FastQC':{'all_sections':{'B':'/owned/b_fastqc.zip'}},'unknown':{'all_sections':{'C':'/owned/c'}}}}))
 assert source_mappings(path)=={'/owned/a.fastp.json':{'A'},'/owned/b_fastqc.zip':{'B'}}
 path.write_text('{"report_data_sources": []}')
 assert source_mappings(path)=={}
