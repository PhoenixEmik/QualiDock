"""Picard CollectInsertSizeMetrics 3.5.0; no independent scientific calculations."""
import asyncio
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict
from .processing import local_file
from .metrics import bounded_text as text


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    by_library: bool = False
    include_duplicates: bool = False
    histogram_pdf: bool = False


COLUMNS = ['MEDIAN_INSERT_SIZE','MODE_INSERT_SIZE','MEDIAN_ABSOLUTE_DEVIATION','MIN_INSERT_SIZE','MAX_INSERT_SIZE',
           'MEAN_INSERT_SIZE','STANDARD_DEVIATION','READ_PAIRS','PAIR_ORIENTATION',
           *['WIDTH_OF_'+str(v)+'_PERCENT' for v in (10,20,30,40,50,60,70,80,90,95,99)],'SAMPLE','LIBRARY','READ_GROUP']


def numeric(value):
    try: result = Decimal(value)
    except InvalidOperation as exc:raise ValueError('Invalid Picard number') from exc
    if not result.is_finite() or result < 0:raise ValueError('Invalid Picard number')
    return result


def parse(path, maximum_pairs=2**63-1):
    metrics, histogram, columns, identities = [], [], [], set()
    state, total, count = None, 0, 0
    previous = -1
    with path.open('rb') as stream:
        while raw := stream.readline(16385):
            total += len(raw)
            if len(raw)>16384 or total>64*1024*1024:
                raise ValueError('Picard report exceeds 16 KiB line / 64 MiB parsing bounds')
            line = raw.decode('utf-8').rstrip('\r\n')
            if line.startswith('## METRICS CLASS'):
                if state is not None or line != '## METRICS CLASS\tpicard.analysis.InsertSizeMetrics':raise ValueError('Unsupported Picard metrics class')
                state='metric-header';continue
            if line.startswith('## HISTOGRAM'):
                if state != 'metrics' or not metrics or line != '## HISTOGRAM\tjava.lang.Integer':raise ValueError('Unsupported Picard histogram')
                state='histogram-header';continue
            if line.startswith('#') or not line:continue
            row=line.split('\t')
            if state=='metric-header':
                if row != COLUMNS:raise ValueError('Unsupported Picard insert-size columns')
                state='metrics'
            elif state=='metrics':
                if len(row)!=len(COLUMNS) or not row[7].isascii() or not row[7].isdecimal() or row[8] not in {'FR','RF','TANDEM'} or len(identities)>=3003:
                    raise ValueError('Malformed Picard insert-size metrics')
                if numeric(row[7])>maximum_pairs:raise ValueError('Picard pair observations exceed source alignment records')
                identity=(*row[-3:],row[8])
                if identity in identities:raise ValueError('Duplicate Picard population/orientation')
                identities.add(identity)
                for i,value in enumerate(row[:20]):
                    if i!=8 and value not in {'','?'}:numeric(value)
                metrics.append(row)
            elif state=='histogram-header':
                if len(row)<2 or len(row)>3004 or row[0]!='insert_size' or len(set(row))!=len(row) or any(not re.fullmatch(r'.+\.(?:fr|rf|tandem)_count',c) for c in row[1:]):
                    raise ValueError('Unsupported/ambiguous Picard histogram columns')
                columns=row;state='histogram'
            elif state=='histogram':
                if len(row)!=len(columns) or not row[0].isascii() or not row[0].isdecimal() or int(row[0])<=previous:
                    raise ValueError('Invalid Picard histogram bins')
                previous=int(row[0])
                for value in row[1:]:
                    count_value=numeric(value)
                    if count_value!=count_value.to_integral_value() or count_value>maximum_pairs:
                        raise ValueError('Picard histogram must contain bounded original integer pair counts')
                count+=1
                if count<=200:histogram.append(row)
            else:raise ValueError('Unexpected Picard report data')
    if state!='histogram' or not metrics or not count:
        raise ValueError('Incomplete Picard metrics/histogram')
    return {'status':'available', 'metrics':{'columns':COLUMNS,'rows':metrics[:200],'total_rows':len(metrics)},
            'histogram':{'columns':columns,'rows':histogram,'total_rows':count}}


def libraries(header):
    names={}
    for line in text(header).splitlines():
        if not line.startswith('@RG\t'):continue
        tags=dict(v.split(':',1) for v in line.split('\t')[1:] if ':' in v)
        sample,library=tags.get('SM'),tags.get('LB')
        if not sample or not library or library=='All_Reads' or (library in names and names[library]!=sample):
            raise ValueError('Per-library metrics require SM/LB on each read group and unambiguous library labels distinct from All_Reads')
        names[library]=sample
    if not names or len(names)>1000:raise ValueError('Per-library metrics require 1–1000 named libraries')


def pdf(path):
    if not 8<=path.stat().st_size<=32*1024*1024:raise ValueError('Missing/oversized Picard PDF')
    with path.open('rb') as stream:
        if stream.read(5)!=b'%PDF-':raise ValueError('Picard histogram is not a PDF')
        stream.seek(max(0,path.stat().st_size-1024))
        if b'%%EOF' not in stream.read():raise ValueError('Incomplete Picard histogram PDF')


