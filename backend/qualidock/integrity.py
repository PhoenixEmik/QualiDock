"""Bounded, read-only FASTQ validation. Does not infer biology or alter FastQC QC."""
import gzip
import hashlib
import io
import os
from pathlib import Path
import struct
import stat
import time
import zlib

VERSION = '1.0'
MAX_LINE = 1024 * 1024
MAX_READ = 4 * 1024 * 1024
IUPAC = frozenset(b'ACGTURYSWKMBDHVNacgturyswkmbdhvn')


class Unsupported(ValueError):
    pass


def snapshot(stat):
    return {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'device': stat.st_dev, 'inode': stat.st_ino}


class HashedRaw(io.RawIOBase):
    def __init__(self, stream):
        self.stream = stream
        self.sha = hashlib.sha256()
        self.bytes_read = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        count = self.stream.readinto(buffer)
        if count:
            self.sha.update(memoryview(buffer)[:count])
            self.bytes_read += count
        return count


def line(stream):
    value = stream.readline(MAX_LINE + 1)
    if len(value) > MAX_LINE:
        raise Unsupported('Line exceeds the 1 MiB supported validation limit')
    return value


def normalize_identifier(identifier):
    """Only the terminal conventional mate suffix; never fuzzy/substring matching."""
    return identifier[:-2] if identifier.endswith((b'/1', b'/2')) else identifier


def record(stream, raw=None):
    # Optional bounded record capture lets synchronized selectors preserve the
    # original bytes without maintaining another FASTQ parser.
    def read_line():
        value = line(stream)
        if raw is not None: raw.append(value)
        return value

    header = read_line()
    if not header:
        return None
    if not header.startswith(b'@') or not header[1:].strip():
        raise ValueError('Expected a non-empty FASTQ @ identifier')
    identifier = header[1:].split()[0]
    length = 0
    while True:
        sequence = read_line()
        if not sequence:
            raise ValueError('Truncated FASTQ sequence or missing + separator')
        if sequence.startswith(b'+'):
            repeated = sequence[1:].strip()
            if repeated and repeated.split()[0] != identifier:
                raise ValueError('FASTQ + identifier differs from its @ identifier')
            break
        bases = sequence.rstrip(b'\r\n')
        if any(base not in IUPAC for base in bases):
            raise ValueError('Sequence contains a character outside the supported IUPAC nucleotide alphabet')
        length += len(bases)
        if length > MAX_READ:
            raise Unsupported('Read exceeds the 4 MiB supported validation limit')
    quality_length, histogram = 0, [0] * 94
    while quality_length < length or length == 0:
        quality = read_line()
        if not quality:
            raise ValueError('Truncated FASTQ qualities')
        quality = quality.rstrip(b'\r\n')
        quality_length += len(quality)
        if quality_length > length:
            raise ValueError('Sequence and quality lengths differ')
        for value in quality:
            if not 33 <= value <= 126:
                raise ValueError('Quality character is outside printable ASCII 33–126')
            histogram[value - 33] += 1
        if not length:
            break
    # Exact first tokens, removing only the conventional mate suffix. Order remains
    # in the length-framed rolling digest; no reordering or fuzzy ID matching occurs.
    normalized = normalize_identifier(identifier)
    return normalized, length, histogram


