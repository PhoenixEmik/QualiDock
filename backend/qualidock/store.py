"""A restricted set of owned result stores, each held under an exclusive lock."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import stat

from .files import PathViolation


class ResultStores:
    def __init__(self, default, roots):
        self.default = Path(default).absolute()
        self.roots = list(dict.fromkeys([self.default, *[Path(p).absolute() for p in roots]]))
        self.locks = {}
        self.identities = {}
        self.paths = {}

    def check(self, root, writable=True):
        if '..' in root.parts or root.resolve(strict=True) != root or not root.is_dir():
            raise PathViolation('Output root must be an existing directory without symlink components')
        info = root.stat()
        if info.st_uid != os.getuid() or writable and (not info.st_mode & stat.S_IWUSR or not os.access(root, os.W_OK | os.X_OK)):
            raise PathViolation('Output root must be owned by the current Unix user and writable')
        if root in self.identities and (info.st_dev, info.st_ino) != self.identities[root]:
            raise PathViolation('Output root was replaced; restart the session to reacquire its lock')
        return info

    def start(self):
        self.default.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            for root in sorted(self.roots):
                info = self.check(root)
                if any(root != other and (root.is_relative_to(other) or other.is_relative_to(root)) for other in self.roots):
                    raise ValueError('Output roots must be distinct, non-nested directories')
                descriptor = os.open(root / '.lock', os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                lock = os.fdopen(descriptor, 'a')
                try:
                    if os.fstat(lock.fileno()).st_uid != os.getuid():
                        raise PathViolation('Output lock must belong to the current Unix user')
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except Exception:
                    lock.close()
                    raise
                self.locks[root] = lock
                self.identities[root] = (info.st_dev, info.st_ino)
        except Exception as exc:
            self.close()
            raise RuntimeError(f'Cannot own results directory: {exc}. Another QualiDock session may own this results directory.') from exc

    def close(self):
        for lock in self.locks.values():
            if not lock.closed:
                lock.close()
        self.locks.clear()

    def resolve(self, raw=None):
        root = Path(raw) if raw else self.default
        if not root.is_absolute() or '..' in root.parts or root not in self.roots:
            raise PathViolation('Select an explicitly configured output root')
        try:
            self.check(root)
        except OSError as exc:
            raise PathViolation('Output root is unavailable') from exc
        if root not in self.locks or self.locks[root].closed:
            raise PathViolation('Output root is not locked by this session')
        return root

    def listing(self):
        result = []
        for root in self.roots:
            try:
                self.resolve(str(root))
                free = shutil.disk_usage(root).free
                error = None if free >= 1024 * 1024 else 'Output filesystem has less than 1 MiB free'
            except (OSError, ValueError) as exc:
                free, error = None, str(exc)
            result.append({'path': str(root), 'default': root == self.default, 'available': error is None, 'free_bytes': free, 'error': error})
        return result

    def allocate(self, run_id, raw=None):
        root = self.resolve(raw)
        if shutil.disk_usage(root).free < 1024 * 1024:
            raise ValueError('Output filesystem has less than 1 MiB free')
        if run_id in self.paths:
            raise ValueError('Analysis output collision; existing results were preserved')
        directory = root / run_id
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise ValueError('Analysis output collision; existing results were preserved') from exc
        except OSError as exc:
            raise PathViolation('Cannot create analysis output directory: permission or filesystem error') from exc
        self.paths[run_id] = directory
        return directory

    def directory(self, run_id):
        directory = self.paths[run_id]
        self.check(directory.parent, writable=False)
        if directory.parent not in self.locks or self.locks[directory.parent].closed:
            raise PathViolation('Result store is not owned by this session')
        if not re.fullmatch('[a-f0-9]{32}', run_id) or directory.is_symlink() or not directory.is_dir() or directory.resolve(strict=True) != directory or directory.stat().st_uid != os.getuid():
            raise PathViolation('Result directory is unavailable')
        return directory
