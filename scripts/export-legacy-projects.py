#!/usr/bin/env python3
"""One-shot, offline, read-only export of the removed project catalog.

This is not imported by the application. Stop QualiDock before running it.
The original database and every analysis directory remain untouched.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

TABLES = ('entities', 'analysis_links', 'associations', 'evidence', 'events', 'batch_plans', 'batch_attempts')


def export(database, destination):
    database, destination = Path(database).absolute(), Path(destination).absolute()
    info = database.lstat()
    if database.resolve(strict=True) != database or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise ValueError('Catalog must be a private, owned regular file without symlink components')
    if any(Path(str(database) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('Catalog has transaction sidecars; close the old server cleanly before exporting')
    lock_path = database.parent / '.lock'
    with os.fdopen(os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as lock:
        if os.fstat(lock.fileno()).st_uid != os.getuid():
            raise ValueError('Result-store lock must be owned by the current user')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = database.stat()
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (1, 2, 3):
                raise ValueError(f'Unsupported legacy catalog schema: {version}; original preserved')
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            tables = {name: [dict(row) for row in db.execute(f'SELECT * FROM "{name}"')] for name in TABLES if name in names}
        # Include a byte-level checksum of the unchanged original for archival use.
        with database.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = database.stat()
        if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size):
            raise ValueError('Catalog changed during export; retry with all servers stopped')
        value = {'format': 'qualidock.legacy-project-export.v1', 'catalog_schema': version, 'catalog_sha256': checksum, 'tables': tables}
        # Exclusive creation: never replace another export, source file or analysis.
        with destination.open('x', encoding='utf-8') as stream:
            os.chmod(destination, 0o600)
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
        return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    export(args.database, args.destination)