async def execute(manager,run,row,stats,preflight,env):
    directory=manager.directory(run['id'])
    if dict((r[0],r[1]) for r in stats['rows']).get('is sorted:')!='1':
        raise ValueError('Picard profile requires coordinate-sorted BAM; QualiDock never sorts inputs')
    options=run['qc']['options']
    if options['by_library']:await asyncio.to_thread(libraries,local_file(directory,preflight['header']))
    prefix=f'qc/{row["id"]}/{row["id"]}'
    temporary=manager.stores.subdirectory(run['id'],f'qc/{row["id"]}/private',exist_ok=True)
    environment={**env,**{k:'' for k in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS')},
                 **{k:str(temporary) for k in ('TMPDIR','TEMP','TMP')},
                 **{k:os.devnull for k in ('R_PROFILE','R_PROFILE_USER','R_ENVIRON','R_ENVIRON_USER')}}
    reports={'stdout':prefix+'.picard.stdout.log','diagnostics':prefix+'.picard.stderr.log',
             **{'preflight_'+k:v for k,v in preflight.items()}}
    runtime_version=None
    if options['histogram_pdf']:
        runtime=run['tools']['picard'].get('rscript_executable')
        if not runtime:raise ValueError('Original Picard PDF requires Rscript; numeric histogram metrics remain available with PDF disabled')
        reports.update(r_version_stdout=prefix+'.R.version.txt',r_version_stderr=prefix+'.R.version.log')
        code=await manager.command(run,'Rscript',[runtime,'--version'],directory,stdout=directory/reports['r_version_stdout'],stderr=directory/reports['r_version_stderr'],env=environment)
        if run['id'] in manager.cancelled:return None
        raw=await asyncio.to_thread(text,local_file(directory,reports['r_version_stdout']))
        raw+='\n'+await asyncio.to_thread(text,local_file(directory,reports['r_version_stderr']))
        match=re.search(r'(?m)^Rscript \(R\) version ([0-9]+\.[0-9]+\.[0-9]+)\b',raw)
        if code or not match:raise ValueError('Cannot identify Rscript runtime for the requested original PDF')
        runtime_version=match[1]
        environment['PATH']=str(Path(runtime).parent)+os.pathsep+os.environ.get('PATH','')
    heap=max(128,(manager.settings.memory_mb-256)*3//4)
    metrics=prefix+'.insert_size_metrics.txt'
    argv=[run['tools']['java']['executable'],'-Xms64m',f'-Xmx{heap}m',f'-XX:ActiveProcessorCount={run["threads"]}',
          '-XX:-UsePerfData','-Djava.io.tmpdir='+str(temporary),'-jar',run['tools']['picard']['executable'],'CollectInsertSizeMetrics',
          'INPUT='+row['path'],'OUTPUT='+str(directory/metrics),'TMP_DIR='+str(temporary),
          'MINIMUM_PCT=0.05','DEVIATIONS=10','INCLUDE_DUPLICATES='+str(options['include_duplicates']).lower(),
          'METRIC_ACCUMULATION_LEVEL=ALL_READS','ASSUME_SORTED=false','VALIDATION_STRINGENCY=STRICT','CREATE_INDEX=false','CREATE_MD5_FILE=false']
    if options['by_library']:argv+=['METRIC_ACCUMULATION_LEVEL=LIBRARY']
    if options['histogram_pdf']:argv+=['H='+str(directory/(prefix+'.histogram.pdf'))]
    manager.update(run,stage=f'Picard insert size · {row["name"]}')
    code=await manager.command(run,'picard',argv,directory,stdout=directory/reports['stdout'],stderr=directory/reports['diagnostics'],env=environment)
    row['exit_code']=code
    if run['id'] in manager.cancelled:return None
    if code:raise ValueError(f'Picard CollectInsertSizeMetrics exited {code}; see analysis log')
    target=directory/metrics
    if not target.exists():
        diagnostic=await asyncio.to_thread(text,local_file(directory,reports['diagnostics']))
        if not re.search(r'(?m)^WARNING\t[^\n]*\tCollectInsertSizeMetrics\tTotal mapped pairs in all categories: 0\.0$',diagnostic):
            raise ValueError('Picard returned zero without metrics or an explicit zero-pair diagnostic')
        result={'status':'unavailable','mapped_pairs_reported':'0.0','metrics':{'columns':COLUMNS,'rows':[],'total_rows':0},'histogram':{'columns':[],'rows':[],'total_rows':0}}
    else:
        maximum=numeric(dict((r[0],r[1]) for r in stats['rows'])['raw total sequences:'])
        result=await asyncio.to_thread(parse,local_file(directory,metrics),maximum)
        reports['metrics']=metrics
        if options['histogram_pdf']:
            pdf_path=prefix+'.histogram.pdf'
            await asyncio.to_thread(pdf,local_file(directory,pdf_path))
            reports['histogram_pdf']=pdf_path
    return {**result,'reports':reports,'heap_mb':heap,'minimum_orientation_fraction':'0.05','deviations':'10','rscript_version':runtime_version}
