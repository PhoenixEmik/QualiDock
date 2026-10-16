"""Explicit read-only Illumina CSV evidence adapters; no demultiplexing occurs."""
import csv
import hashlib
import io
from pathlib import PurePosixPath
from decimal import Decimal,InvalidOperation

NAMES={'SampleSheet.csv','Demultiplex_Stats.csv','Quality_Metrics.csv','Index_Hopping_Counts.csv','fastq_list.csv'}
DEMUX36=['Lane','SampleID','Index','# Reads','# Perfect Index Reads','# One Mismatch Index Reads','# of >= Q30 Bases (PF)','Mean Quality Score (PF)']
DEMUX39=['Lane','SampleID','Index','# Reads','# Perfect Index Reads','# One Mismatch Index Reads','# Two Mismatch Index Reads','% Reads','% Perfect Index Reads','% One Mismatch Index Reads','% Two Mismatch Index Reads']
QUALITY=['Lane','SampleID','index','index2','ReadNumber','Yield','YieldQ30','QualityScoreSum','Mean Quality Score (PF)','% Q30']
HOPPING=['Lane','SampleID','index','index2','# Reads','% of Hopped Reads','% of All Reads']
FASTQS=['RGID','RGSM','RGLB','Lane','Read1File','Read2File']
MAX_ROWS=10000


def count(value):
    if not value.isascii() or not value.isdecimal() or int(value)>2**53-1:
        raise ValueError('Reported counts must be nonnegative safe integers')
    return int(value)


def decimal(value):
    if not value:return None
    try:number=Decimal(value)
    except InvalidOperation as exc:raise ValueError('Invalid reported numerical value') from exc
    if not number.is_finite():raise ValueError('Non-finite report value')
    return value  # Preserve the exact lexical precision of the source report.


def table(raw,allowed):
    reader=csv.reader(io.StringIO(raw.decode('utf-8-sig'),newline=''),strict=True)
    records=list(reader)
    if not records or records[0] not in allowed:
        raise ValueError('Unsupported Illumina report schema; not evaluated')
    headers=records[0]
    if len(records)>MAX_ROWS+1:raise ValueError('Report exceeds 10,000 rows')
    rows=[]
    for record in records[1:]:
        if not record:continue
        if len(record)!=len(headers) or any(len(cell)>4096 for cell in record):
            raise ValueError('Malformed or oversized Illumina CSV row')
        rows.append(dict(zip(headers,record)))
    return headers,rows


def sample_sheet(raw):
    records=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'),newline=''),strict=True))
    if len(records)>MAX_ROWS:raise ValueError('Sample sheet exceeds 10,000 rows')
    sections={};section=None
    for row in records:
        if not row or not any(row):continue
        if any(len(value)>4096 for value in row):raise ValueError('Oversized sample-sheet field')
        if row[0].startswith('[') and row[0].endswith(']'):
            section=row[0].lower()
            if section in sections:raise ValueError('Duplicate sample-sheet section')
            sections[section]=[]
        elif section:sections[section].append(row)
        else:raise ValueError('Unsupported sample sheet; expected sectioned Illumina CSV')
    keys=[key for key in ('[data]','[bclconvert_data]') if key in sections]
    if len(keys)!=1 or not sections[keys[0]]:raise ValueError('Sample sheet needs exactly one Data or BCLConvert_Data section')
    data=sections[keys[0]];headers=data[0]
    if len(headers)!=len(set(headers)) or 'Sample_ID' not in headers or 'index' not in headers:
        raise ValueError('Unsupported sample-sheet columns: Sample_ID and index are required')
    rows=[]
    for values in data[1:]:
        if len(values)!=len(headers):raise ValueError('Malformed sample-sheet data row')
        row=dict(zip(headers,values))
        if not row['Sample_ID']:raise ValueError('Sample_ID cannot be empty')
        if 'Lane' in row:count(row['Lane'])
        rows.append(row)
    run_id=None
    demux=sections.get('[demultiplexing]',[])
    if len(demux)>=2 and 'runID' in demux[0] and len(demux[1])==len(demux[0]):
        run_id=dict(zip(demux[0],demux[1]))['runID']
    return {'schema':'Illumina SampleSheet v2 data section' if keys[0]=='[bclconvert_data]' else 'Illumina SampleSheet v1 data section',
            'columns':headers,'rows':rows,'run_id':run_id,'settings':{key:rows for key,rows in sections.items() if key in {'[settings]','[bclconvert_settings]'}}}


