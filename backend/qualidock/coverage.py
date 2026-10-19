"""Explicit mosdepth 0.3.14 reports; alignment.py owns the shared QC lifecycle."""
import asyncio
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from .files import approved_file
from .integrity import snapshot
from .processing import local_file

THRESHOLDS = (1, 10, 20, 30)


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    reference: str | None = Field(default=None, min_length=1, max_length=64, pattern=r'^[A-Za-z][A-Za-z0-9_.-]*$')
    panel: str | None = Field(default=None, min_length=1, max_length=64, pattern=r'^[A-Za-z][A-Za-z0-9_.-]*$')
    mapq: int = Field(default=0, ge=0, le=255)
    exclude_supplementary: bool = False


def panel(settings, identity):
    if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}',identity) or not isinstance(settings.coverage_panels, dict) or identity not in settings.coverage_panels:
        raise ValueError('Choose an administrator-approved BED panel')
    configured = settings.coverage_panels[identity]
    if not isinstance(configured, (str, Path)):
        raise ValueError('Approved BED must be an absolute local path')
    path = approved_file(Path(configured).expanduser())
    before = snapshot(path.stat())
    with path.open('rb') as stream:
        raw = stream.read(2*1024*1024+1)
    if len(raw) > 2*1024*1024:
        raise ValueError('BED panel exceeds 2 MiB')
    rows, ends, width = [], {}, None
    for line in raw.decode('utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        fields = line.split('\t')
        if len(fields) not in (3,4) or len(line) > 4096 or len(rows) >= 10000 or (width and len(fields) != width):
            raise ValueError('BED supports 1–10000 consistently three/four-column intervals')
        width = len(fields)
        chrom, start, end = fields[:3]
        name = fields[3] if width == 4 else ''
        if not chrom or len(chrom) > 1024 or not start.isdecimal() or not end.isdecimal() or not 0 <= int(start) < int(end) or int(start) < ends.get(chrom, 0) or len(name) > 200 or (width == 4 and not name):
            raise ValueError('BED intervals must be nonempty, ordered and nonoverlapping within each reference; names at most 200 characters')
        ends[chrom] = int(end)
        rows.append([chrom, start, end, name])
    if not rows or snapshot(path.stat()) != before:
        raise ValueError('Empty BED or panel changed during validation')
    return {'id': identity, 'path': str(path), 'snapshot': before, 'sha256': hashlib.sha256(raw).hexdigest(),
            'named': width == 4, 'rows': rows}


def panels(settings):
    if not isinstance(settings.coverage_panels, dict):
        return [{'id':'configuration', 'available':False, 'error':'QUALIDOCK_COVERAGE_PANELS must be a JSON object'}]
    result = []
    for identity in list(settings.coverage_panels)[:32]:
        try:
            value = panel(settings, identity)
            result.append({'id': identity, 'available': True, 'intervals':len(value['rows']), 'error': None})
        except (ValueError,OSError,TypeError,UnicodeError) as exc:
            result.append({'id':identity, 'available':False, 'error':str(exc)})
    return result


def index(manager, source):
    # Force this exact authorized index with upstream's ##idx## syntax; never
    # let HTSlib discover an unvalidated alternate or fetch a remote index.
    suffixes = ('.csi', '.bai') if source.suffix.lower() == '.bam' else ('.crai',)
    for suffix in suffixes:
        for candidate in (Path(str(source)+suffix), source.with_suffix(suffix)):
            if not (candidate.exists() or candidate.is_symlink()):
                continue
            path = manager.files.resolve(str(candidate))
            if not path.is_file() or '##idx##' in str(path) or not path.stat().st_mode & 0o444:
                raise ValueError('Alignment index must be a readable local file')
            with path.open('rb') as stream:
                magic = stream.read(4)
            if suffix == '.bai' and magic != b'BAI\x01':
                raise ValueError('Invalid BAI index header')
            if suffix == '.csi':
                if magic[:2] == b'\x1f\x8b':
                    with gzip.open(path, 'rb') as stream:
                        magic = stream.read(4)
                if magic != b'CSI\x01':
                    raise ValueError('Invalid CSI index header')
            if suffix == '.crai':
                with (gzip.open(path, 'rb') if magic[:2] == b'\x1f\x8b' else path.open('rb')) as stream:
                    fields = stream.readline(4097).strip().split(b'\t')
                if len(fields) != 6 or any(not f.lstrip(b'-').isdigit() for f in fields):
                    raise ValueError('Invalid CRAI index header')
            return {'path':str(path), **snapshot(path.stat()), 'identity':'filesystem snapshot and upstream index decoding, not a cryptographic binding to the alignment'}
    raise ValueError('Alignment coverage requires an existing matching BAI/CSI or CRAI index; QualiDock never creates alignment indexes')


def lines(path, compressed=False):
    opener = gzip.open if compressed else open
    total = 0
    with opener(path, 'rb') as stream:
        while line := stream.readline(4097):
            total += len(line)
            if len(line) > 4096 or total > 64*1024*1024:
                raise ValueError('Coverage report exceeds the 4 KiB line / 64 MiB decoded parsing limit')
            yield line.decode('utf-8').rstrip('\r\n').split('\t')


def number(value):
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Invalid mosdepth number') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('Invalid mosdepth number')
    return result


def table(columns, rows, count):
    return {'columns':columns, 'rows':rows, 'total_rows':count}


def distribution(path, expected):
    cdf, count, states = [], 0, {}
    for values in lines(path):
        if len(values) != 3 or values[0] not in expected or not values[1].isdecimal() or not 0 <= number(values[2]) <= 1:
            raise ValueError('Invalid mosdepth cumulative distribution')
        name,depth,fraction = values
        depth,value = int(depth),number(fraction)
        previous = states.get(name)
        if previous and (depth >= previous[0] or value < previous[1]):
            raise ValueError('Nonmonotonic mosdepth cumulative distribution')
        states[name] = (depth,value)
        if name == 'total':
            count += 1
            if count <= 20000:cdf.append(values[1:])
    if set(states) != expected or any(v != (0,Decimal(1)) for v in states.values()):
        raise ValueError('Incomplete mosdepth cumulative distribution')
    return table(["Depth","Reported fraction ≥ depth"], cdf if count <= 20000 else [], count)


def parse(directory, prefix, contigs, bed):
    files = {'summary':prefix+'.mosdepth.summary.txt', 'global_distribution':prefix+'.mosdepth.global.dist.txt'}
    summary, reported, seen, totals, regional = [], {}, set(), {}, {}
    header = ['chrom','length','bases','mean','min','max']
    for i, values in enumerate(lines(local_file(directory,files['summary']))):
        if i == 0:
            if values != header:raise ValueError('Unsupported mosdepth summary columns')
            continue
        if len(values) != 6 or values[0] in seen or len(seen) >= 200002:
            raise ValueError('Malformed/ambiguous mosdepth summary')
        name,length,bases,mean,low,high = values
        if not all(v.isdecimal() for v in (length,bases,low,high)):
            raise ValueError('Invalid mosdepth summary counts')
        length,bases = int(length),int(bases)
        if not length and (bases or number(mean) != 0 or number(low) != 0 or number(high) != 0):
            raise ValueError('Invalid empty mosdepth aggregate')
        if length and not number(low) <= number(mean) <= number(high):
            raise ValueError('Inconsistent mosdepth summary depths')
        if name in contigs:
            if length != contigs[name]:raise ValueError('mosdepth reference length differs from alignment header')
            reported[name] = (length,bases)
        elif name == 'total' or (bed and name == 'total_region'):
            totals[name] = values
        elif bed and name.endswith('_region') and name[:-7] in contigs:
            regional[name[:-7]] = (length,bases)
        else:
            raise ValueError('Unrecognized mosdepth reference summary')
        seen.add(name)
        if len(summary) < 200:summary.append(values)
    total = totals.get('total')
    if not reported or not total or int(total[1]) != sum(v[0] for v in reported.values()) or int(total[2]) != sum(v[1] for v in reported.values()):
        raise ValueError('Missing/empty/inconsistent mosdepth global summary')
    global_distribution = distribution(local_file(directory,files['global_distribution']), {*reported,'total'})
    result = {'summary':table(header,summary,len(seen)), 'total':total,
              'distribution':global_distribution,
              'reported_reference_bases':int(total[1]), 'header_reference_bases':sum(contigs.values()),
              'omitted_references':[name for name in contigs if name not in reported][:50],
              'omitted_reference_count':len(contigs)-len(reported), 'reports':files}
    if not bed:return result
    files['regional_distribution'] = prefix+'.mosdepth.region.dist.txt'
    region_total = totals.get('total_region')
    if not region_total or int(region_total[1]) != sum(v[0] for v in regional.values()) or int(region_total[2]) != sum(v[1] for v in regional.values()):
        raise ValueError('Inconsistent mosdepth regional summary')
    distribution(local_file(directory,files['regional_distribution']), ({name for name,v in regional.items() if v[0]} | {'total'}) if int(region_total[1]) else set())
    expected = {(r[0],int(r[1]),int(r[2]),r[3]):r for r in bed['rows']}
    for kind in ('regions','thresholds'):
        path = prefix+'.'+kind+'.bed.gz'
        files[kind] = path
        data, actual, columns = [], set(), ['chrom','start','end', *(['region'] if bed['named'] or kind == 'thresholds' else []), *(['mean'] if kind == 'regions' else [str(v)+'X' for v in THRESHOLDS])]
        for i, values in enumerate(lines(local_file(directory,path),True)):
            if kind == 'thresholds' and i == 0:
                if values != ['#chrom','start','end','region',*[str(v)+'X' for v in THRESHOLDS]]:
                    raise ValueError('Unsupported mosdepth thresholds header')
                continue
            if len(values) != len(columns) or not values[1].isdecimal() or not values[2].isdecimal():raise ValueError('Malformed mosdepth regional report')
            name = values[3] if bed['named'] else ''
            key = (values[0],int(values[1]),int(values[2]),name)
            if key not in expected or key in actual:raise ValueError('mosdepth region identity mismatch/duplicate')
            actual.add(key)
            if kind == 'regions':number(values[-1])
            else:
                counts = values[4:]
                if any(not v.isdecimal() or int(v) > key[2]-key[1] for v in counts) or [int(v) for v in counts] != sorted(map(int,counts),reverse=True):
                    raise ValueError('Invalid mosdepth threshold counts or denominator')
            if len(data) < 200:data.append(values)
        if actual != set(expected):raise ValueError('mosdepth omitted requested BED regions')
        result[kind] = table(columns,data,len(actual))
        sidecar = path+'.csi'
        local_file(directory,sidecar)
        files[kind+'_index'] = sidecar
    result['requested_region_bases'] = sum(int(r[2])-int(r[1]) for r in bed['rows'])
    result['reported_region_bases'] = int(totals['total_region'][1]) if 'total_region' in totals else None
    return result


async def execute(manager, run, row, contigs, stats, preflight, selected_index, env):
    directory = manager.directory(run['id'])
    values = {r[0]:r[1] for r in stats['rows']}
    header = local_file(directory,preflight['header']).read_text()
    if not any(line.startswith('@HD\t') and 'SO:coordinate' in line.split('\t') for line in header.splitlines()) or values.get('is sorted:') != '1':
        raise ValueError('mosdepth requires actual coordinate-sorted alignments with SO:coordinate; QualiDock never sorts inputs')
    bed = run['qc'].get('bed_panel')
    if 'total' in contigs or (bed and any(name+'_region' in contigs for name in contigs)):
        raise ValueError('Alignment names collide with reserved mosdepth total/_region summary labels')
    if bed:
        if await asyncio.to_thread(panel,manager.settings,bed['id']) != bed:raise ValueError('Approved BED changed while queued')
        if any(r[0] not in contigs or int(r[2]) > contigs[r[0]] for r in bed['rows']):raise ValueError('BED reference/interval is outside the alignment sequence dictionary')
    prefix = f'qc/{row["id"]}/{row["id"]}'
    options = run['qc']['options']
    flags = 1796 | (2048 if options['exclude_supplementary'] else 0)
    argv = [run['tools']['mosdepth']['executable'],'--no-per-base','--threads',str(run['threads']-1),'--flag',str(flags),'--mapq',str(options['mapq'])]
    if Path(row['path']).suffix.lower() == '.cram':argv += ['--fasta',run['qc']['reference']['path']]
    if bed:argv += ['--by',bed['path'],'--thresholds',','.join(map(str,THRESHOLDS))]
    argv += [str(directory/prefix),row['path']+'##idx##'+selected_index['path']]
    manager.update(run,stage=f'mosdepth · {row["name"]}')
    code = await manager.command(run,'mosdepth',argv,directory,stdout=directory/(prefix+'.mosdepth.log'),env={**env,'MOSDEPTH_PRECISION':'5'})
    row['exit_code'] = code
    if run['id'] in manager.cancelled:return None
    if code:raise ValueError(f'mosdepth exited with code {code}; see analysis log')
    result = await asyncio.to_thread(parse,directory,prefix,contigs,bed)
    if await asyncio.to_thread(index,manager,Path(row['path'])) != selected_index:raise ValueError('Alignment index changed during coverage QC')
    if bed and await asyncio.to_thread(panel,manager.settings,bed['id']) != bed:raise ValueError('Approved BED changed during coverage QC')
    result.update(index=selected_index, exclude_flags=flags, mapq=options['mapq'], precision=5)
    result['reports'].update({'execution_log':prefix+'.mosdepth.log',**{'preflight_'+name:path for name,path in preflight.items()}})
    return result
