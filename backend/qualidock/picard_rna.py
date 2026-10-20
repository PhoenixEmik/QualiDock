"""Pinned Picard 3.5.0 RNA metrics and approved native annotations; no calculations."""
import asyncio
import hashlib
from decimal import Decimal
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from .files import approved_file
from .integrity import snapshot
from .processing import local_file
from . import picard


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    annotation: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_.-]{0,63}$')
    strand: Literal['NONE','FIRST_READ_TRANSCRIPTION_STRAND','SECOND_READ_TRANSCRIPTION_STRAND']
    rrna: str | None = Field(default=None, pattern=r'^[A-Za-z][A-Za-z0-9_.-]{0,63}$')
    histogram_pdf: bool = False
    multiqc: bool = False


def approved(settings, identity, kind='refflat'):
    configured = settings.rna_refflat_annotations if kind=='refflat' else settings.rrna_intervals
    label = 'native refFlat' if kind=='refflat' else 'rRNA interval_list'
    if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}',identity) or not isinstance(configured,dict) or identity not in configured:
        raise ValueError('Choose an administrator-approved '+label)
    if not isinstance(configured[identity],(str,Path)):
        raise ValueError('Approved '+label+' must be an absolute local path')
    try:path = approved_file(Path(configured[identity]).expanduser())
    except OSError as exc:raise ValueError('Approved '+label+' is unavailable or unreadable') from exc
    try:
        before = snapshot(path.stat())
        digest,size,records,exons = hashlib.sha256(),0,0,0
        contigs,genes,transcripts = {},{},set()
        in_intervals = False
        with path.open('rb') as stream:
            while raw := stream.readline(16385):
                size += len(raw);digest.update(raw)
                if len(raw)>16384 or size>128*1024*1024:
                    raise ValueError(label+' exceeds 16 KiB line /128 MiB total bounds')
                line=raw.decode('utf-8').rstrip('\r\n')
                if not line or line.startswith('#'):continue
                f=line.split('\t')
                if kind=='refflat':
                    if len(f)!=11 or any(not v or len(v)>16000 or any(c.isspace() or ord(c)<32 for c in v) for v in f):
                        raise ValueError('refFlat requires eleven nonempty tab-separated fields')
                    gene,tx,chrom,strand,start,end,cds_start,cds_end,count,starts,ends=f
                    if any(len(v)>1024 for v in (gene,tx,chrom)) or gene==tx or tx in transcripts or strand not in {'+','-'} or any(not v.isascii() or not v.isdecimal() for v in (start,end,cds_start,cds_end,count)):
                        raise ValueError('Invalid/duplicate refFlat gene, transcript, contig, strand or integer')
                    start,end,cds_start,cds_end,count=map(int,(start,end,cds_start,cds_end,count))
                    if not start<=cds_start<=cds_end<=end or start==end or not 1<=count<=1000 or end>2**31-1:
                        raise ValueError('Invalid refFlat transcript/coding bounds or exon count')
                    if gene in genes and genes[gene]!=(chrom,strand):raise ValueError('Ambiguous refFlat gene chromosome/strand')
                    begins,finishes=starts.removesuffix(',').split(','),ends.removesuffix(',').split(',')
                    if len(begins)!=count or len(finishes)!=count or any(not v.isascii() or not v.isdecimal() for v in begins+finishes):raise ValueError('Invalid refFlat exon arrays')
                    previous=start
                    for left,right in zip(map(int,begins),map(int,finishes)):
                        if not previous<=left<right<=end:raise ValueError('refFlat exons must be ordered, nonoverlapping and inside transcript')
                        previous=right
                    if int(begins[0])!=start or previous!=end:raise ValueError('refFlat exons must span transcript bounds')
                    transcripts.add(tx);genes[gene]=(chrom,strand);exons+=count
                    contigs[chrom]=max(contigs.get(chrom,0),end)
                else:
                    if line.startswith('@'):
                        if in_intervals:raise ValueError('interval_list header follows intervals')
                        if f[0]=='@SQ':
                            pairs=[v.split(':',1) for v in f[1:] if ':' in v]
                            tags=dict(pairs)
                            if len(tags)!=len(pairs) or len(pairs)!=len(f)-1:raise ValueError('Duplicate/malformed interval_list dictionary tags')
                            chrom,length=tags.get('SN'),tags.get('LN','')
                            if not chrom or len(chrom)>1024 or any(c.isspace() or ord(c)<33 for c in chrom) or chrom in contigs or not length.isascii() or not length.isdecimal() or not 0<int(length)<=2**31-1:raise ValueError('Invalid interval_list sequence dictionary')
                            contigs[chrom]=int(length)
                        elif f[0] not in {'@HD','@RG','@PG','@CO'}:raise ValueError('Unsupported interval_list header')
                        if len(contigs)>100000:raise ValueError('Too many interval_list references')
                        continue
                    in_intervals=True
                    if len(f)!=5 or f[0] not in contigs or f[3] not in {'+','-'} or not f[4] or any(not v.isascii() or not v.isdecimal() for v in f[1:3]) or not 1<=int(f[1])<=int(f[2])<=contigs[f[0]]:
                        raise ValueError('Invalid 1-based inclusive interval_list coordinates')
                records+=1
                if records>1000000 or exons>2000000 or len(contigs)>100000:raise ValueError(label+' exceeds annotation record/exon/contig limits')
        if not records or snapshot(path.stat())!=before:raise ValueError('Empty or changed '+label)
        return {'id':identity,'path':str(path),'snapshot':before,'sha256':digest.hexdigest(),'bytes':size,'records':records,'contigs':contigs,
                'identity':label+' SHA-256 and BAM dictionary names/coordinate bounds'+(' and lengths' if kind!='refflat' else '')+'; not independent reference-sequence or assembly verification'}
    except OSError as exc:raise ValueError('Approved '+label+' became unavailable during validation') from exc


