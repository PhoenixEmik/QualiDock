"""Bounded local variant inputs and original BCFtools stats; no variant engine."""
import gzip
import asyncio
import os
from pathlib import Path
import re

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


def original(path, source, header, per_sample):
    """Validate original report framing/identity before publishing any artifact."""
    text=report_text(path)
    if not text.startswith('# This file was produced by bcftools stats (1.24+htslib-1.24) ') or not text.endswith('\n'):
        raise ValueError('Unsupported or truncated BCFtools stats report')
    rows=[line.split('\t') for line in text.splitlines() if line and not line.startswith('#')]
    identities=[r for r in rows if r[0]=='ID']
    if identities!=[['ID','0',str(source)]]:raise ValueError('Ambiguous or incorrect BCFtools report source identity')
    summary=[r[2:] for r in rows if r[0]=='SN' and len(r)==4 and r[1]=='0']
    if [r[0] for r in summary]!=SUMMARY_KEYS or any(not r[1].isascii() or not r[1].isdecimal() for r in summary):
        raise ValueError('Missing, duplicate or invalid BCFtools summary values')
    values=dict(summary)
    if int(values[SUMMARY_KEYS[0]])!=len(header['samples']) or any(int(v)>int(values['number of records:']) for k,v in summary[2:]):
        raise ValueError('BCFtools summary disagrees with the input header or record population')
    required=['ID','SN','TSTV','SiS','AF','QUAL','IDD','ST','DP',*(['PSC','PSI','HWE'] if per_sample else [])]
    declared={r[0][2:] for r in (line.split('\t') for line in text.splitlines()) if len(r)>1 and r[0].startswith('# ') and r[1]=='[2]id'}
    if not set(required)<=declared:raise ValueError('Truncated BCFtools section definitions')
    return {'status':'available','summary':{'columns':['Original BCFtools metric','Reported value'],'rows':summary,'total_rows':len(summary)},
            'input_format':header['format'],'compression':header['compression'],'sample_count':len(header['samples']),
            'per_sample_requested':per_sample,'sample_statistics_available':per_sample and 'GT' in header['tags']['FORMAT']}


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
