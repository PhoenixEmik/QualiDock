"""Bounded local variant inputs and original BCFtools stats; no variant engine."""
import gzip
import hashlib
import asyncio
import os
from pathlib import Path
import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from .files import VARIANT
from .integrity import snapshot
from .processing import local_file
from .store import now, save_json

HEADER_LIMIT = 4*1024*1024
LINE_LIMIT = 256*1024
MAX_SAMPLES = 10000
BGZF_EOF = bytes.fromhex('1f8b08040000000000ff0600424302001b0003000000000000000000')


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)
    per_sample: bool = False
    multiqc: bool = False


def readable(path, *, per_sample=False):
    """Call only after FileAccess authorization; read at most a bounded header."""
    if not VARIANT.search(path.name) or '##idx##' in str(path) or any(ord(c)<32 for c in str(path)) or not path.is_file() or not path.stat().st_mode & 0o444 or not os.access(path,os.R_OK):
        raise ValueError('Choose a readable canonical .vcf, .vcf.gz or .bcf input without control characters or HTSlib index syntax')
    before=snapshot(path.stat())
    with path.open('rb') as raw:
        prefix=raw.read(18)
        compressed=prefix[:2]==b'\x1f\x8b'
        bgzf=compressed and len(prefix)==18 and prefix[3]&4 and prefix[12:16]==b'BC\x02\x00'
        if bgzf:
            if path.stat().st_size<28:raise ValueError('Truncated BGZF input')
            raw.seek(-28,2)
            if raw.read()!=BGZF_EOF:raise ValueError('BGZF EOF marker missing; incomplete input is not qualified')
    if path.name.lower().endswith('.vcf.gz') != compressed and not path.name.lower().endswith('.bcf'):
        raise ValueError('Variant compression does not match the file extension')
    if path.name.lower().endswith('.bcf') and compressed and not bgzf:
        raise ValueError('Compressed BCF requires the qualified BGZF format')
    try:
        with (gzip.open(path,'rb') if compressed else path.open('rb')) as stream:
            magic=stream.read(5)
            if path.name.lower().endswith('.bcf'):
                if magic!=b'BCF\x02\x02':raise ValueError('Only qualified BCF 2.2 is supported')
                length=stream.read(4)
                if len(length)!=4 or not 1<=int.from_bytes(length,'little')<=HEADER_LIMIT:raise ValueError('Invalid or oversized BCF header')
                text=stream.read(int.from_bytes(length,'little'))
                if len(text)!=int.from_bytes(length,'little') or not text.endswith(b'\x00'):raise ValueError('Truncated BCF header')
                lines=text[:-1].splitlines(keepends=True)
            else:
                lines=[];size=0;line=magic+stream.readline(LINE_LIMIT+1)
                while True:
                    size+=len(line)
                    if len(line)>LINE_LIMIT or size>HEADER_LIMIT:raise ValueError('VCF header exceeds 256 KiB per line /4 MiB')
                    lines.append(line)
                    if line.startswith(b'#CHROM\t'):break
                    if not line.startswith(b'##'):raise ValueError('Missing or invalid VCF column header')
                    line=stream.readline(LINE_LIMIT+1)
            decoded=[line.decode('utf-8').rstrip('\r\n') for line in lines]
    except (OSError,EOFError,UnicodeError) as exc:
        raise ValueError('Invalid or truncated variant header/compression') from exc
    if not decoded or decoded[0] not in {'##fileformat=VCFv4.2','##fileformat=VCFv4.3'}:
        raise ValueError('Only genuinely qualified VCF 4.2 /4.3 headers are supported')
    if any(len(line.encode('utf-8'))>LINE_LIMIT for line in decoded) or any(not line.startswith('##') for line in decoded[:-1]) or any(line.startswith('##fileformat=') for line in decoded[1:]):
        raise ValueError('Malformed or ambiguous variant header')
    columns=decoded[-1].split('\t')
    if columns[:8]!=['#CHROM','POS','ID','REF','ALT','QUAL','FILTER','INFO'] or (len(columns)!=8 and (len(columns)<10 or columns[8]!='FORMAT')):
        raise ValueError('Unsupported VCF columns')
    samples=columns[9:]
    if len(samples)>MAX_SAMPLES or len(set(samples))!=len(samples) or any(not s or len(s)>200 or any(c.isspace() or ord(c)<32 for c in s) for s in samples):
        raise ValueError('VCF requires unique nonempty sample IDs (at most 10000,200 characters each)')
    if per_sample and not samples:raise ValueError('Per-sample statistics require input sample columns; no samples are invented')
    tags={kind:sorted({m[1] for line in decoded for m in [re.match(r'##'+kind+r'=<ID=([^,>]+),',line)] if m}) for kind in ['INFO','FORMAT']}
    if snapshot(path.stat())!=before:raise ValueError('Variant input changed during header checks')
    if not compressed and not path.name.lower().endswith('.bcf'):
        with path.open('rb') as stream:
            stream.seek(-1,2)
            if stream.read()!=b'\n':raise ValueError('Qualified text VCF requires a complete final newline')
    return {'format':'BCF 2.2' if path.name.lower().endswith('.bcf') else decoded[0].removeprefix('##fileformat='),
            'compression':'BGZF' if bgzf else 'gzip' if compressed else 'none','samples':samples,'tags':tags,'source_snapshot':before}


