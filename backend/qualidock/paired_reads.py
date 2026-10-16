"""Small synchronized FASTQ selector, executed by the existing LocalExecutor."""
import argparse
from contextlib import ExitStack
import gzip
import io
import json
import os
from pathlib import Path
import stat

from .integrity import record, snapshot
from .store import save_json

VERSION = '1.0'


def execute(config):
    if len(config['inputs']) != 2 or len(config['snapshots']) != 2 or len(config['outputs']) != 2 or len(set(config['outputs'])) != 2:
        raise ValueError('Synchronized selection requires two inputs and two distinct outputs')
    total = retained = 0
    with ExitStack() as stack:
        sources, streams, writers = [], [], []
        for path, expected in zip(map(Path, config['inputs']), config['snapshots']):
            if path.resolve(strict=True) != path:
                raise ValueError('Input contains a symlink')
            raw = stack.enter_context(os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb', buffering=0))
            if not stat.S_ISREG(os.fstat(raw.fileno()).st_mode) or snapshot(os.fstat(raw.fileno())) != expected:
                raise ValueError('Source changed after full validation')
            buffered = stack.enter_context(io.BufferedReader(raw))
            stream = stack.enter_context(gzip.GzipFile(fileobj=buffered, mode='rb')) if path.name.lower().endswith('.gz') or buffered.peek(2)[:2] == b'\x1f\x8b' else buffered
            sources.append(raw); streams.append(stream)
        for path in map(Path, config['outputs']):
            if path.parent.resolve(strict=True) != path.parent or str(path) in config['inputs']:
                raise ValueError('Output contains a symlink or targets a source')
            raw = stack.enter_context(os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb'))
            writer = stack.enter_context(gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0)) if config['gzip'] else raw
            writers.append((writer, raw))
        while True:
            parts = [[], []]
            reads = [record(stream, raw=parts[index]) for index, stream in enumerate(streams)]
            if all(read is None for read in reads): break
            if any(read is None for read in reads) or reads[0][0] != reads[1][0]:
                raise ValueError('Mate identifiers, counts or ordering differ')
            total += 1
            keep = all(read[1] >= config['min_length'] and (config['max_length'] is None or read[1] <= config['max_length']) for read in reads)
            if keep:
                for (writer, _), content in zip(writers, parts): writer.writelines(content)
                retained += 1
        for path, raw, expected in zip(map(Path, config['inputs']), sources, config['snapshots']):
            if snapshot(os.fstat(raw.fileno())) != expected or snapshot(path.stat()) != expected or path.resolve() != path:
                raise ValueError('Source changed during synchronized selection')
        read_bytes = [raw.tell() for raw in sources]
        written_bytes = []
        for writer, raw in writers:
            if writer is not raw: writer.close()
            raw.flush(); written_bytes.append(raw.tell())
    result = {'processor': 'QualiDock synchronized FASTQ selector', 'version': VERSION,
              'operation': 'length', 'record_unit': 'read_pairs', 'input_records': total,
              'retained_records': retained, 'removed_records': total-retained,
              'input_bytes_read': read_bytes, 'output_bytes_written': written_bytes}
    save_json(Path(config['result']), result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    execute(json.loads(parser.parse_args().config.read_text()))