def scan_file(entry, mode='full', quick_reads=10000, progress=lambda value: None):
    result = {'id': entry['id'], 'path': entry['path'], 'state': 'running', 'coverage': 'partial',
              'records_scanned': 0, 'bases_scanned': 0, 'compressed_bytes_read': 0,
              'gzip_crc': 'not_evaluated', 'sha256': None, 'checksum_status': 'not_evaluated',
              'id_order_sha256': None, 'q20_bases': None, 'q30_bases': None,
              'quality_bases': None, 'phred_offset': entry.get('phred_offset'),
              'encoding_source': entry.get('encoding_source'), 'min_length': None, 'max_length': None,
              'source_snapshot': entry.get('snapshot'), 'error': None}
    result['qc_input_snapshot_verified'] = entry.get('qc_input_snapshot_verified', False)
    if not entry['path'].lower().endswith('.gz'):
        result['gzip_crc'] = 'not_applicable'
    if entry.get('preflight_error'):
        result.update(state='failed', error=entry['preflight_error'])
        return result
    path = Path(entry['path'])
    opened = None
    try:
        if path.resolve(strict=True) != path or path.is_symlink():
            raise ValueError('Source path changed or contains symlink components')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb', buffering=0) as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError('FASTQ source is not a regular file')
            before = snapshot(os.fstat(source.fileno()))
            if before != entry['snapshot']:
                raise ValueError('Source changed before validation started')
            hashed = HashedRaw(source)
            buffered = io.BufferedReader(hashed, buffer_size=64 * 1024)
            compressed = path.name.lower().endswith('.gz') or buffered.peek(2)[:2] == b'\x1f\x8b'
            result['gzip_crc'] = 'not_evaluated' if compressed else 'not_applicable'
            opened = gzip.GzipFile(fileobj=buffered, mode='rb') if compressed else buffered
            ordered = hashlib.sha256()
            histogram = [0] * 94
            last_progress = 0.0
            full = False
            while True:
                parsed = record(opened)
                if parsed is None:
                    full = True
                    break
                identifier, length, qualities = parsed
                ordered.update(struct.pack('>I', len(identifier)))
                ordered.update(identifier)
                result['records_scanned'] += 1
                result['bases_scanned'] += length
                result['min_length'] = length if result['min_length'] is None else min(result['min_length'], length)
                result['max_length'] = length if result['max_length'] is None else max(result['max_length'], length)
                histogram = [a + b for a, b in zip(histogram, qualities)]
                result['compressed_bytes_read'] = hashed.bytes_read
                if time.monotonic() - last_progress >= 1:
                    progress(dict(result))
                    last_progress = time.monotonic()
                if mode == 'quick' and result['records_scanned'] >= quick_reads:
                    full = not opened.read(1)
                    break
            result['compressed_bytes_read'] = hashed.bytes_read
            if snapshot(os.fstat(source.fileno())) != before or snapshot(path.stat()) != before or path.resolve() != path:
                raise ValueError('Source changed during validation; no complete result can be asserted')
            if full:
                if hashed.bytes_read != before['size']:
                    raise ValueError('Not all source bytes were included in the checksum')
                result.update(state='passed', coverage='full', sha256=hashed.sha.hexdigest(),
                              checksum_status='computed_source_not_transfer_verified', id_order_sha256=ordered.hexdigest(),
                              gzip_crc='verified' if compressed else 'not_applicable')
                offset = entry.get('phred_offset')
                if offset in {33, 64}:
                    if any(histogram[:offset - 33]):
                        raise ValueError('Qualities conflict with the explicitly reported encoding')
                    result.update(q20_bases=sum(histogram[max(0, offset + 20 - 33):]),
                                  q30_bases=sum(histogram[max(0, offset + 30 - 33):]), quality_bases=sum(histogram))
            else:
                result.update(state='not_evaluated', error='Quick scan stopped at its read limit; full structure, gzip CRC, checksum and pairing are not evaluated')
    except Unsupported as exc:
        result.update(state='not_evaluated', error=str(exc))
    except (OSError, EOFError, ValueError, zlib.error) as exc:
        result.update(state='failed', error=str(exc))
        if isinstance(exc, (gzip.BadGzipFile, EOFError, zlib.error)):
            result['gzip_crc'] = 'failed'
    finally:
        if opened is not None:
            opened.close()
    if result['state'] != 'passed':
        result.update(sha256=None, id_order_sha256=None, checksum_status='not_evaluated', q20_bases=None, q30_bases=None, quality_bases=None)
    return result


def compare_pairs(pairs, files, expected_paths=None):
    lookup = {record['path']: record for record in files}
    result = []
    for pair in pairs:
        left, right = lookup.get(pair['r1']), lookup.get(pair['r2'])
        state, error = 'not_evaluated', 'Both mates require complete scans before synchronization can be asserted'
        if not left or not right:
            if expected_paths is None or pair['r1'] not in expected_paths or pair['r2'] not in expected_paths:
                state, error = 'failed', 'A configured mate is missing from the selected inputs'
        elif left['state'] == 'failed' or right['state'] == 'failed':
            state, error = 'failed', 'At least one mate failed full input validation'
        elif left['state'] == right['state'] == 'passed':
            if left['records_scanned'] != right['records_scanned']:
                state, error = 'failed', 'Mate read counts differ'
            elif left['id_order_sha256'] != right['id_order_sha256']:
                state, error = 'failed', 'Normalized mate identifiers or their order differ'
            else:
                state, error = 'passed', None
        result.append({**pair, 'state': state, 'error': error, 'method': 'SHA-256 of length-framed normalized identifiers in original order'})
    return result