def listing(settings,kind):
    configured=settings.rna_refflat_annotations if kind=='refflat' else settings.rrna_intervals
    if not isinstance(configured,dict):return [{'id':'configuration','available':False,'error':'Approved annotations must be a JSON object'}]
    rows=[]
    for identity in list(configured)[:32]:
        try:
            approved(settings,identity,kind);rows.append({'id':identity,'available':True,'error':None})
        except (ValueError,OSError,TypeError,UnicodeError) as exc:rows.append({'id':identity,'available':False,'error':str(exc)})
    return rows


COLUMNS = ['PF_BASES','PF_ALIGNED_BASES','RIBOSOMAL_BASES','CODING_BASES','UTR_BASES','INTRONIC_BASES','INTERGENIC_BASES',
    'IGNORED_READS','CORRECT_STRAND_READS','INCORRECT_STRAND_READS','NUM_R1_TRANSCRIPT_STRAND_READS','NUM_R2_TRANSCRIPT_STRAND_READS','NUM_UNEXPLAINED_READS',
    'PCT_R1_TRANSCRIPT_STRAND_READS','PCT_R2_TRANSCRIPT_STRAND_READS','PCT_RIBOSOMAL_BASES','PCT_CODING_BASES','PCT_UTR_BASES','PCT_INTRONIC_BASES','PCT_INTERGENIC_BASES','PCT_MRNA_BASES','PCT_USABLE_BASES','PCT_CORRECT_STRAND_READS',
    'MEDIAN_CV_COVERAGE','MEDIAN_5PRIME_BIAS','MEDIAN_3PRIME_BIAS','MEDIAN_5PRIME_TO_3PRIME_BIAS','SAMPLE','LIBRARY','READ_GROUP']
HISTOGRAM=['normalized_position','All_Reads.normalized_coverage']


