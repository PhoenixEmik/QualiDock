"""Actual Kraken2 report fixture plus explicit schema/security edge cases."""
import asyncio
import json
from pathlib import Path
import pytest
from qualidock.screening import parse_text,parse_report,resolve_database,configurations
from qualidock.tools import detect_tool
from test_workspace import start,wait

ROOT=Path(__file__).parent/'fixtures/screening'


def test_actual_kraken2_report_preserves_exact_values_and_hierarchical_denominators():
 result=parse_report(ROOT/'genuine-kraken2-2.17.1.tsv')
 assert result['records_processed']==440 and result['classified_records']==419 and result['unclassified_records']==21
 assert result['rows'][0]['reported_percent']=='4.77'
 assert result['rows'][0]['raw'][0]=='  4.77'
 assert sum(row['clade_reads'] for row in result['rows'])>result['records_processed'] # Ancestor overlap is deliberately not summed.
 assert result['rows'][0]['taxid']=='0'


def test_only_verified_six_column_schema_accepts_all_unclassified_zero_and_missing():
 assert parse_text('100.00\t7\t7\tU\t0\tunclassified\n')['classified_records']==0
 assert parse_text('100.00\t7\t0\tR\t1\troot\n')['unclassified_records']==0
 assert parse_text('')['records_processed'] is None
 for text in ['bad schema','NaN\t1\t1\tU\t0\tu','100\t-1\t0\tU\t0\tu','100\t2\t3\tU\t0\tu','100\t2\t2\tS\t5\tmissing root','100\t2\t2\tU\t0\tu\n100\t2\t2\tU\t0\tu']:
  with pytest.raises(ValueError):parse_text(text)


def test_missing_optional_tool_database_and_bad_config_do_not_break_core_qc(client,setup):
 settings,root=setup;settings.kraken2='/absent/kraken2'
 config=client.get('/api/screening').json()
 assert not config['tool']['available'] and config['databases']==[]
 run=wait(client,start(client,root,mode='fastqc')['id']);assert run['state']=='completed'
 response=client.post(f"/api/runs/{run['id']}/screening",json={'file_ids':['invented'],'database_id':'not-configured'})
 assert response.status_code==400
 settings.screening_error='Invalid optional configuration'
 assert client.get('/api/config').status_code==200
 assert client.get('/api/screening').json()['error']=='Invalid optional configuration'


def test_database_symlinks_unknown_fields_and_opts_layout_are_rejected(tmp_path,setup):
 settings,_=setup
 config={'id':'test','name':'test','version':'explicit','source':'public fixture','path':str(tmp_path)}
 for name in ['hash.k2d','taxo.k2d']:(tmp_path/name).write_bytes(b'fixture-layout-only')
 (tmp_path/'opts.k2d').write_bytes(b'x'*64)
 root,files=resolve_database(config);assert len(files)==3
 (tmp_path/'opts.k2d').write_bytes(b'x'*65)
 with pytest.raises(ValueError):resolve_database(config)
 (tmp_path/'opts.k2d').unlink();(tmp_path/'opts.k2d').symlink_to(tmp_path/'hash.k2d')
 with pytest.raises(ValueError):resolve_database(config)
 settings.screening_databases=[{**config,'arbitrary':'field'}]
 with pytest.raises(ValueError):configurations(settings)


def test_invalid_optional_json_configuration_is_reported_without_breaking_settings(tmp_path,monkeypatch):
 from qualidock.config import Settings
 monkeypatch.setenv('QUALIDOCK_ROOTS',json.dumps([str(tmp_path)]))
 monkeypatch.setenv('QUALIDOCK_SCREENING_DATABASES','not valid JSON')
 settings=Settings.from_env()
 assert settings.roots==[tmp_path.resolve()] and settings.screening_error
 assert settings.screening_databases==[]
