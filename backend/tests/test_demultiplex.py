"""Unmodified Illumina outputs, plus explicitly synthetic edge-case metadata."""
import base64
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.demultiplex import parse_documents,map_fastqs
from test_workspace import start,wait

ROOT=Path(__file__).parent/'fixtures/demultiplex'

def documents():return {path.name:path.read_bytes() for path in ROOT.glob('*.csv')}


def test_genuine_393_reported_values_denominators_and_unknown_version():
 result=parse_documents(documents(),'3.9.3')
 assert result['reported_tool_version'] is None and result['declared_tool_version']=='3.9.3'
 assert result['run_id']=='210615_A00302_0309_AHY3CLDSXY'
 assert result['reconciliation_state']=='matched' and not result['discrepancies']
 lane=result['lane_totals'][0]
 assert lane['reported_pf_reads']==8554720+2893684750
 assert lane['undetermined_pf_reads']==2893684750
 assert lane['undetermined_percent_of_imported_rows']==100*2893684750/(8554720+2893684750)
 assert result['demultiplex']['rows'][0]['% Reads']=='0.0029'
 assert result['quality']['rows'][0]['YieldQ30']=='231205514'
 assert result['index_hopping']['rows'][0]['% of Hopped Reads']=='' # Unavailable, never zero.
 assert result['sample_sheet']['rows'][0]['index2']=='GAGCATCTAT'


def test_genuine_363_and_missing_reports_never_claim_sample_identity():
 result=parse_documents({'Demultiplex_Stats.csv':(ROOT/'3.6.3/Demultiplex_Stats.csv').read_bytes()})
 assert result['demultiplex']['schema']=='bclconvert.demux.3.6-family'
 assert result['reconciliation_state']=='not_evaluated' and result['sample_sheet'] is None
 assert result['demultiplex']['rows'][0]['# Reads']=='228354192'
 result=parse_documents({'SampleSheet.csv':documents()['SampleSheet.csv']})
 assert result['state']=='not_evaluated'


def test_v2_sample_sheet_mismatch_unknown_schema_empty_hopping_and_csv_errors():
 original=documents();modified=dict(original)
 modified['SampleSheet.csv']=original['SampleSheet.csv'].replace(b'GAGCATCTAT',b'ATAGATGCTC')
 result=parse_documents(modified)
 assert any(item['code']=='index_mismatch' for item in result['discrepancies'])
 v2=b'[BCLConvert_Settings]\nAdapterRead1,AGATCGGA\n[BCLConvert_Data]\nLane,Sample_ID,index,index2\n1,A,ACGT,TGCA\n'
 result=parse_documents({'SampleSheet.csv':v2})
 assert result['sample_sheet']['schema']=='Illumina SampleSheet v2 data section'
 assert result['sample_sheet']['settings']['[bclconvert_settings]'][0]==['AdapterRead1','AGATCGGA']
 for name,raw in [('Demultiplex_Stats.csv',b'unknown,columns\nx,y'),('SampleSheet.csv',b'[Data]\nSample_ID,index\n"unterminated'),('Demultiplex_Stats.csv',b'\xff')]:
  with pytest.raises(ValueError):parse_documents({name:raw})


def test_fastq_mappings_are_explicit_unique_lane_read_identities():
 result=parse_documents(documents());row=result['fastq_list']['rows'][0]
 file={'file_id':'read-1','filename':Path(row['Read1File']).name,'lane':'L001','read':'R1'}
 mapped=map_fastqs(result,[file])
 assert mapped[0]['state']=='matched' and mapped[0]['file_id']=='read-1'
 assert map_fastqs(result,[file,{**file,'file_id':'collision'}])[0]['state']=='ambiguous'
 assert map_fastqs(result,[{**file,'lane':'L002'}])[0]['state']=='not_observed'


def test_evidence_is_persistent_bytes_unchanged_authorized_and_bad_import_retains_previous(setup):
 settings,root=setup;headers={'Authorization':f'Bearer {settings.token}','X-QualiDock-Request':'1'}
 with TestClient(create_app(settings),headers=headers) as client:
  run=wait(client,start(client,root)['id']);base=f"/api/runs/{run['id']}"
  payload={'documents':[{'name':name,'content_base64':base64.b64encode(raw).decode()} for name,raw in documents().items()],'declared_tool_version':'3.9.3'}
  response=client.post(base+'/demultiplex',json=payload)
  assert response.status_code==200,response.text
  evidence=response.json();record=client.get(base).json()['demultiplex']
  for doc in evidence['documents']:
   assert client.get(base+'/download',params={'path':doc['artifact']}).content==documents()[doc['name']]
  bad={'documents':[{'name':'Demultiplex_Stats.csv','content_base64':base64.b64encode(b'unknown').decode()}]}
  assert client.post(base+'/demultiplex',json=bad).status_code==400
  assert client.get(base).json()['demultiplex']==record
  client.headers.pop('Authorization')
  assert client.post(base+'/demultiplex',json=payload).status_code==401
 with TestClient(create_app(settings),headers=headers) as client:
  restored=client.get(base+'/delivery').json()['demultiplex']
  assert restored['lane_totals']==evidence['lane_totals'] and restored['documents']==evidence['documents']
