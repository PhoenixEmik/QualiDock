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
    value = json.loads(data)
    raw = value.get('report_saved_raw_data', {}) if isinstance(value,dict) else {}
    key = {'rseqc-genebody':'rseqc_gene_body_cov', 'rseqc-infer':'multiqc_rseqc_infer_experiment',
           'rseqc-distribution':'multiqc_rseqc_read_distribution',
           'picard-rna':'multiqc_picard_RnaSeqMetrics', 'picard':'multiqc_picard_insertSize'}[mode]
    rows = raw.get(key, {}) if isinstance(raw, dict) else {}
    if not isinstance(rows, dict):return set()
    if mode == 'picard':
        return {row['SAMPLE_NAME'] for row in rows.values() if isinstance(row, dict) and isinstance(row.get('SAMPLE_NAME'),str)}
    return {name for name, row in rows.items() if isinstance(name,str) and isinstance(row,dict) and row}


async def verify_picard_rna(directory, run, names):
    """Verify the two qualified official schemas against original ALL_READS data."""
    from decimal import Decimal, InvalidOperation
    value = json.loads(await asyncio.to_thread(bounded_text, directory/'multiqc/multiqc_data/multiqc_data.json'))
    raw = value.get('report_saved_raw_data', {}).get('multiqc_picard_RnaSeqMetrics', {})
    if not isinstance(raw,dict) or any(not isinstance(v,dict) for v in raw.values()):raise ValueError('Malformed MultiQC RNA sample data')
    expected = {r['report']:r['picard'] for r in run['qc']['results'] if r['state']=='completed'}
    if set(names)!=set(expected) or any(not n for n in names.values()) or len(set(names.values()))!=len(names) or set(raw)!=set(names.values()):
        raise ValueError('Incomplete or ambiguous MultiQC Picard RNA source mapping')
    for report,data in expected.items():
        observed = raw[names[report]]
        for key,original in zip(data['metrics']['columns'][:-3],data['metrics']['rows'][0][:-3]):
            if original=='':
                if observed.get(key) not in (None,'NA',''):raise ValueError('MultiQC replaced unavailable Picard RNA evidence')
            else:
                try:
                    expected_value=Decimal(original)*(100 if key.startswith('PCT_') else 1)
                    actual_value=Decimal(str(observed.get(key)))
                    # MultiQC's percent conversion uses binary floating point;
                    # this bound covers JSON round-off only, not scientific rounding.
                    tolerance=Decimal('1e-10') if key.startswith('PCT_') else Decimal(0)
                    if not actual_value.is_finite() or abs(actual_value-expected_value)>tolerance:
                        raise ValueError('MultiQC Picard RNA '+key+' differs from original report')
                except InvalidOperation as exc:raise ValueError('Missing MultiQC Picard RNA value') from exc
    available = {names[p]:d['histogram']['rows'] for p,d in expected.items() if d['coverage_available']}
    missing = {names[p] for p,d in expected.items() if not d['coverage_available']}
    plot=value.get('report_plot_data',{}).get('picard_rna_coverage',{})
    datasets=plot.get('datasets',[])
    lines=datasets[0].get('lines',[]) if len(datasets)==1 else []
    seen=set()
    for line in lines:
        name=line.get('name');pairs=line.get('pairs')
        if name in seen or name not in set(available)|missing:raise ValueError('Unknown/duplicate MultiQC RNA coverage sample')
        seen.add(name)
        if name in missing:
            if pairs!=[]:raise ValueError('Unavailable RNA coverage became a curve')
        else:
            try:
                if len(pairs)!=101 or any(len(pair)!=2 or Decimal(str(pair[0]))!=Decimal(original[0]) or Decimal(str(pair[1]))!=Decimal(original[1]) for pair,original in zip(pairs,available[name])):
                    raise ValueError('MultiQC RNA coverage points differ from original')
            except (InvalidOperation,TypeError) as exc:raise ValueError('Malformed MultiQC RNA coverage') from exc
    if not set(available)<=seen:raise ValueError('Missing available MultiQC RNA coverage profile')
