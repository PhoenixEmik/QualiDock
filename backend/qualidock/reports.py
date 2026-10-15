"""Discover and snapshot bounded FastQC reports, never source sequencing data."""
from pathlib import Path
from .files import FileAccess, PathViolation
from .metrics import MAX_DATA

MAX_REPORTS = 500
MAX_SCAN = 20000
MAX_IMPORT = 512 * 1024 * 1024


def metadata(path: Path) -> dict:
    stat = path.stat()
    return {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def discover(paths: list[Path], access: FileAccess) -> list[dict]:
    candidates = set()
    inspected = 0
    def visit(path, depth=0):
        nonlocal inspected
        if depth > 64:
            raise ValueError("Report directory nesting exceeds 64 levels")
        inspected += 1
        if inspected > MAX_SCAN:
            raise ValueError("Report directory exceeds 20,000 entries; select a smaller directory")
        # Resolve every traversed entry. In particular, never let MultiQC follow an escaped symlink.
        resolved = access.resolve(str(path))
        if path.is_symlink():
            raise PathViolation("Report directory imports must not contain symlinks")
        if resolved.is_dir():
            for child in resolved.iterdir():
                if not child.name.startswith('.'):
                    visit(child, depth + 1)
        elif resolved.is_file() and (resolved.name.endswith('_fastqc.zip') or resolved.name == 'fastqc_data.txt'):
            candidates.add(resolved)
            if len(candidates) > MAX_REPORTS * 2:
                raise ValueError("Select at most 500 FastQC reports")
    for path in paths:
        visit(path)
    # FastQC may leave both its ZIP and extracted directory. Import each result once.
    candidates = {p for p in candidates if p.name != 'fastqc_data.txt' or Path(str(p.parent) + '.zip') not in candidates}
    if not candidates:
        raise ValueError("No supported FastQC ZIPs or extracted fastqc_data.txt reports were found")
    if len(candidates) > MAX_REPORTS:
        raise ValueError("Select at most 500 FastQC reports")
    result, total = [], 0
    for path in sorted(candidates):
        if path.stat().st_size > (128 * 1024 * 1024 if path.suffix == '.zip' else MAX_DATA):
            raise ValueError(f"QC report exceeds the import size limit: {path.name}")
        record = {**metadata(path), "companions": []}
        companions = [path.with_name('summary.txt'), path.parent / 'fastqc_report.html'] if path.name == 'fastqc_data.txt' else [path.with_suffix('.html')]
        for companion in companions:
            if companion.exists() or companion.is_symlink():
                checked = access.resolve(str(companion))
                if companion.is_symlink() or not checked.is_file() or checked.stat().st_size > MAX_DATA:
                    raise PathViolation("Report companion is not a bounded regular file")
                record['companions'].append(metadata(checked))
        total += record['size'] + sum(item['size'] for item in record['companions'])
        if total > MAX_IMPORT:
            raise ValueError("QC report imports exceed 512 MiB; select fewer reports")
        result.append(record)
    return result