def _parse_documents(documents,declared_version='',declared_run_id=''):
    if not documents or set(documents)-NAMES:raise ValueError('Select supported Illumina report filenames only')
    if sum(len(value) for value in documents.values())>4*1024*1024 or any(len(value)>2*1024*1024 for value in documents.values()):
        raise ValueError('Illumina evidence exceeds 2 MiB/file or 4 MiB total')
    result={'state':'available','source_tool':'Illumina BCL Convert','reported_tool_version':None,
            'declared_tool_version':declared_version or None,'version_source':'Not reported in the supported CSV schemas; any declared version is user-supplied',
            'declared_run_id':declared_run_id or None,'run_id':None,'documents':[],'sample_sheet':None,'demultiplex':None,'quality':None,'index_hopping':None,'fastq_list':None,
            'discrepancies':[],'lane_totals':[],'file_mappings':[]}
    for name,raw in documents.items():
        result['documents'].append({'name':name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
        if name=='SampleSheet.csv':
            result['sample_sheet']=sample_sheet(raw);result['run_id']=result['sample_sheet']['run_id'];continue
        allowed={'Demultiplex_Stats.csv':[DEMUX36,DEMUX39],'Quality_Metrics.csv':[QUALITY],
                 'Index_Hopping_Counts.csv':[HOPPING],'fastq_list.csv':[FASTQS]}[name]
        headers,rows=table(raw,allowed)
        for row in rows:
            if count(row['Lane'])==0:raise ValueError('Lane must be a positive integer')
            for key,value in row.items():
                if key.startswith('# ') or key in {'Yield','YieldQ30','QualityScoreSum','ReadNumber'}:count(value)
                elif key.startswith('%') or key=='Mean Quality Score (PF)':decimal(value)
        key={'Demultiplex_Stats.csv':'demultiplex','Quality_Metrics.csv':'quality','Index_Hopping_Counts.csv':'index_hopping','fastq_list.csv':'fastq_list'}[name]
        result[key]={'columns':headers,'rows':rows,'schema':('bclconvert.demux.3.6-family' if headers==DEMUX36 else 'bclconvert.demux.3.9-family') if key=='demultiplex' else 'bclconvert.'+key+'.verified-v1'}
    if result['run_id'] and declared_run_id and result['run_id']!=declared_run_id:
        result['discrepancies'].append({'code':'run_id_mismatch','message':'Declared run ID differs from SampleSheet [Demultiplexing] runID'})
    sheet=result['sample_sheet'];observed=result['demultiplex']
    if not observed:
        result['state']='not_evaluated';result['message']='Demultiplex_Stats.csv is missing; sample assignment has not been evaluated'
        return result
    rows=observed['rows'];seen=set()
    for row in rows:
        key=(row['Lane'],row['SampleID'],row['Index'])
        if key in seen:raise ValueError('Duplicate lane/sample/index observations; denominator would be ambiguous')
        seen.add(key)
    for lane in dict.fromkeys(row['Lane'] for row in rows):
        values=[row for row in rows if row['Lane']==lane];total=sum(count(row['# Reads']) for row in values)
        if total>2**53-1:raise ValueError('Lane count exceeds exact supported integer range')
        unknown=[row for row in values if row['SampleID']=='Undetermined']
        undetermined=sum(count(row['# Reads']) for row in unknown) if unknown else None
        result['lane_totals'].append({'lane':lane,'reported_pf_reads':total,'undetermined_pf_reads':undetermined,
                                     'undetermined_percent_of_imported_rows':100*undetermined/total if undetermined is not None and total else None,
                                     'denominator':'Sum of # Reads across imported unique lane/sample/index rows; full run coverage is not independently verified. Not the sum of R1 and R2 FASTQ records.'})
    if sheet:
        expected=sheet['rows'];matched=set();identities=set()
        for index,row in enumerate(expected):
            key=(row.get('Lane'),row['Sample_ID'],row.get('index',''),row.get('index2',''))
            if key in identities:result['discrepancies'].append({'code':'duplicate_expected','message':f'Duplicate sample-sheet identity at data row {index+1}'})
            identities.add(key)
        for row in rows:
            if row['SampleID']=='Undetermined':continue
            candidates=[(index,entry) for index,entry in enumerate(expected) if entry['Sample_ID']==row['SampleID'] and (not entry.get('Lane') or int(entry['Lane'])==int(row['Lane']))]
            barcode=lambda entry: '-'.join(value for value in (entry.get('index',''),entry.get('index2','')) if value).upper()
            exact=[index for index,entry in candidates if barcode(entry)==row['Index'].upper()]
            if len(exact)==1:matched.add(exact[0])
            else:result['discrepancies'].append({'code':'index_mismatch' if candidates else 'unexpected_sample','message':f"Lane {row['Lane']}, {row['SampleID']}, index {row['Index']}: no unique exact sample-sheet assignment; i5 orientation is not inferred"})
        for index,row in enumerate(expected):
            if index not in matched:result['discrepancies'].append({'code':'missing_expected_sample','message':f"Sample-sheet row {index+1}: {row['Sample_ID']} lane {row.get('Lane','all observed lanes')} was not uniquely matched"})
    else:
        result['message']='SampleSheet.csv is missing; expected sample/barcode assignment is not evaluated'
    for reference in (result.get('fastq_list') or {}).get('rows',[]):
        expected_barcode = reference['RGID'].rsplit('.',1)[0].replace('.', '-').upper()
        compatible = [row for row in rows if row['Lane'] == reference['Lane'] and row['SampleID'] == reference['RGSM'] and row['Index'].upper() == expected_barcode]
        if len(compatible) != 1:
            result['discrepancies'].append({'code':'fastq_list_mismatch','message':f"FASTQ list {reference['RGSM']} lane {reference['Lane']} has no unique matching demultiplex sample/index observation"})
    result['reconciliation_state']='review_required' if result['discrepancies'] else 'matched' if sheet else 'not_evaluated'
    return result


def map_fastqs(evidence,files):
    """Use explicit fastq_list identities only; imported paths are never opened."""
    result=[]
    for row in (evidence.get('fastq_list') or {}).get('rows',[]):
        for read,key in [('R1','Read1File'),('R2','Read2File')]:
            if not row[key]:continue
            name=PurePosixPath(row[key]).name
            matches=[file for file in files if file['filename']==name and file['lane']==f"L{int(row['Lane']):03d}" and file['read']==read]
            result.append({'sample_id_reported':row['RGSM'],'lane':row['Lane'],'read':read,'reported_filename':name,
                           'file_id':matches[0]['file_id'] if len(matches)==1 else None,'state':'matched' if len(matches)==1 else 'ambiguous' if matches else 'not_observed',
                           'note':'Exact filename/lane/read lookup only; biological sample identity is not verified'})
    return result


def parse_documents(documents,declared_version='',declared_run_id=''):
    try:return _parse_documents(documents,declared_version,declared_run_id)
    except (csv.Error,UnicodeError) as exc:raise ValueError('Malformed UTF-8 Illumina CSV; not evaluated') from exc
