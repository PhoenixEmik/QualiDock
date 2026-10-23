"""Read-only SAMtools/HTSlib 1.24 adapter; no FASTQ parsing or pairing."""
import asyncio
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import os
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field
from .files import ALIGNMENT, approved_file
from .integrity import snapshot
from .metrics import bounded_text
from .processing import local_file
from .store import now, save_json
from . import multiqc, coverage, rseqc, picard, picard_rna

MODES = {'samtools', 'mosdepth', 'picard', 'picard-rna', *rseqc.MODES}


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    reference: str | None = Field(default=None, min_length=1, max_length=64, pattern=r'^[A-Za-z][A-Za-z0-9_.-]*$')
    multiqc: bool = False


def readable(path):
    if not ALIGNMENT.search(path.name) or '##idx##' in str(path) or not path.is_file() or not path.stat().st_mode & 0o444 or not os.access(path, os.R_OK):
        raise ValueError('Choose a readable local .bam or .cram alignment')
    with path.open('rb') as stream:
        magic = stream.read(4)
    if path.suffix.lower() == '.cram':
        if magic != b'CRAM':
            raise ValueError('CRAM extension does not match its file format')
    else:
        try:
            with gzip.open(path, 'rb') as stream:
                if stream.read(4) != b'BAM\x01':
                    raise ValueError('BAM extension does not match its file format')
        except (OSError, EOFError) as exc:
            raise ValueError('Invalid BAM compressed header') from exc


def reference(settings, identity):
    if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}', identity) or not isinstance(settings.alignment_references, dict) or identity not in settings.alignment_references:
        raise ValueError('CRAM requires an administrator-approved local reference')
    configured = settings.alignment_references[identity]
    if not isinstance(configured, (str, Path)):
        raise ValueError('Approved reference must be an absolute local FASTA path')
    path = Path(configured).expanduser()
    if not path.is_absolute():
        raise ValueError('Approved reference must be an absolute local FASTA path')
    files = [path, Path(str(path)+'.fai')]
    for file in files:
        approved_file(file)
    with path.open('rb') as stream:
        if stream.read(1) != b'>':
            raise ValueError('Only uncompressed local FASTA references are supported')
    fai = files[1]
    if fai.stat().st_size > 16*1024*1024:
        raise ValueError('Reference .fai exceeds 16 MiB')
    with fai.open('rb') as stream:
        raw = stream.read(16*1024*1024+1)
    if len(raw) > 16*1024*1024:
        raise ValueError('Reference .fai exceeds 16 MiB')
    contigs = {}
    fasta_size = path.stat().st_size
    for line in raw.decode('utf-8').splitlines():
        fields = line.split('\t')
        if len(fields) != 5 or fields[0] in contigs or not fields[0] or len(fields[0]) > 1024 or any(not x.isdecimal() for x in fields[1:]):
            raise ValueError('Invalid reference .fai')
        length, offset, bases, width = map(int, fields[1:])
        if not length or not bases or width < bases or offset >= fasta_size:
            raise ValueError('Invalid reference .fai coordinates')
        contigs[fields[0]] = length
    if not contigs or len(contigs) > 100000:
        raise ValueError('Reference must have 1–100000 indexed sequences')
    return {'id': identity, 'path': str(path), 'files': [{'path': str(f), **snapshot(f.stat())} for f in files],
            'fai_sha256': hashlib.sha256(raw).hexdigest(), 'contigs': contigs,
            'identity': 'FASTA filesystem snapshot and FAI SHA-256; CRAM slice MD5 checks remain enabled, not a full reference content checksum'}


def references(settings):
    if not isinstance(settings.alignment_references, dict):
        return [{'id': 'configuration', 'available': False, 'error': 'QUALIDOCK_ALIGNMENT_REFERENCES must be a JSON object'}]
    rows = []
    for identity in list(settings.alignment_references)[:32]:
        try:
            reference(settings, identity)
            rows.append({'id': identity, 'available': True, 'error': None})
        except (ValueError, OSError, TypeError, UnicodeError) as exc:
            rows.append({'id': identity, 'available': False, 'error': str(exc)})
    return rows


