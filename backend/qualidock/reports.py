"""Discover and snapshot bounded supported QC reports, never source sequencing data."""
from pathlib import Path
from .files import FileAccess, PathViolation
from .metrics import MAX_DATA
from .import_formats import fastp_metadata

MAX_REPORTS = 500
MAX_SCAN = 20000
MAX_IMPORT = 512 * 1024 * 1024


def metadata(path: Path) -> dict:
    stat = path.stat()
    return {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def discover(paths: list[Path], access: FileAccess, summary=None) -> list[dict]:
    candidates = set()
    inspected = 0
    summary = summary if summary is not None else {}
    summary.update(unsupported_files=0, exclusions=[])
    explicit = set(paths)
    def excluded(path,reason):
        summary["unsupported_files"] += 1
        if len(summary["exclusions"]) < 20:
            summary["exclusions"].append({"filename":path.name,"reason":reason})
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
        elif resolved.is_file() and (resolved.name.endswith('_fastqc.zip') or resolved.name == 'fastqc_data.txt' or resolved.suffix.lower() == '.json'):
            candidates.add(resolved)
            if len(candidates) > MAX_REPORTS * 2:
                raise ValueError("Select at most 500 supported QC reports")
        elif resolved.is_file():
            companion = (resolved.name in {'summary.txt','fastqc_report.html'} and resolved.with_name('fastqc_data.txt').exists()) or (resolved.name.endswith('_fastqc.html') and resolved.with_suffix('.zip').exists())
            if companion and resolved not in explicit:return
            if resolved in explicit:
                raise ValueError("Unsupported report input: select FastQC reports or fastp JSON")
            excluded(resolved,"Not an allowlisted QC-report format")
    for path in paths:
        visit(path)
    # FastQC may leave both its ZIP and extracted directory. Import each result once.
    candidates = {p for p in candidates if p.name != 'fastqc_data.txt' or Path(str(p.parent) + '.zip') not in candidates}
    if not candidates:
        raise ValueError("No supported FastQC ZIPs, extracted fastqc_data.txt or fastp JSON reports were found")
    if len(candidates) > MAX_REPORTS:
        raise ValueError("Select at most 500 supported QC reports")
    result, total = [], 0
    for path in sorted(candidates):
        if path.stat().st_size > (128 * 1024 * 1024 if path.suffix == '.zip' else MAX_DATA):
            raise ValueError(f"QC report exceeds the import size limit: {path.name}")
        details = {'kind':'fastqc','tool':'FastQC','version':None,'schema':'fastqc.data.v1'}
        if path.suffix.lower() == '.json':
            try:
                details = fastp_metadata(path)
            except (ValueError,UnicodeError,RecursionError) as exc:
                if path in explicit:
                    raise ValueError(f"Unsupported report {path.name}: {exc}") from exc
                excluded(path,str(exc));continue
        record = {**metadata(path), **details, "companions": []}
        companions = [path.with_name('summary.txt'), path.parent / 'fastqc_report.html'] if path.name == 'fastqc_data.txt' else [path.with_suffix('.html')]
        for companion in companions if details['kind'] == 'fastqc' else []:
            if companion.exists() or companion.is_symlink():
                checked = access.resolve(str(companion))
                if companion.is_symlink() or not checked.is_file() or checked.stat().st_size > MAX_DATA:
                    raise PathViolation("Report companion is not a bounded regular file")
                record['companions'].append(metadata(checked))
        total += record['size'] + sum(item['size'] for item in record['companions'])
        if total > MAX_IMPORT:
            raise ValueError("QC report imports exceed 512 MiB; select fewer reports")
        result.append(record)
    if not result:
        raise ValueError("No supported FastQC or fastp reports were found; unknown QC formats are excluded")
    summary["supported_reports"] = len(result)
    return result
