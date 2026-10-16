"""Bounded first-record preview. No hashing, indexing, QC or persisted read data."""
import gzip
import io
import os
from pathlib import Path
import stat
import zlib

from . import datasets
from .files import FASTQ, PathViolation
from .integrity import record, snapshot, Unsupported

MAX_COMPRESSED = 512 * 1024
MAX_DECOMPRESSED = 128 * 1024
MAX_RECORD = 32 * 1024
MAX_RESPONSE = 512 * 1024


class LimitedRaw(io.RawIOBase):
    def __init__(self, stream):
        self.stream, self.count = stream, 0

    def readable(self):
        return True

    def readinto(self, buffer):
        count = self.stream.readinto(memoryview(buffer)[:MAX_COMPRESSED - self.count + 1])
        self.count += count
        if self.count > MAX_COMPRESSED:
            raise Unsupported('Compressed preview byte limit exceeded')
        return count


class PreviewLines:
    def __init__(self, stream):
        self.stream, self.total, self.current = stream, 0, 0

    def readline(self, size):
        value = self.stream.readline(min(size, MAX_DECOMPRESSED-self.total+1, MAX_RECORD-self.current+1))
        self.total += len(value)
        self.current += len(value)
        if self.total > MAX_DECOMPRESSED or self.current > MAX_RECORD:
            raise Unsupported('FASTQ preview record or decompressed byte limit exceeded')
        return value


def preview(path, count):
    result = {'path': str(path), 'records': [], 'status': 'available', 'error': None,
              'quality_encoding': 'not_inferred', 'coverage': 'first_records_only'}
    try:
        if path.resolve(strict=True) != path:
            raise PathViolation('FASTQ preview does not follow symlinks')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb', buffering=0) as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode): raise ValueError('FASTQ is not a regular file')
            limited = LimitedRaw(source)
            with io.BufferedReader(limited, buffer_size=8192) as buffered:
                compressed = path.name.lower().endswith('.gz') or buffered.peek(2)[:2] == b'\x1f\x8b'
                opened = gzip.GzipFile(fileobj=buffered, mode='rb') if compressed else buffered
                try:
                    lines = PreviewLines(opened)
                    for ordinal in range(1, count+1):
                        raw = []
                        lines.current = 0
                        parsed = record(lines, raw)
                        if parsed is None: break
                        separator = next(i for i, line in enumerate(raw[1:],1) if line.startswith(b'+'))
                        result['records'].append({'ordinal': ordinal, 'identifier': raw[0][1:].rstrip(b'\r\n').decode('ascii'),
                                                  'length': parsed[1], 'sequence': b''.join(line.rstrip(b'\r\n') for line in raw[1:separator]).decode('ascii'),
                                                  'quality': b''.join(line.rstrip(b'\r\n') for line in raw[separator+1:]).decode('ascii')})
                    result.update(compressed=compressed, compressed_bytes_read=limited.count, decompressed_bytes_read=lines.total)
                    if snapshot(os.fstat(source.fileno())) != snapshot(before) or snapshot(path.stat()) != snapshot(before) or path.resolve() != path:
                        raise ValueError('FASTQ changed during preview; retry')
                finally:
                    if compressed: opened.close()
        if not result['records']: result['status'] = 'empty'
    except PathViolation:
        raise
    except Unsupported:
        result.update(status='record_too_large', error='Preview byte limit exceeded; full-file QC remains available', records=[])
    except (OSError, EOFError, ValueError, zlib.error):
        # Never include parser exceptions containing raw identifiers/sequences.
        result.update(status='unavailable', error='FASTQ is unavailable, malformed, changed, or uses unsupported header text', records=[])
    return result


def inspect(manager, paths, references, count, paired):
    if len(set(paths)) != len(paths): raise ValueError('Select distinct FASTQs')
    registered = datasets.registered(manager, references)
    if set(registered)-set(paths): raise ValueError('Derived references must be selected')
    resolved = []
    for raw in paths:
        path = datasets.resolve(manager, raw, registered)
        if raw not in registered and any(path.is_relative_to(root) for root in manager.stores.roots):
            raise PathViolation('Results require an exact registered derived dataset reference')
        if str(path) != raw or not FASTQ.search(path.name):
            raise PathViolation('Select an exact FASTQ path without aliases or symlinks')
        resolved.append(path)
    if paired and len(paths) != 2: raise ValueError('A confirmed preview pair requires R1 and R2')
    files = [preview(path, count) for path in resolved]
    pairs = []
    if paired and all(row['status'] in {'available','empty'} for row in files):
        from .integrity import normalize_identifier
        for index in range(max(len(row['records']) for row in files)):
            records = [row['records'][index] if index < len(row['records']) else None for row in files]
            matched = all(records) and len({normalize_identifier(row['identifier'].split()[0].encode()) for row in records}) == 1
            pairs.append({'ordinal':index+1,'status':'match' if matched else 'mismatch'})
    return {'files':files,'pairs':pairs,'paired':paired,'pairing_scope':'User-confirmed R1/R2; observed first-N identifiers only, never whole-file synchronization',
            'limits':{'records':count,'record_bytes':MAX_RECORD,'decompressed_bytes_per_file':MAX_DECOMPRESSED,'compressed_bytes_per_file':MAX_COMPRESSED,'response_bytes':MAX_RESPONSE}}
