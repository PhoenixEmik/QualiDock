"""Verified RSeQC reports; alignment.py retains the execution lifecycle."""
import asyncio
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field
from .files import approved_file
from .integrity import snapshot
from .processing import local_file

MODES = {'rseqc-infer', 'rseqc-distribution'}
ANNOTATION_LIMIT = 128 * 1024 * 1024


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    multiqc: bool = False
    annotation: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z][A-Za-z0-9_.-]*$')


class InferOptions(Options):
    sample_size: int = Field(default=200000, ge=1, le=10000000)
    mapq: int = Field(default=30, ge=0, le=255)


def annotation(settings, identity):
    configured = settings.rna_annotations
    if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}', identity) or not isinstance(configured,dict) or identity not in configured:
        raise ValueError('Choose an administrator-approved BED12 gene annotation')
    if not isinstance(configured[identity], (str, Path)):
        raise ValueError('Annotation must be an absolute local BED12 path')
    path = approved_file(Path(configured[identity]).expanduser())
    before = snapshot(path.stat())
    digest, size, transcripts, blocks, contigs = hashlib.sha256(), 0, 0, 0, {}
    with path.open('rb') as stream:
        while raw := stream.readline(16385):
            size += len(raw); digest.update(raw)
            if len(raw) > 16384 or size > ANNOTATION_LIMIT:
                raise ValueError('BED12 exceeds 16 KiB per line / 128 MiB total')
            line = raw.decode('utf-8').rstrip('\r\n')
            if not line or line.startswith('#'):
                continue
            fields = line.split('\t')
            if len(fields) != 12 or any(not f or any(c.isspace() or ord(c) < 32 for c in f) for f in fields):
                raise ValueError('BED12 requires exactly twelve nonempty whitespace-free tab-separated fields')
            chrom, start, end, name, score, strand, thick_start, thick_end, rgb, count, lengths, starts = fields
            if len(chrom) > 1024 or len(name) > 1024 or strand not in {'+','-'} or any(not v.isascii() or not v.isdecimal() for v in (start,end,score,thick_start,thick_end,count)):
                raise ValueError('Invalid BED12 identity, strand or integer fields')
            start,end,score,thick_start,thick_end,count = map(int,(start,end,score,thick_start,thick_end,count))
            if not start <= thick_start <= thick_end <= end or start == end or not 0 <= score <= 1000 or not 1 <= count <= 1000:
                raise ValueError('Invalid BED12 transcript/coding bounds, score or block count')
            colors = rgb.split(',')
            if rgb != '0' and (len(colors) != 3 or any(not c.isascii() or not c.isdecimal() or int(c) > 255 for c in colors)):
                raise ValueError('Invalid BED12 itemRgb')
            sizes, offsets = lengths.removesuffix(',').split(','), starts.removesuffix(',').split(',')
            if len(sizes) != count or len(offsets) != count or any(not v.isascii() or not v.isdecimal() for v in sizes+offsets):
                raise ValueError('BED12 block arrays do not match blockCount')
            previous = 0
            for length, offset in zip(map(int,sizes),map(int,offsets)):
                if length <= 0 or offset < previous or offset+length > end-start:
                    raise ValueError('BED12 exon blocks must be nonempty, ordered, nonoverlapping and inside the transcript')
                previous = offset+length
            if int(offsets[0]) != 0 or previous != end-start:
                raise ValueError('BED12 exon blocks must span the transcript bounds')
            transcripts += 1; blocks += count
            contigs[chrom] = max(contigs.get(chrom,0), end)
            if transcripts > 1000000 or blocks > 2000000 or len(contigs) > 100000:
                raise ValueError('BED12 exceeds transcript/block/contig limits')
    if not transcripts or snapshot(path.stat()) != before:
        raise ValueError('Empty annotation or BED12 changed during validation')
    if len({name.upper() for name in contigs}) != len(contigs):
        raise ValueError('RSeQC distribution uppercases contigs; case-colliding annotation names are ambiguous')
    return {'id':identity,'path':str(path),'snapshot':before,'sha256':digest.hexdigest(),'bytes':size,
            'transcripts':transcripts,'blocks':blocks,'contigs':contigs,
            'identity':'BED12 SHA-256 and matching BAM contig names/coordinate bounds; not independent genome-assembly or reference-sequence verification'}


def annotations(settings):
    if not isinstance(settings.rna_annotations,dict):
        return [{'id':'configuration','available':False,'error':'QUALIDOCK_RNA_ANNOTATIONS must be a JSON object'}]
    result = []
    for identity in list(settings.rna_annotations)[:32]:
        try:
            value = annotation(settings,identity)
            result.append({'id':identity,'available':True,'transcripts':value['transcripts'],'error':None})
        except (ValueError,OSError,TypeError,UnicodeError) as exc:
            result.append({'id':identity,'available':False,'error':str(exc)})
    return result


def text(path):
    with path.open('rb') as stream:
        raw = stream.read(1024*1024+1)
    if len(raw) > 1024*1024:
        raise ValueError('RSeQC report exceeds 1 MiB')
    return raw.decode('utf-8')


def number(value):
    try: result = Decimal(value)
    except InvalidOperation as exc: raise ValueError('Invalid RSeQC numerical value') from exc
    if not result.is_finite() or result < 0: raise ValueError('Invalid RSeQC numerical value')
    return result


