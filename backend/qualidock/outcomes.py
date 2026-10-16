"""Stable file identities and collision-free FastQC artifact plans."""
from collections import Counter
import hashlib
from pathlib import Path
from .files import FASTQ


def plan(paths):
    stems = Counter(FASTQ.sub('', path.name) for path in paths)
    records = []
    for path in paths:
        stem = FASTQ.sub('', path.name)
        identity = 'i_' + hashlib.sha256(str(path).encode()).hexdigest()[:24]
        directory = 'fastqc/' + identity if stems[stem] > 1 else 'fastqc'
        records.append({'id': identity, 'path': str(path), 'name': path.name,
                        'output_directory': directory, 'report': f'{directory}/{stem}_fastqc.zip',
                        'html': f'{directory}/{stem}_fastqc.html', 'state': 'queued',
                        'error': None, 'exit_code': None, 'finished_at': None})
    return records


def batches(records, maximum=8):
    groups = {}
    for record in records:
        groups.setdefault(record['output_directory'], []).append(record)
    return [group[index:index + maximum] for group in groups.values() for index in range(0, len(group), maximum)]


def stop(records, state, message):
    for record in records:
        if record['state'] in {'queued', 'unknown', 'running'}:
            record.update(state=state, error=message)


def counts(records):
    return {state: sum(record['state'] == state for record in records)
            for state in ('queued', 'running', 'unknown', 'completed', 'failed', 'cancelled', 'interrupted')}
