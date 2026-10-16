"""Exact registered FASTQ references, not additional filesystem access roots."""
from copy import deepcopy
import hashlib
from pathlib import Path

from .files import PathViolation


def registered(manager, references):
    records = {}
    identities = set()
    for reference in references or []:
        identity = (reference['run_id'], reference['dataset_id'])
        if identity in identities:
            raise ValueError('Duplicate derived dataset reference')
        identities.add(identity)
        source = manager.runs[identity[0]]
        if source['state'] not in {'completed', 'partial'}:
            raise PathViolation('Only published derived FASTQs can be reused')
        dataset = next((row for row in source.get('derived_datasets', []) if row['id'] == identity[1]), None)
        if dataset is None:
            raise PathViolation('Dataset is not a registered derived FASTQ')
        try:
            path = manager.artifact(identity[0], dataset['path'])
        except OSError as exc:
            raise PathViolation('Derived FASTQ is missing or unreadable') from exc
        if str(path) in records:
            raise ValueError('A FASTQ may be selected only once')
        unit = next((unit for unit in source.get('processing', {}).get('units', []) if unit['id'] == dataset['unit_id']), {})
        records[str(path)] = {**deepcopy(dataset), 'run_id': identity[0], 'dataset_id': identity[1], 'absolute_path': str(path),
                              'lane': unit.get('lane'), 'chunk': unit.get('chunk')}
    return records


def resolve(manager, raw, records):
    # Literal equality: an alias, symlink, '..' or sibling never inherits access.
    return Path(raw) if raw in records else manager.files.resolve(str(raw))


def pairing(records):
    rows = []
    for path, record in records.items():
        siblings = [(p, r) for p, r in records.items() if r['run_id'] == record['run_id'] and r['unit_id'] == record['unit_id']]
        mates = [p for p, r in siblings if r.get('paired') and r.get('read') in {'R1', 'R2'} and r['read'] != record.get('read')]
        paired = bool(record.get('paired') and record.get('read') in {'R1', 'R2'} and len(siblings) == 2 and len(mates) == 1)
        rows.append({'path': path, 'name': Path(path).name, 'read': record.get('read'), 'paired': paired,
                     'mate': mates[0] if paired else None, 'pair_key': f"{record['run_id']}:{record['unit_id']}" if paired else None,
                     'source': 'confirmed', 'lane': record.get('lane'), 'chunk': record.get('chunk'),
                     'assignment': 'paired' if paired else 'unpaired'})
    return rows


def groups(manager, records):
    result = {}
    for path, record in records.items():
        source = manager.runs[record['run_id']]
        original = next((g for g in source.get('sample_groups', []) if record['source'] in g['files']), None)
        key = record['run_id'] + ':' + (original['id'] if original else record['unit_id'])
        result.setdefault(key, {'id': 'derived-' + hashlib.sha256(key.encode()).hexdigest()[:20],
                                'display_name': original['display_name'] if original else Path(record['source']).name[:120],
                                'source': 'confirmed', 'files': []})['files'].append(path)
    return list(result.values())


def draft(manager, run_id, dataset_ids=None):
    source = manager.runs[run_id]
    ids = dataset_ids if dataset_ids is not None else [d['id'] for d in source.get('derived_datasets', [])]
    if not ids or len(ids) > 500:
        raise ValueError('Select 1–500 published FASTQ datasets')
    references = [{'run_id': run_id, 'dataset_id': identity} for identity in ids]
    records = registered(manager, references)
    configuration = manager.sample_configuration(list(records), input_datasets=references)
    relationships = {row['path']: row for row in configuration['input_pairing']}
    entries = [{**manager.files._entry(Path(path).parent, Path(path).name), **relationships[path]} for path in records]
    return {**configuration, 'name': '', 'mode': 'both', 'paths': list(records), 'entries': entries,
            'threads': min(source.get('threads', 1), manager.settings.max_threads),
            'output_root': str(manager.directory(run_id).parent), 'rerun_of': None, 'input_datasets': [{**ref, 'path': path} for ref, path in zip(references, records)]}