def infer(path, diagnostics, sample_size):
    lines = [line for line in text(path).splitlines() if line]
    counts = re.findall(r'^Total ([0-9]+) usable reads were sampled$',text(diagnostics),re.MULTILINE)
    if len(counts) != 1 or int(counts[0]) > sample_size:
        raise ValueError('Missing/inconsistent RSeQC sampled-alignment count')
    result = {'sampled_alignments':counts[0], 'columns':['Original RSeQC category','Reported fraction'], 'rows':[]}
    if lines == ['Unknown data type: Mixture']:
        return {**result,'layout':'Mixture','status':'unavailable'}
    if not lines or lines[0] not in {'This is PairEnd Data','This is SingleEnd Data'} or len(lines) != 4 or not int(counts[0]):
        raise ValueError('Incomplete/unsupported RSeQC infer_experiment report')
    paired = lines[0] == 'This is PairEnd Data'
    labels = ['Fraction of reads failed to determine',
              'Fraction of reads explained by "'+('1++,1--,2+-,2-+' if paired else '++,--')+'"',
              'Fraction of reads explained by "'+('1+-,1-+,2++,2--' if paired else '+-,-+')+'"']
    for line,label in zip(lines[1:],labels):
        prefix = label+': '
        if not line.startswith(prefix):raise ValueError('Unsupported RSeQC strandedness categories')
        value = line[len(prefix):]
        if number(value) > 1:raise ValueError('Invalid RSeQC strandedness fraction')
        result['rows'].append([label,value])
    if abs(sum(number(row[1]) for row in result['rows'])-1) > Decimal('0.00015'):
        raise ValueError('RSeQC rounded fractions do not sum to one')
    return {**result,'layout':'PairEnd' if paired else 'SingleEnd','status':'available'}


def distribution(path):
    lines = [line.split() for line in text(path).splitlines() if line.strip() and not set(line.strip()) == {'='}]
    labels = ['Total Reads','Total Tags','Total Assigned Tags']
    totals = []
    for values,label in zip(lines[:3],labels):
        if ' '.join(values[:-1]) != label or not values[-1].isdecimal():raise ValueError('Invalid RSeQC distribution totals')
        totals.append([label,values[-1]])
    if len(lines) != 14 or lines[3] != ['Group','Total_bases','Tag_count','Tags/Kb'] or int(totals[2][1]) > int(totals[1][1]):
        raise ValueError('Incomplete RSeQC distribution report')
    expected = ['CDS_Exons',"5'UTR_Exons","3'UTR_Exons",'Introns','TSS_up_1kb','TSS_up_5kb','TSS_up_10kb','TES_down_1kb','TES_down_5kb','TES_down_10kb']
    rows = lines[4:]
    for row,label in zip(rows,expected):
        if len(row) != 4 or row[0] != label or not row[1].isdecimal() or not row[2].isdecimal() or int(row[2]) > int(totals[1][1]):
            raise ValueError('Unsupported/inconsistent RSeQC distribution category')
        number(row[3])
    return {'totals':totals,'columns':lines[3],'rows':rows}


async def execute(manager, run, row, contigs, preflight, env):
    directory = manager.directory(run['id'])
    approved = run['qc']['annotation']
    if await asyncio.to_thread(annotation,manager.settings,approved['id']) != approved:
        raise ValueError('Approved annotation changed while queued')
    if len({name.upper() for name in contigs}) != len(contigs) or any(name not in contigs or end > contigs[name] for name,end in approved['contigs'].items()):
        raise ValueError('BED12 contigs/coordinates do not match the BAM dictionary; no alias conversion is performed')
    tool = 'rseqc_infer' if run['mode'] == 'rseqc-infer' else 'rseqc_distribution'
    suffix = 'infer_experiment' if tool == 'rseqc_infer' else 'read_distribution'
    prefix = f'qc/{row["id"]}/{row["id"]}.{suffix}'
    stdout,stderr = directory/(prefix+'.txt'),directory/(prefix+'.log')
    options = run['qc']['options']
    argv = [run['tools'][tool]['executable'],'-i',row['path'],'-r',approved['path']]
    if tool == 'rseqc_infer':argv += ['-s',str(options['sample_size']),'-q',str(options['mapq'])]
    manager.update(run,stage=f'RSeQC {suffix} · {row["name"]}')
    code = await manager.command(run,tool,argv,directory,stdout=stdout,stderr=stderr,env=env)
    row['exit_code'] = code
    if run['id'] in manager.cancelled:return None
    if code:raise ValueError(f'RSeQC {suffix} exited {code}; see analysis log')
    result = await asyncio.to_thread(infer,local_file(directory,prefix+'.txt'),local_file(directory,prefix+'.log'),options['sample_size']) if tool == 'rseqc_infer' else await asyncio.to_thread(distribution,local_file(directory,prefix+'.txt'))
    if await asyncio.to_thread(annotation,manager.settings,approved['id']) != approved:
        raise ValueError('Approved annotation changed during RSeQC')
    return {'operation':suffix,**result,'reports':{'stdout':prefix+'.txt','diagnostics':prefix+'.log',**{'preflight_'+k:v for k,v in preflight.items()}}}