def parse(path):
    if path.stat().st_size>65536:raise ValueError('Picard RNA report exceeds 64 KiB')
    with path.open('rb') as stream:raw=stream.read(65537)
    if len(raw)>65536:raise ValueError('Picard RNA report exceeds 64 KiB')
    state,values,rows=None,None,[]
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('## METRICS CLASS'):
            if state is not None or line!='## METRICS CLASS\tpicard.analysis.RnaSeqMetrics':raise ValueError('Unsupported/duplicate Picard RNA metrics class')
            state='columns';continue
        if line.startswith('## HISTOGRAM'):
            if state!='metrics' or values is None or line!='## HISTOGRAM\tjava.lang.Integer':raise ValueError('Unsupported/duplicate Picard RNA histogram')
            state='histogram-columns';continue
        if not line or line.startswith('#'):continue
        f=line.split('\t')
        if state=='columns':
            if f!=COLUMNS:raise ValueError('Unsupported Picard 3.5.0 RNA columns')
            state='metrics'
        elif state=='metrics':
            if values is not None or len(f)!=len(COLUMNS) or any(f[-3:]):raise ValueError('Picard RNA supports exactly one ALL_READS population')
            for i,v in enumerate(f[:-3]):
                if v=='':
                    if i<13 and i!=2:raise ValueError('Missing mandatory Picard RNA count')
                    continue
                n=picard.numeric(v)
                if i<13 and (not v.isascii() or not v.isdecimal()):raise ValueError('Invalid Picard RNA integer count')
                if COLUMNS[i].startswith('PCT_') and n>1:raise ValueError('Picard RNA PCT fields must be original fractions')
            values=f
            number=lambda name:picard.numeric(f[COLUMNS.index(name)] or '0')
            if sum(number(k) for k in ['CODING_BASES','UTR_BASES','INTRONIC_BASES','INTERGENIC_BASES','RIBOSOMAL_BASES'])!=number('PF_ALIGNED_BASES'):
                raise ValueError('Inconsistent Picard RNA aligned-base categories')
            if bool(f[2])!=bool(f[15]):raise ValueError('Incomplete Picard RNA rRNA evidence')
            # Validate upstream's six-decimal fractions against its own counts;
            # retain the original strings, never replace them with these checks.
            numerators={k:number(k.removeprefix('PCT_')) for k in ['PCT_CODING_BASES','PCT_UTR_BASES','PCT_INTRONIC_BASES','PCT_INTERGENIC_BASES','PCT_RIBOSOMAL_BASES']}
            numerators.update(PCT_MRNA_BASES=number('CODING_BASES')+number('UTR_BASES'),PCT_USABLE_BASES=number('CODING_BASES')+number('UTR_BASES'))
            for key,numerator in numerators.items():
                denominator=number('PF_BASES' if key=='PCT_USABLE_BASES' else 'PF_ALIGNED_BASES')
                value=f[COLUMNS.index(key)]
                if value and ((not denominator and picard.numeric(value)!=0) or (denominator and abs(picard.numeric(value)-numerator/denominator)>Decimal('0.0000005'))):
                    raise ValueError('Inconsistent Picard RNA fraction denominator')
        elif state=='histogram-columns':
            if f!=HISTOGRAM:raise ValueError('Unsupported Picard RNA histogram population')
            state='histogram'
        elif state=='histogram':
            if len(f)!=2 or f[0]!=str(len(rows)) or len(rows)>=101:raise ValueError('Picard RNA histogram requires exact positions 0–100')
            picard.numeric(f[1]);rows.append(f)
        else:raise ValueError('Unexpected Picard RNA report data')
    if values is None or state not in {'metrics','histogram'} or (state=='histogram' and len(rows)!=101):raise ValueError('Incomplete Picard RNA metrics or coverage')
    if rows and (values[1]=='0' or not any(picard.numeric(r[1])>0 for r in rows)):raise ValueError('Non-informative/inconsistent Picard RNA coverage histogram')
    return {'status':'available','metrics':{'columns':COLUMNS,'rows':[values],'total_rows':1},
            'histogram':{'columns':HISTOGRAM,'rows':rows,'total_rows':len(rows)},'coverage_available':bool(rows),
            'units':{k:'fraction' if k.startswith('PCT_') else 'bases' if k.endswith('BASES') else 'reads' if 'READS' in k else 'relative coverage/bias' for k in COLUMNS[:-3]}}


