"""Shared MultiQC I/O; callers own input selection, naming policy and run state."""
import asyncio
import json
from .import_formats import source_mappings
from .metrics import parse_multiqc, bounded_text
from .store import save_json


async def execute(manager, run, reports, *, options=(), config=None):
    directory = manager.directory(run['id'])
    manager.stores.subdirectory(run['id'], 'multiqc', exist_ok=True)
    if any('\n' in str(path) or '\r' in str(path) for path in reports):
        raise ValueError('MultiQC report paths cannot contain newlines')
    file_list = directory / 'multiqc-inputs.txt'
    file_list.write_text(''.join(str(path)+'\n' for path in reports))
    arguments = list(options)
    if config is not None:
        config_path = directory / 'multiqc-config.json'
        save_json(config_path, config)
        arguments += ['--config', str(config_path)]
    code = await manager.command(run, 'multiqc', [run['tools']['multiqc']['executable'],
        '--file-list', str(file_list), '--outdir', str(directory/'multiqc'), '--force',
        '--data-format', 'json', '--no-version-check', *arguments], directory)
    if run['id'] in manager.cancelled: return None
    if code: return f'MultiQC exited with code {code}. See analysis log.'
    if not (directory/'multiqc/multiqc_report.html').is_file():
        return 'MultiQC did not produce an HTML report.'
    return None


async def summary(directory):
    structured = directory/'multiqc/multiqc_data/multiqc_data.json'
    if not structured.exists():
        return {'status':'missing', 'message':'MultiQC structured JSON was not generated; inspect the log and official report.', 'columns':[], 'rows':[]}
    try:
        return await asyncio.to_thread(parse_multiqc, structured)
    except (ValueError, OSError, UnicodeError, TypeError) as exc:
        return {'status':'invalid', 'message':f'Cannot parse MultiQC General Statistics: {exc}', 'columns':[], 'rows':[]}


async def report_names(directory, reports, statistics=None, *, sample_names=None):
    sources = await asyncio.to_thread(source_mappings, directory/'multiqc/multiqc_data/multiqc_data.json')
    actual = set(sample_names) if sample_names is not None else {row['sample'] for row in statistics['rows']}
    names = {}
    for path in reports:
        candidates = sources.get(str(path), set()) & actual
        names[str(path.relative_to(directory))] = next(iter(candidates)) if len(candidates) == 1 else None
    return names


async def alignment_sample_names(directory, mode):
    """Verified official MultiQC 1.x raw modules; RSeQC has no General Stats."""
    data = await asyncio.to_thread(bounded_text, directory/'multiqc/multiqc_data/multiqc_data.json')
    raw = json.loads(data).get('report_saved_raw_data', {})
    key = {'rseqc-infer':'multiqc_rseqc_infer_experiment',
           'rseqc-distribution':'multiqc_rseqc_read_distribution',
           'picard':'multiqc_picard_insertSize'}[mode]
    rows = raw.get(key, {}) if isinstance(raw, dict) else {}
    if not isinstance(rows, dict):return set()
    if mode == 'picard':
        return {row['SAMPLE_NAME'] for row in rows.values() if isinstance(row, dict) and isinstance(row.get('SAMPLE_NAME'),str)}
    return {name for name, row in rows.items() if isinstance(name,str) and isinstance(row,dict) and row}