SUMMARY_KEYS = ['number of samples:', 'number of records:', 'number of no-ALTs:', 'number of SNPs:',
                'number of MNPs:', 'number of indels:', 'number of others:',
                'number of multiallelic sites:', 'number of multiallelic SNP sites:']


def report_text(path, maximum=16*1024*1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>maximum:raise ValueError('Variant report exceeds its regular-file parsing limit')
    with path.open('rb') as stream:raw=stream.read(maximum+1)
    if len(raw)>maximum:raise ValueError('Variant report exceeds its parsing limit')
    return raw.decode('utf-8')


SCHEMAS = {
    'SN':['key','value'],
    'TSTV':['ts','tv','ts/tv','ts (1st ALT)','tv (1st ALT)','ts/tv (1st ALT)'],
    'QUAL':['Quality','number of SNPs','number of transitions (1st ALT)','number of transversions (1st ALT)','number of indels'],
    'ST':['type','count'],
    'DP':['bin','number of genotypes','fraction of genotypes (%)','number of sites','fraction of sites (%)'],
    'PSC':['sample','nRefHom','nNonRefHom','nHets','nTransitions','nTransversions','nIndels','average depth','nSingletons','nHapRef','nHapAlt','nMissing'],
}


def number(value, integer=False):
    if len(value)>64 or not re.fullmatch(r'[0-9]+' if integer else r'[0-9]+(?:\.[0-9]+)?',value):
        raise ValueError('Invalid/nonfinite BCFtools numeric value')
    return Decimal(value)


def original(path, source, header, per_sample):
    """Stream validated original sections; never load the variant dataset."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size>16*1024*1024:
        raise ValueError('BCFtools report exceeds 16 MiB regular-file limit')
    tables={code:{'columns':columns,'rows':[],'total_rows':0} for code,columns in SCHEMAS.items()}
    charts={code:[] for code in ['QUAL','DP']}
    seen={code:set() for code in SCHEMAS};declared=set();identities=[];other=set();total=0
    sample_ids=set(header['samples']);digest=hashlib.sha256();quality_available=False;site_depth=False;genotype_depth=False
    dp_counts=[Decimal(0),Decimal(0)];dp_fractions=[Decimal(0),Decimal(0)]
    with path.open('rb') as stream:
        while raw:=stream.readline(65537):
            total+=len(raw);digest.update(raw)
            if len(raw)>65536 or total>16*1024*1024 or not raw.endswith(b'\n'):
                raise ValueError('Oversized or truncated BCFtools report line')
            line=raw.decode('utf-8').rstrip('\r\n')
            if total==len(raw) and not line.startswith('# This file was produced by bcftools stats (1.24+htslib-1.24) '):
                raise ValueError('Unsupported original BCFtools report version')
            fields=line.split('\t')
            if line.startswith('# '):
                if len(fields)>1 and fields[1]=='[2]id':
                    code=fields[0][2:]
                    if code in declared or len(declared)>=64:raise ValueError('Duplicate or ambiguous BCFtools section')
                    declared.add(code)
                    columns=[re.sub(r'^\[\d+\]','',v) for v in fields[2:]]
                    if code in SCHEMAS and columns!=SCHEMAS[code]:raise ValueError('Unsupported BCFtools column definitions')
                continue
            if not line or line.startswith('#'):continue
            code=fields[0]
            if code=='ID':identities.append(fields);continue
            if code not in SCHEMAS:
                if len(other)>=64 and code not in other:raise ValueError('Too many unrecognized original sections')
                other.add(code);continue
            if code not in declared or len(fields)!=len(SCHEMAS[code])+2 or fields[1]!='0':
                raise ValueError('Malformed or ambiguous BCFtools section identity')
            row=fields[2:];key=row[0] if code!='TSTV' else '0'
            if key in seen[code] or len(seen[code])>=50000:raise ValueError('Duplicate or oversized BCFtools section rows')
            seen[code].add(key)
            if code=='SN':number(row[1],True)
            elif code=='TSTV':
                for i,v in enumerate(row):number(v,i not in {2,5})
            elif code=='ST':
                if not re.fullmatch(r'[ACGT]>[ACGT]',row[0]) or row[0][0]==row[0][2]:raise ValueError('Invalid substitution identity')
                number(row[1],True)
            elif code=='QUAL':
                if row[0]!='.':
                    number(row[0]);quality_available|=any(number(v,True)>0 for v in row[1:])
                for v in row[1:]:number(v,True)
                if int(row[1])!=int(row[2])+int(row[3]):raise ValueError('Inconsistent original QUAL counts')
            elif code=='DP':
                if not re.fullmatch(r'[<>]?[0-9]+',row[0]):raise ValueError('Unsupported original depth bin')
                for i,v in enumerate(row[1:],1):number(v,i in {1,3})
                for i in range(2):
                    count=number(row[1+2*i],True);fraction=number(row[2+2*i])
                    if fraction>100:raise ValueError('Invalid original depth fraction')
                    dp_counts[i]+=count;dp_fractions[i]+=fraction
                if not row[0].startswith('<'):
                    genotype_depth|=number(row[1],True)>0;site_depth|=number(row[3],True)>0
                if not per_sample and number(row[1],True):raise ValueError('Unrequested genotype depth statistics')
            elif code=='PSC':
                if not per_sample or row[0] not in sample_ids:raise ValueError('Unknown/unrequested within-file sample')
                for i,v in enumerate(row[1:],1):number(v,i!=7)
            table=tables[code];table['total_rows']+=1
            if len(table['rows'])<200:table['rows'].append(row)
            if code in charts and charts[code] is not None:
                if len(charts[code])>=2000:charts[code]=None
                else:charts[code].append(row)
    required={'ID','SN','TSTV','SiS','AF','QUAL','IDD','ST','DP',*(['PSC','PSI','HWE'] if per_sample else [])}
    if not total or not required<=declared:raise ValueError('Truncated BCFtools section definitions')
    if identities!=[['ID','0',str(source)]]:raise ValueError('Ambiguous or incorrect BCFtools report source identity')
    summary=tables['SN']['rows'];values=dict(summary)
    if [r[0] for r in summary]!=SUMMARY_KEYS or int(values['number of samples:'])!=len(header['samples']):
        raise ValueError('Missing/duplicate summary or disagreement with source sample header')
    count=int(values['number of records:'])
    if any(int(v)>count for k,v in summary[2:]):raise ValueError('Summary count exceeds input record population')
    substitutions={a+'>'+b for a in 'ACGT' for b in 'ACGT' if a!=b}
    if seen['ST']!=substitutions or tables['TSTV']['total_rows']!=1:raise ValueError('Incomplete substitution/TiTv evidence')
    tstv=tables['TSTV']['rows'][0]
    transitions={'A>G','G>A','C>T','T>C'}
    ts=sum(int(r[1]) for r in tables['ST']['rows'] if r[0] in transitions)
    tv=sum(int(r[1]) for r in tables['ST']['rows'] if r[0] not in transitions)
    if [ts,tv]!=[int(tstv[0]),int(tstv[1])]:raise ValueError('Substitution and TiTv counts disagree')
    for offset in [0,3]:
        numerator,denominator,reported=map(Decimal,tstv[offset:offset+3])
        if numerator>Decimal(tstv[0]) or denominator>Decimal(tstv[1]):raise ValueError('Invalid first-ALT substitution counts')
        if denominator and abs(reported-numerator/denominator)>Decimal('0.0050000001'):
            raise ValueError('Invalid reported TiTv rounding')
        if not denominator and reported:raise ValueError('Undefined original TiTv must retain upstream zero')
    if per_sample and seen['PSC']!=sample_ids:raise ValueError('Incomplete per-sample report')
    if not per_sample and (seen['PSC'] or {'PSC','PSI','HWE'}&declared):raise ValueError('Unexpected per-sample report')
    for counts,fractions in zip(dp_counts,dp_fractions):
        if counts and abs(fractions-100)>Decimal('0.000001')*max(1,tables['DP']['total_rows']):
            raise ValueError('Truncated/inconsistent original depth distribution')
    if dp_counts[1]>count or dp_counts[0]>count*len(header['samples']):raise ValueError('Depth observations exceed record/sample population')
    for code in charts:tables[code]['chart_rows']=charts[code]
    samples=tables['PSC']
    # Upstream average depth 0.0 conflates missing observations and measured zero.
    # Keep the raw original downloadable; omit that ambiguous native column.
    samples={'columns':[v for i,v in enumerate(samples['columns']) if i!=7],
             'rows':[[v for i,v in enumerate(row) if i!=7] for row in samples['rows']], 'total_rows':samples['total_rows']}
    return {'status':'available','summary':{'columns':['Original BCFtools metric','Reported value'],'rows':summary,'total_rows':len(summary)},
            'input_format':header['format'],'compression':header['compression'],'sample_count':len(header['samples']),
            'per_sample_requested':per_sample,'sample_statistics_available':per_sample and 'GT' in header['tags']['FORMAT'],
            'quality_available':quality_available,'site_depth_available':site_depth,'genotype_depth_available':genotype_depth,
            'report_sha256':digest.hexdigest(),'header_tags':header['tags'],
            'tstv':tables['TSTV'],'tstv_ratio':tstv[2] if tv else None,
            'quality':tables['QUAL'],'depth':tables['DP'],'substitutions':tables['ST'],'sample_counts':samples,
            'uninterpreted_sections':sorted(other)}


async def execute(manager,run,metrics,errors):
    directory=manager.directory(run['id']);options=run['qc']['options']
    for row in run['qc']['results']:
        if run['id'] in manager.cancelled:break
        try:
            paths=await asyncio.to_thread(manager.checked_inputs,run)
            source=next(p for p in paths if str(p)==row['path'])
            header=await asyncio.to_thread(readable,source,per_sample=options['per_sample'])
            manager.stores.subdirectory(run['id'],f'qc/{row["id"]}',exist_ok=True)
            reports={'stats':row['report'],'diagnostics':f'qc/{row["id"]}/{row["id"]}.bcftools.log'}
            row['state']='running';manager.update(run,stage=f'BCFtools stats · {row["name"]}')
            argv=[run['tools']['bcftools']['executable'],'stats','--threads',str(run['threads']-1),
                  *(['--samples','-'] if options['per_sample'] else []),str(source)]
            env={'REF_PATH':'/dev/null','REF_CACHE':'/dev/null','HTS_PATH':'','BCFTOOLS_PLUGINS':''}
            code=await manager.command(run,'bcftools',argv,directory,stdout=directory/reports['stats'],stderr=directory/reports['diagnostics'],env=env)
            row['exit_code']=code
            if run['id'] in manager.cancelled:return
            if code:raise ValueError(f'BCFtools stats exited {code}; original diagnostics are in the analysis log')
            diagnostic=report_text(local_file(directory,reports['diagnostics']),1024*1024)
            if re.search(r'(?m)^\[(?:E|W)::',diagnostic):raise ValueError('BCFtools reported a native input/format warning or error; completeness is not qualified')
            parsed=await asyncio.to_thread(original,local_file(directory,row['report']),source,header,options['per_sample'])
            await asyncio.to_thread(manager.checked_inputs,run)
            if await asyncio.to_thread(readable,source,per_sample=options['per_sample'])!=header:raise ValueError('Variant input changed during statistics')
            row.update(state='completed',error=None,variant={**parsed,'reports':reports,'source_snapshot':header['source_snapshot']})
            run['report_input_map'][row['report']]={'id':row['id'],'path':row['path']}
        except (ValueError,OSError,KeyError,TypeError) as exc:
            row.update(state='failed',error=str(exc));errors.append(row['name']+': '+str(exc))
        row['finished_at']=now()
        manager.update(run,sample_count=sum(r['state']=='completed' for r in run['qc']['results']))
    metrics['qc']=run['qc']
    await asyncio.to_thread(save_json,directory/'metrics.json',metrics)
