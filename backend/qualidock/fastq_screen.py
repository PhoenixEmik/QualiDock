"""Restricted FastQ Screen 0.16.x / Bowtie2 adapter, not a reference manager."""
import asyncio
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys

from pydantic import BaseModel, ConfigDict, Field
from .integrity import snapshot
from .metrics import bounded_text
from .processing import local_file

SAFE_PATH = re.compile(r'^/[A-Za-z0-9_./-]+$')
NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,63}$')


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    panel: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z][A-Za-z0-9_.-]*$')
    subset: int = Field(default=100000, ge=1, le=1000000)
    multiqc: bool = False


def safe_path(path):
    if not SAFE_PATH.fullmatch(str(path)):
        raise ValueError('FastQ Screen requires shell-safe output, index and executable paths (letters, digits, /, _, ., - only)')
    return path


def regular(path):
    if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_file() or not os.access(path, os.R_OK):
        raise ValueError('Reference configuration/index must be readable, regular and contain no symlinks')
    return path


def panel(settings, identity):
    if not isinstance(identity, str) or not isinstance(settings.screen_panels, dict) or identity not in settings.screen_panels or not NAME.fullmatch(identity):
        raise ValueError('Choose an administrator-approved FastQ Screen panel')
    configured_path = settings.screen_panels[identity]
    if not isinstance(configured_path, (str, Path)):
        raise ValueError('Panel configuration must be an absolute file path')
    path = regular(Path(configured_path).expanduser().absolute())
    info = path.stat()
    if info.st_size > 65536 or info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o022:
        raise ValueError('Panel configuration must be at most 64 KiB, owned by this user/root, and not group/world writable')
    with path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Panel configuration exceeds 64 KiB')
    aligner = shutil.which(settings.bowtie2)
    if not aligner:
        raise ValueError('Bowtie2 unavailable; configure QUALIDOCK_BOWTIE2 or PATH')
    aligner = safe_path(Path(aligner).resolve(strict=True))
    references = []
    for line in raw.decode('utf-8').splitlines():
        parts = [] if line.lstrip().startswith('#') else line.split()
        if not parts:
            continue
        if parts[0] == 'BOWTIE2' and len(parts) == 2:
            configured = shutil.which(parts[1])
            if not configured or Path(configured).resolve() != aligner:
                raise ValueError('Panel BOWTIE2 must match configured QUALIDOCK_BOWTIE2/PATH executable')
        elif parts[0] == 'THREADS' and len(parts) == 2 and parts[1].isdecimal():
            pass  # The allocated run thread limit always overrides this value.
        elif parts[0] == 'DATABASE' and len(parts) == 3 and NAME.fullmatch(parts[1]):
            if len(references) >= 16:
                raise ValueError('Configure at most 16 reference indexes per panel')
            prefix = safe_path(Path(parts[2]))
            components = None
            for suffix in ('bt2', 'bt2l'):
                files = [Path(f'{prefix}.{piece}.{suffix}') for piece in ('1', '2', '3', '4', 'rev.1', 'rev.2')]
                if all(file.is_file() for file in files):
                    components = [{'path': str(regular(file)), **snapshot(file.stat())} for file in files]
                    break
            if not components:
                raise ValueError(f'Missing complete Bowtie2 index: {parts[1]}')
            if any(row['name'] == parts[1] for row in references):
                raise ValueError('Duplicate reference name in panel')
            references.append({'name': parts[1], 'prefix': str(prefix), 'indexes': components})
        else:
            raise ValueError('Panel supports only DATABASE <safe-name> <absolute-prefix>, BOWTIE2 and THREADS directives')
    if not 1 <= len(references) <= 16:
        raise ValueError('Configure 1–16 reference indexes per panel')
    if snapshot(path.stat()) != snapshot(info):
        raise ValueError('Panel changed during validation')
    return {'id': identity, 'configuration': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
            'aligner': str(aligner), 'references': references,
            'index_identity': 'filesystem snapshots, not content checksums'}


def listing(settings):
    rows = []
    if not isinstance(settings.screen_panels, dict):
        return [{'id': 'configuration', 'available': False, 'references': [], 'error': 'QUALIDOCK_SCREEN_PANELS must be a JSON object'}]
    for identity in list(settings.screen_panels)[:16]:
        try:
            value = panel(settings, identity)
            rows.append({'id': identity, 'available': True, 'references': [r['name'] for r in value['references']], 'error': None})
        except (ValueError, OSError, UnicodeError, TypeError) as exc:
            rows.append({'id': identity, 'available': False, 'references': [], 'error': str(exc)})
    return rows


