"""Run the versioned integrity scanner under the existing LocalExecutor guardian."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from .integrity import VERSION, scan_file, compare_pairs
from .store import save_json


def execute(config, output):
    now = lambda: datetime.now(timezone.utc).isoformat()
    result = {'schema_version': 1, 'validator': 'QualiDock FASTQ integrity', 'version': VERSION,
              'mode': config['mode'], 'quick_read_limit': config['quick_reads'],
              'started_at': now(), 'finished_at': None, 'files': [], 'pairs': [], 'result': 'not_evaluated'}
    for entry in config['files']:
        def progress(value):
            try:
                save_json(output, {**result, 'current_file': value})
            except OSError as exc:
                raise RuntimeError('Cannot persist integrity progress; validation is incomplete') from exc
        progress({'id': entry['id'], 'path': entry['path'], 'state': 'running', 'records_scanned': 0})
        result['files'].append(scan_file(entry, config['mode'], config['quick_reads'], progress))
        result['pairs'] = compare_pairs(config['pairs'], result['files'], {entry['path'] for entry in config['files']})
        save_json(output, result)
    result['pairs'] = compare_pairs(config['pairs'], result['files'], {entry['path'] for entry in config['files']})
    states = [entry['state'] for entry in [*result['files'], *result['pairs']]]
    result.update(result='failed' if 'failed' in states else 'not_evaluated' if 'not_evaluated' in states else 'passed', finished_at=now())
    save_json(output, result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    execute(json.loads(args.config.read_text()), args.output)