def header(path, approved=None):
    if path.stat().st_size > 16*1024*1024:
        raise ValueError('Alignment header exceeds 16 MiB')
    contigs = {}
    for line in bounded_text(path).splitlines():
        if not line.startswith('@'):
            raise ValueError('Unexpected alignment records in header-only output')
        if line.startswith('@SQ\t'):
            tags = dict(field.split(':', 1) for field in line.split('\t')[1:] if ':' in field)
            name, length = tags.get('SN'), tags.get('LN', '')
            if not name or name in contigs or not length.isdecimal() or int(length) <= 0 or len(contigs) >= 100000:
                raise ValueError('Invalid alignment sequence dictionary')
            contigs[name] = int(length)
    if not contigs:
        raise ValueError('Alignment has no reference sequence dictionary')
    if approved and any(approved['contigs'].get(name) != length for name, length in contigs.items()):
        raise ValueError('Approved reference is missing alignment contigs or has mismatched lengths; remote/UR fallback is forbidden')
    return contigs


def parse_flagstat(path):
    if path.stat().st_size > 65536:
        raise ValueError('flagstat exceeds 64 KiB')
    rows = []
    for line in bounded_text(path).splitlines():
        match = re.fullmatch(r'(\d+) \+ (\d+) (.+)', line)
        if not match:
            raise ValueError('Unsupported SAMtools flagstat output')
        rows.append([match[3], match[1], match[2]])
    names = []
    for label, _, _ in rows:
        if any(label.startswith(name+' (') for name in ('mapped', 'primary mapped', 'properly paired', 'singletons')):
            match = re.fullmatch(r'(.+) \((N/A|[0-9]+(?:\.[0-9]+)?%) : (N/A|[0-9]+(?:\.[0-9]+)?%)\)', label)
            if not match or any(value != 'N/A' and Decimal(value[:-1]) > 100 for value in match.groups()[1:]):
                raise ValueError('Invalid SAMtools flagstat percentages')
            names.append(match[1])
        else:
            names.append(label)
    expected = ['in total (QC-passed reads + QC-failed reads)', 'primary', 'secondary', 'supplementary',
                'duplicates', 'primary duplicates', 'mapped', 'primary mapped', 'paired in sequencing',
                'read1', 'read2', 'properly paired', 'with itself and mate mapped', 'singletons',
                'with mate mapped to a different chr', 'with mate mapped to a different chr (mapQ>=5)']
    if names != expected:
        raise ValueError('Incomplete or unsupported SAMtools flagstat output')
    if any(int(row[i]) > int(rows[0][i]) for row in rows for i in (1, 2)):
        raise ValueError('Inconsistent SAMtools flagstat counts')
    return {'columns': ['Reported category', 'QC-passed segments', 'QC-failed segments'], 'rows': rows}


def parse_stats(path, flagstat=None):
    # Stream only bounded summary rows; retain the untouched full report on disk.
    rows = []
    with path.open('rt', encoding='utf-8') as stream:
        while line := stream.readline(1024*1024+1):
            if len(line) > 1024*1024:
                raise ValueError('SAMtools stats line exceeds 1 MiB')
            if not line.startswith('SN\t'):
                continue
            fields = line.rstrip('\n').split('\t')
            if len(fields) not in (3, 4) or len(rows) >= 200:
                raise ValueError('Malformed SAMtools summary')
            try:
                value = Decimal(fields[2])
                if not value.is_finite() or value < 0:
                    raise ValueError('Invalid SAMtools summary value')
            except InvalidOperation as exc:
                raise ValueError('Invalid SAMtools summary number') from exc
            rows.append([fields[1], fields[2], fields[3] if len(fields) == 4 else ''])
    values = {r[0]: r[1] for r in rows}
    if len(values) != len(rows) or not {'raw total sequences:', 'reads mapped:', 'reads unmapped:', 'total length:'} <= values.keys():
        raise ValueError('Missing or duplicate SAMtools summary values')
    if flagstat is not None:
        primary = next(row for row in flagstat['rows'] if row[0] == 'primary')
        if Decimal(values['raw total sequences:']) != int(primary[1]) + int(primary[2]):
            raise ValueError('SAMtools stats and flagstat primary counts disagree')
    return {'columns': ['Original SAMtools metric', 'Reported value', 'Original note'], 'rows': rows}


