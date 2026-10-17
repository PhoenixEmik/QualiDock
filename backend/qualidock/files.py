from pathlib import Path
import re
import os
import stat as file_stat
import threading
import time
import uuid
from collections import OrderedDict
from .sample_metadata import PAIR_NAME, describe

FASTQ = re.compile(r"\.(?:fastq|fq)(?:\.gz)?$", re.I)
ALIGNMENT = re.compile(r'\.(?:bam|cram)$', re.I)
PAIR = PAIR_NAME


class PathViolation(ValueError):
    pass


class DirectoryChanged(ValueError):
    pass


def approved_file(path):
    """Operator-owned local reference/panel; source input roots use FileAccess."""
    if not path.is_absolute() or '##idx##' in str(path) or path.resolve(strict=True) != path or not path.is_file() or not path.stat().st_mode & 0o444 or not os.access(path, os.R_OK):
        raise ValueError('Approved reference/panel files must be local readable regular files without symlinks')
    info = path.stat()
    if info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o022:
        raise ValueError('Approved files must be owned by this user/root and not group/world writable')
    return path


MAX_INDEX_ENTRIES = 200000
MAX_CACHED_DIRECTORIES = 8
CACHE_IDLE_SECONDS = 300


class FileAccess:
    def __init__(self, roots: list[Path]):
        self.roots = [p.resolve(strict=True) for p in roots]
        if not self.roots or not all(p.is_dir() for p in self.roots):
            raise ValueError("Configure at least one existing directory root")
        self._snapshots = OrderedDict()
        self._index_lock = threading.RLock()

    def resolve(self, raw: str) -> Path:
        if "\x00" in raw or ".." in Path(raw).parts:
            raise PathViolation("Path traversal is not allowed")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise PathViolation("An absolute path within a configured root is required")
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise PathViolation("Path is unavailable") from exc
        if not any(resolved.is_relative_to(root) for root in self.roots):
            raise PathViolation("Path is outside the configured roots")
        return resolved

    @staticmethod
    def signature(directory):
        stat = directory.stat()
        return stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns

    def _entry(self, directory, name):
        path = directory / name
        info = path.lstat()
        if file_stat.S_ISLNK(info.st_mode):
            target = self.resolve(str(path))
            info = target.stat()
        if not (file_stat.S_ISREG(info.st_mode) or file_stat.S_ISDIR(info.st_mode)):
            return None
        kind = "directory" if file_stat.S_ISDIR(info.st_mode) else "fastq" if FASTQ.search(name) else "fastqc" if name.endswith("_fastqc.zip") or name == "fastqc_data.txt" else "qcreport" if name.lower() == "fastp.json" or name.lower().endswith(".fastp.json") else "file"
        pair = PAIR.match(FASTQ.sub("", name)) if kind == "fastq" else None
        if kind == 'file' and ALIGNMENT.search(name):
            kind = 'alignment'
        return {"name": name, "path": str(path), "kind": kind,
                "size": info.st_size if kind != "directory" else None, "modified": info.st_mtime,
                "read": f"R{pair[3]}" if pair else None,
                "pair_key": str(directory / (pair[1] + pair[4])) if pair else None,
                "paired": False, "mate": None, "ambiguous": False, **(describe(path) if kind == "fastq" else {})}

    def _snapshot(self, directory, token, refresh):
        signature = self.signature(directory)
        with self._index_lock:
            cached = self._snapshots.get(str(directory))
            valid = cached and cached['signature'] == signature and time.monotonic() - cached['accessed'] <= CACHE_IDLE_SECONDS
            if token and (not valid or cached['token'] != token):
                raise DirectoryChanged("Directory changed or listing expired. Refresh the directory before loading more files.")
            if valid and not refresh:
                cached['accessed'] = time.monotonic()
                self._snapshots.move_to_end(str(directory))
                return cached
            names, groups = [], {}
            with os.scandir(directory) as children:
                for child in children:
                    if child.name.startswith('.'):
                        continue
                    try:
                        if child.is_symlink():
                            entry = self._entry(directory, child.name)
                            if entry is None:
                                continue
                            is_directory = entry['kind'] == 'directory'
                        else:
                            is_directory = child.is_dir(follow_symlinks=False)
                            if not is_directory and not child.is_file(follow_symlinks=False):
                                continue
                        names.append((child.name, is_directory))
                        if len(names) > MAX_INDEX_ENTRIES:
                            raise ValueError(f"Directory exceeds {MAX_INDEX_ENTRIES:,} entries. Choose a smaller subdirectory.")
                        if not is_directory and FASTQ.search(child.name):
                            pair = PAIR.match(FASTQ.sub('', child.name))
                            if pair:
                                groups.setdefault(pair[1] + pair[4], {}).setdefault('R' + pair[3], []).append(child.name)
                    except (PathViolation, OSError):
                        continue
            names.sort(key=lambda item: (not item[1], item[0].casefold(), item[0]))
            if self.signature(directory) != signature:
                raise DirectoryChanged("Directory changed while indexing. Refresh and try again.")
            samples = {}
            for name, is_directory in names:
                if is_directory or not FASTQ.search(name):
                    continue
                details = describe(directory / name)
                pair = PAIR.match(FASTQ.sub('', name))
                group = groups.get(pair[1] + pair[4], {}) if pair else {}
                if details['sample_key'] and not any(len(group.get(read, [])) > 1 for read in ('R1', 'R2')):
                    samples.setdefault(details['sample_key'], []).append(str(directory / name))
            cached = {'signature': signature, 'names': names, 'groups': groups, 'samples': samples, 'token': uuid.uuid4().hex, 'accessed': time.monotonic()}
            self._snapshots.pop(str(directory), None)
            while self._snapshots and (len(self._snapshots) >= MAX_CACHED_DIRECTORIES or sum(len(value['names']) for value in self._snapshots.values()) + len(names) > MAX_INDEX_ENTRIES):
                self._snapshots.popitem(last=False)
            self._snapshots[str(directory)] = cached
            return cached

    def _pair(self, current, cached, entry):
        if current and current['pair_key']:
            pair = PAIR.match(FASTQ.sub('', current['name']))
            group = cached['groups'].get(pair[1] + pair[4], {})
            current['ambiguous'] = any(len(group.get(read, [])) > 1 for read in ('R1', 'R2'))
            if len(group.get('R1', [])) == len(group.get('R2', [])) == 1:
                mate = entry(group['R2' if current['read'] == 'R1' else 'R1'][0])
                if mate and mate['kind'] == 'fastq':
                    current['paired'], current['mate'] = True, mate['path']
        return current

    def pairing(self, paths: list[Path]) -> list[dict]:
        """Persist the same confirmed relationships used by the explorer.

        Inspect directory naming groups, including unselected ambiguous names,
        but read metadata only for requested files and their potential mates.
        """
        result = []
        for directory in dict.fromkeys(path.parent for path in paths):
            self.resolve(str(directory))
            cached = self._snapshot(directory, None, False)
            checked = {}
            def entry(name):
                if name not in checked:
                    checked[name] = self._entry(directory, name)
                return checked[name]
            for path in paths:
                if path.parent == directory:
                    current = self._pair(entry(path.name), cached, entry)
                    if current:
                        result.append({key: current[key] for key in ('path', 'name', 'read', 'pair_key', 'paired', 'mate', 'lane', 'chunk', 'ambiguous')})
            if self.resolve(str(directory)) != directory or self.signature(directory) != cached['signature']:
                raise DirectoryChanged("Directory changed while confirming pairs. Refresh and retry.")
        return result

    def browse(self, raw: str, offset: int = 0, limit: int = 500, snapshot: str | None = None, refresh: bool = False) -> dict:
        if offset < 0 or not 1 <= limit <= 500 or refresh and offset:
            raise ValueError("Invalid directory pagination")
        directory = self.resolve(raw)
        if not directory.is_dir():
            raise PathViolation("Choose a directory")
        cached = self._snapshot(directory, snapshot, refresh)
        entries, checked = [], {}
        def entry(name):
            if name not in checked:
                try:
                    checked[name] = self._entry(directory, name)
                except (PathViolation, OSError):
                    checked[name] = None
            return checked[name]
        for name, _ in cached['names'][offset:offset + limit]:
            current = entry(name)
            if current is None:
                continue
            entries.append(self._pair(current, cached, entry))
        # Never combine pages from different filesystem generations or a replaced parent.
        if self.resolve(str(directory)) != directory or self.signature(directory) != cached['signature']:
            raise DirectoryChanged("Directory changed while reading the page. Refresh and try again.")
        parent = directory.parent if any(directory.parent.is_relative_to(r) for r in self.roots) else None
        total = len(cached['names'])
        following = offset + limit
        sample_keys = {entry.get('sample_key') for entry in entries if not entry.get('ambiguous')}
        sample_groups = {key: {'paths': cached['samples'][key][:501], 'total': len(cached['samples'][key])} for key in sample_keys if key in cached['samples']}
        return {"sample_groups": sample_groups, "path": str(directory), "parent": str(parent) if parent else None, "entries": entries,
                "total": total, "snapshot": cached['token'], "next_offset": following if following < total else None}