def parse_report(path, expected, subset, available, version=None):
    if path.stat().st_size > 128 * 1024:
        raise ValueError('FastQ Screen summary exceeds 128 KiB')
    text = bounded_text(path)
    lines = text.splitlines()
    reported_version = re.escape(version) if version is not None else r'0\.16\.\d+'
    if not lines or not re.fullmatch(r'#Fastq_screen version: '+reported_version+r'\t#Aligner: bowtie2\t#Reads in subset: '+str(subset), lines[0]):
        raise ValueError('Unsupported FastQ Screen version/aligner/subset report header')
    columns = ['Genome', '#Reads_processed', '#Unmapped', '%Unmapped', '#One_hit_one_genome', '%One_hit_one_genome',
               '#Multiple_hits_one_genome', '%Multiple_hits_one_genome', '#One_hit_multiple_genomes',
               '%One_hit_multiple_genomes', 'Multiple_hits_multiple_genomes', '%Multiple_hits_multiple_genomes']
    if len(lines) < 3 or lines[1].split('\t') != columns:
        raise ValueError('Unsupported FastQ Screen summary columns')
    rows = []
    for line in lines[2:]:
        if not line or line.startswith('%Hit_no_genomes:'):
            continue
        row = next(csv.reader(io.StringIO(line), delimiter='\t'))
        if len(row) != len(columns) or row[0] not in expected:
            raise ValueError('Unexpected reference or malformed FastQ Screen summary')
        counts = [int(row[index]) for index in (1, 2, 4, 6, 8, 10)]
        percentages = [float(row[index]) for index in (3, 5, 7, 9, 11)]
        if any(n < 0 for n in counts) or sum(counts[1:]) != counts[0] or not 0 < counts[0] <= min(available, subset * 2):
            raise ValueError('Inconsistent FastQ Screen read counts')
        if any(not 0 <= number <= 100 for number in percentages):
            raise ValueError('Invalid FastQ Screen percentage')
        rows.append(row)
    if len(rows) != len(expected) or {row[0] for row in rows} != set(expected) or len({row[1] for row in rows}) != 1:
        raise ValueError('Missing/duplicate references or inconsistent processed-read counts')
    no_hits = [line.removeprefix('%Hit_no_genomes: ').strip() for line in lines if line.startswith('%Hit_no_genomes:')]
    if len(no_hits) != 1 or not 0 <= float(no_hits[0]) <= 100:
        raise ValueError('Missing/invalid no-genome percentage')
    return {'columns': columns, 'rows': rows, 'no_genome_percent': no_hits[0], 'processed_reads': int(rows[0][1])}


async def execute(manager, run, row, source):
    """Upstream uses internal shell strings: never pass raw filenames/config text."""
    directory = manager.directory(run['id'])
    safe_path(directory)
    safe_path(Path(sys.executable))
    recorded = run['qc']['reference_panel']
    current = await asyncio.to_thread(panel, manager.settings, recorded['id'])
    if current != recorded:
        raise ValueError('Reference panel/index identity changed since analysis setup')
    private = manager.stores.subdirectory(run['id'], f'qc/private/{row["id"]}', exist_ok=True)
    alias = private / (row['id'] + ('.fastq.gz' if row['path'].lower().endswith('.gz') else '.fastq'))
    alias.symlink_to(row['path'])  # Authorized original remains unchanged, no full FASTQ copy.
    destination = manager.stores.subdirectory(run['id'], f'qc/{row["id"]}', exist_ok=True)
    status = private / 'aligner-status.jsonl'
    wrapper = private / 'bowtie2-checked'
    # Upstream ignores pipe close status. Preserve actual child exit codes so a
    # broken aligner/index can never become a successful "unmapped" observation.
    wrapper.write_text(f'#!{sys.executable}\nimport json, subprocess, sys\n'
                       f'command = [{recorded["aligner"]!r}, *sys.argv[1:]]\n'
                       'code = subprocess.run(command).returncode\n'
                       f'with open({str(status)!r}, "a") as stream: stream.write(json.dumps({{"argv": command, "exit_code": code}})+"\\n")\n'
                       'sys.exit(code if 0 <= code <= 255 else 1)\n')
    wrapper.chmod(0o700)
    conf = private / 'panel.conf'
    conf.write_text(f'BOWTIE2\t{wrapper}\n'+''.join(f'DATABASE\t{r["name"]}\t{r["prefix"]}\n' for r in recorded['references']))
    value = run['qc']['options']
    argv = [run['tools']['fastq_screen']['executable'], '--conf', str(conf), '--aligner', 'bowtie2',
            '--subset', str(value['subset']), '--threads', str(run['threads']), '--outdir', str(destination), str(alias)]
    code = await manager.command(run, 'fastq_screen', argv, directory)
    if run['id'] in manager.cancelled:
        return None
    row['exit_code'] = code
    if code:
        raise ValueError(f'FastQ Screen exited with code {code}; see analysis log')
    statuses = [json.loads(line) for line in bounded_text(status).splitlines()]
    if len(statuses) != len(recorded['references']) or any(entry['exit_code'] != 0 for entry in statuses):
        raise ValueError('A Bowtie2 reference alignment failed; no mapping summary is published')
    if await asyncio.to_thread(panel, manager.settings, recorded['id']) != recorded:
        raise ValueError('Reference panel/index changed during screening')
    row['aligner_executions'] = statuses
    report = destination / (row['id']+'_screen.txt')
    summary = await asyncio.to_thread(parse_report, local_file(directory, str(report.relative_to(directory))),
                                      [r['name'] for r in recorded['references']], value['subset'], source['records_scanned'], run['tools']['fastq_screen']['version'])
    local_file(directory, str((destination/(row['id']+'_screen.html')).relative_to(directory)))
    row['report'] = str(report.relative_to(directory))
    return summary