async def verify_annotations(manager,run,contigs):
    for key,kind in [('annotation','refflat'),('rrna','rrna')]:
        saved=run['qc'].get(key)
        if not saved:continue
        if await asyncio.to_thread(approved,manager.settings,saved['id'],kind)!=saved:raise ValueError('Approved '+kind+' annotation changed while queued or executing')
        if kind=='refflat':
            if any(name not in contigs or end>contigs[name] for name,end in saved['contigs'].items()):raise ValueError('refFlat contigs/coordinates do not match BAM dictionary')
        elif list(saved['contigs'].items())!=list(contigs.items()):raise ValueError('rRNA interval_list dictionary does not match BAM names, order and lengths')


async def execute(manager,run,row,contigs,stats,preflight,env):
    if dict((r[0],r[1]) for r in stats['rows']).get('is sorted:')!='1':raise ValueError('Picard RNA requires coordinate-sorted BAM; inputs are never sorted')
    await verify_annotations(manager,run,contigs)
    directory=manager.directory(run['id']);options=run['qc']['options']
    prefix,temporary,environment,reports,heap,r_version=await picard.runtime(manager,run,row,preflight,env)
    if run['id'] in manager.cancelled:return None
    target=directory/row['report']
    argv=[run['tools']['java']['executable'],'-Xms64m',f'-Xmx{heap}m',f'-XX:ActiveProcessorCount={run["threads"]}',
          '-XX:-UsePerfData','-Djava.io.tmpdir='+str(temporary),'-jar',run['tools']['picard']['executable'],'CollectRnaSeqMetrics',
          'INPUT='+row['path'],'OUTPUT='+str(target),'REF_FLAT='+run['qc']['annotation']['path'],'STRAND_SPECIFICITY='+options['strand'],
          'MINIMUM_LENGTH=500','END_BIAS_BASES=100','RRNA_FRAGMENT_PERCENTAGE=0.8','METRIC_ACCUMULATION_LEVEL=ALL_READS',
          'TMP_DIR='+str(temporary),'ASSUME_SORTED=false','VALIDATION_STRINGENCY=STRICT','CREATE_INDEX=false','CREATE_MD5_FILE=false']
    if options['rrna']:argv+=['RIBOSOMAL_INTERVALS='+run['qc']['rrna']['path']]
    plot=prefix+'.rna_coverage.pdf'
    if options['histogram_pdf']:argv+=['CHART_OUTPUT='+str(directory/plot)]
    manager.update(run,stage='Picard RNA metrics · '+row['name'])
    code=await manager.command(run,'picard',argv,directory,stdout=directory/reports['stdout'],stderr=directory/reports['diagnostics'],env=environment)
    row['exit_code']=code
    if run['id'] in manager.cancelled:return None
    result=await asyncio.to_thread(parse,local_file(directory,row['report']))
    await verify_annotations(manager,run,contigs)
    values=dict(zip(COLUMNS,result['metrics']['rows'][0]))
    if bool(values['RIBOSOMAL_BASES'])!=bool(options['rrna']):raise ValueError('Picard RNA rRNA fields disagree with requested annotation')
    warnings=[]
    if code:
        # Only the qualified chart stage may fail after complete metrics. Other
        # upstream failures never become a successful numerical result.
        diagnostic=await asyncio.to_thread(picard.text,local_file(directory,reports['diagnostics']))
        if not options['histogram_pdf'] or 'RExecutor' not in diagnostic or 'Problem invoking R to generate plot.' not in diagnostic:
            raise ValueError(f'Picard CollectRnaSeqMetrics exited {code}; see original diagnostics')
        warnings.append(f'Original Picard PDF generation failed (exit {code}); valid numerical metrics are retained')
    reports['metrics']=row['report']
    plot_status='not_requested'
    if options['histogram_pdf']:
        try:
            if code:raise ValueError('Picard chart command failed')
            await asyncio.to_thread(picard.pdf,local_file(directory,plot))
            reports['coverage_pdf']=plot;plot_status='available'
        except (ValueError,OSError) as exc:
            plot_status='unavailable';warnings.append('Original PDF unavailable: '+str(exc))
    return {**result,'reports':reports,'heap_mb':heap,'rscript_version':r_version,'plot_status':plot_status,'warnings':warnings}