async def execute(manager, run, metrics, errors):
    directory = manager.directory(run['id'])
    await asyncio.to_thread(manager.checked_inputs, run)
    approved = run['qc'].get('reference')
    if approved and await asyncio.to_thread(reference, manager.settings, approved['id']) != approved:
        raise ValueError('Approved reference changed while queued')
    # Disables configured remote reference search/cache. The complete local FAI
    # dictionary is checked before any record decode; no missing-contig UR fallback.
    env = {'REF_PATH': '/dev/null', 'REF_CACHE': '/dev/null', 'HTS_PATH': ''}
    is_coverage = run['mode'] == 'mosdepth'
    is_rna = run['mode'] in rseqc.MODES
    is_picard = run['mode'] in {'picard','picard-rna'}
    for row in run['qc']['results']:
        if run['id'] in manager.cancelled:
            break
        try:
            paths = await asyncio.to_thread(manager.checked_inputs, run)
            source = next(p for p in paths if str(p) == row['path'])
            before = snapshot(source.stat())
            index = await asyncio.to_thread(coverage.index, manager, source) if is_coverage else None
            destination = manager.stores.subdirectory(run['id'], f'qc/{row["id"]}', exist_ok=True)
            row['state'] = 'running'
            manager.update(run, stage=f'SAMtools · {row["name"]}')
            executable = run['tools']['samtools']['executable']
            cram = source.suffix.lower() == '.cram'
            if cram and not approved:
                raise ValueError('CRAM requires an approved local reference')
            decoding = ['--input-fmt-option', 'reference='+approved['path']] if cram else []
            outputs = {}
            for label, args, suffix in [
                ('header', ['head', '-n', '0'], '.header.txt'),
                ('quickcheck', ['quickcheck', '-v'], '.quickcheck.txt'),
                ('flagstat', ['flagstat', '-@', str(run['threads']-1), *decoding], '.flagstat.txt'),
                ('stats', ['stats', '-@', str(run['threads']-1), *decoding], '.stats.txt'),
            ]:
                if run['mode'] != 'samtools' and label == 'flagstat':
                    continue
                output = destination / (row['id']+suffix)
                argv = [executable, *args, str(source)]
                code = await manager.command(run, 'samtools', argv, directory, stdout=output, env=env)
                row['exit_code'] = code
                if run['id'] in manager.cancelled:
                    return
                if code:
                    raise ValueError(f'SAMtools {label} exited with code {code}; see analysis log')
                outputs[label] = str(output.relative_to(directory))
                if label == 'header':
                    contigs = await asyncio.to_thread(header, local_file(directory, outputs[label]), approved if cram else None)
            flagstat = await asyncio.to_thread(parse_flagstat, local_file(directory, outputs['flagstat'])) if run['mode']=='samtools' else None
            stats = await asyncio.to_thread(parse_stats, local_file(directory, outputs['stats']), flagstat)
            result = None
            if is_coverage:
                result = await coverage.execute(manager, run, row, contigs, stats, outputs, index, env)
                if run['id'] in manager.cancelled:
                    return
            elif is_rna:
                result = await rseqc.execute(manager, run, row, contigs, outputs, env, stats)
                if run['id'] in manager.cancelled:
                    return
            elif is_picard:
                result = await picard_rna.execute(manager,run,row,contigs,stats,outputs,env) if run['mode']=='picard-rna' else await picard.execute(manager,run,row,stats,outputs,env)
                if run['id'] in manager.cancelled:
                    return
            if snapshot(source.stat()) != before:
                raise ValueError('Alignment changed during QC')
            await asyncio.to_thread(manager.checked_inputs, run)
            if approved and await asyncio.to_thread(reference, manager.settings, approved['id']) != approved:
                raise ValueError('Approved reference changed during QC')
            row.update(state='completed', error=None)
            if is_coverage:
                row['mosdepth'] = {**result, 'source_snapshot': before}
            elif is_rna:
                row['rseqc'] = {**result, 'source_snapshot': before}
            elif is_picard:
                row['picard'] = {**result, 'source_snapshot': before}
                for warning in result.get('warnings',[]):
                    errors.append(row['name']+': '+warning)
                    run['warnings'].append(row['name']+': '+warning)
            else:
                row['alignment'] = {'format': source.suffix[1:].upper(), 'quickcheck': 'passed (header/EOF only)',
                    'source_snapshot': before, 'contigs': contigs, 'reports': outputs, 'flagstat': flagstat, 'stats': stats}
                for name in ('flagstat', 'stats'):
                    run['report_input_map'][outputs[name]] = {'id': row['id'], 'path': row['path']}
        except (ValueError, OSError, KeyError, TypeError, UnicodeError) as exc:
            if run['id'] in manager.cancelled:return
            row.update(state='failed', error=str(exc))
            errors.append(f'{row["name"]}: {exc}')
        row['finished_at'] = now()
        manager.update(run, sample_count=sum(r['state'] == 'completed' for r in run['qc']['results']))
    metrics['qc'] = run['qc']
    if run['id'] not in manager.cancelled and run['qc']['options'].get('multiqc'):
        config = None
        if is_rna or is_picard:
            key = 'rseqc' if is_rna else 'picard'
            reports = [directory/row['report'] for row in run['qc']['results']
                       if row['state']=='completed' and row[key].get('status','available')=='available' and row[key].get('multiqc_supported',True)]
            for row in run['qc']['results']:
                if row['state']=='completed' and (row[key].get('status','available')!='available' or not row[key].get('multiqc_supported',True)):
                    run['warnings'].append(f"MultiQC omitted {row['name']}: no compatible MultiQC observations were reported; original diagnostics remain available.")
            for path in reports:
                row = next(r for r in run['qc']['results'] if r['report']==str(path.relative_to(directory)))
                run['report_input_map'][row['report']] = {'id':row['id'],'path':row['path']}
            if is_picard:
                # Official options avoid INPUT=basename collisions without editing reports.
                config = {'picard_config':{'s_name_filenames':True}} if run['tools']['multiqc']['version']=='1.25.1' else {'use_filename_as_sample_name':['picard']}
        else:
            # Genuine 1.25.1 flagstat module crashes on N/A. Preserve originals.
            legacy = run['tools']['multiqc']['version'] == '1.25.1'
            sections = {'stats'} if legacy else {'flagstat', 'stats'}
            if legacy:
                run['warnings'].append('MultiQC 1.25.1 aggregates SAMtools stats only: its flagstat module fails on N/A percentages. Original flagstat and native counts remain available.')
            reports = [directory/path for row in run['qc']['results'] if row['state']=='completed' for name,path in row['alignment']['reports'].items() if name in sections]
        if reports:
            if run['mode']=='picard-rna':run['qc']['multiqc_status']='invalid'
            try:
                problem = await multiqc.execute(manager, run, reports, config=config)
            except (ValueError,OSError) as exc:
                problem = f'MultiQC aggregation failed: {exc}; original reports remain available'
            if problem:
                errors.append(problem)
            elif run['id'] not in manager.cancelled:
                metrics['multiqc'] = await multiqc.summary(directory)
                try:
                    samples = await multiqc.alignment_sample_names(directory,run['mode']) if is_rna or is_picard else None
                    names = await multiqc.report_names(directory,reports,metrics['multiqc'],sample_names=samples)
                    if run['mode']=='picard-rna':
                        await multiqc.verify_picard_rna(directory, run, names)
                        run['qc']['multiqc_status']='available'
                    for report, name in names.items():
                        if name is None:
                            errors.append(f'No unique MultiQC {run["mode"]} source mapping for {report}; original reports remain available')
                        else:
                            run['report_input_map'][report]['multiqc_name'] = name
                except (ValueError,OSError,TypeError,UnicodeError) as exc:
                    if run['mode']=='picard-rna':metrics.pop('multiqc',None)
                    errors.append(f'Cannot verify MultiQC source mapping: {exc}; original reports remain available')
    await asyncio.to_thread(save_json, directory/'metrics.json', metrics)
