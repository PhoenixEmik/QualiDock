"""Small tool adapters inside RunManager's lifecycle. Never an independent executor."""
from __future__ import annotations
import asyncio
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import sys
from pydantic import BaseModel, ConfigDict, Field
from .integrity import snapshot
from .files import PathViolation
from .metrics import bounded_text, parse_multiqc
from .import_formats import fastp_metadata, source_mappings
from .outcomes import plan

MODES = {'fastp', 'seqkit-stats', 'seqkit-sample', 'seqkit-filter', 'seqkit-extract'}


class FastpOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    adapter_trimming: bool = True
    quality_filtering: bool = True
    qualified_quality: int = Field(default=15, ge=0, le=93)
    unqualified_percent: int = Field(default=40, ge=0, le=100)
    min_length: int = Field(default=15, ge=1, le=1000000)
    gzip: bool = True
    compare_qc: bool = True
    multiqc: bool = False


class SeqkitOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    gzip: bool = True
    preserve_pairs: bool = False
    count: int | None = Field(default=None, ge=1, le=9007199254740991)
    fraction: float = Field(default=0.1, gt=0, le=1, allow_inf_nan=False)
    seed: int = Field(default=11, ge=0, le=2147483647)
    min_length: int = Field(default=15, ge=1, le=1000000)
    max_length: int | None = Field(default=None, ge=1, le=1000000)
    identifiers: list[str] = Field(default_factory=list, max_length=10000)


def options(mode, supplied):
    if mode not in MODES:
        if supplied: raise ValueError('Processing options require a processing operation')
        return None
    value = (FastpOptions if mode == 'fastp' else SeqkitOptions).model_validate(supplied or {}).model_dump()
    if mode.startswith('seqkit-'):
        if mode != 'seqkit-sample' and value['count'] is not None:
            raise ValueError('An exact count requires the sampling operation')
        if value['max_length'] is not None and value['max_length'] < value['min_length']:
            raise ValueError('Maximum length must be at least minimum length')
        if mode == 'seqkit-extract' and not value['identifiers']:
            raise ValueError('Enter at least one exact read identifier')
        if any(not identifier or len(identifier) > 1024 or any(c.isspace() or ord(c) < 32 for c in identifier) for identifier in value['identifiers']):
            raise ValueError('Read identifiers must be exact non-empty first tokens, without whitespace')
        value['identifiers'] = list(dict.fromkeys(value['identifiers']))
    return value


def required(mode, value, operation_units=None):
    if mode == 'fastp':
        return ['fastp', *(['fastqc'] if value['compare_qc'] else []), *(['multiqc'] if value['multiqc'] else [])]
    if mode in {'seqkit-filter', 'seqkit-extract'} and value.get('preserve_pairs') and operation_units and all(len(unit['inputs']) == 2 for unit in operation_units):
        return []
    return ['seqkit']


def check_features(mode, value, tools):
    if mode == 'seqkit-sample' and value.get('count') is not None:
        version = tuple(int(part) for part in (tools.get('seqkit', {}).get('version') or '0').split('.'))
        if version < (2, 14):
            raise ValueError('Exact-count sampling requires verified SeqKit 2.14 or newer (sample2 --two-pass); fraction sampling remains available')


def units(run, value=None):
    """Use persisted mutual pairs; lanes are never merged. Only fastp and validated fraction sampling preserve pairs."""
    value = value or run.get('processing', {}).get('options', {})
    relationships = {row['path']: row for row in run.get('input_pairing', [])}
    result, seen = [], set()
    for path in run['inputs']:
        if path in seen: continue
        member = relationships.get(path, {})
        paths = [path]
        if (run['mode'] in {'fastp', 'seqkit-sample'} or run['mode'] in {'seqkit-filter', 'seqkit-extract'} and value.get('preserve_pairs')) and member.get('paired'):
            mate = relationships.get(member.get('mate'), {})
            if mate.get('mate') != path or mate.get('read') == member.get('read'):
                raise ValueError('Conflicting paired-end metadata')
            paths = [path, member['mate']] if member['read'] == 'R1' else [member['mate'], path]
        seen.update(paths)
        result.append({'id': f'u{len(result) + 1:04}', 'inputs': paths, 'state': 'queued',
                       'lane': member.get('lane'), 'chunk': member.get('chunk'), 'error': None,
                       'outputs': [], 'fastp': None})
    return result


def stage_records(paths, unit_id, stage):
    """Retain the existing FastQC collision namespaces inside each processing stage."""
    records = plan(paths)
    for record in records:
        namespace = Path('fastqc') / unit_id / stage / Path(record['output_directory']).relative_to('fastqc')
        record['output_directory'] = str(namespace)
        for key in ('report', 'html'):
            record[key] = str(namespace / Path(record[key]).name)
    return records


def local_file(directory, relative):
    path = directory / relative
    if path.resolve(strict=True) != path or not path.is_relative_to(directory) or not path.is_file():
        raise PathViolation('Processing artifact is missing or contains a symlink')
    return path


async def validate(manager, run, files, pairs, name):
    """Reuse the bounded scanner in a cancellable, resource-governed subprocess."""
    from .store import save_json
    directory = manager.directory(run['id'])
    private = manager.stores.subdirectory(run['id'], 'processing/private', exist_ok=True)
    config, output = private / f'{name}-config.json', private / f'{name}-validation.json'
    entries = [{'id': f'f{index}', 'path': str(path), 'snapshot': snapshot(path.stat())} for index, path in enumerate(files)]
    await asyncio.to_thread(save_json, config, {'mode': 'full', 'quick_reads': 10000, 'files': entries, 'pairs': pairs})
    code = await manager.command(run, 'FASTQ validation', [sys.executable, '-m', 'qualidock.integrity_worker', '--config', str(config), '--output', str(output)], directory)
    if run['id'] in manager.cancelled: return None
    if code: raise ValueError('FASTQ validation failed; see analysis log')
    return json.loads(bounded_text(local_file(directory, str(output.relative_to(directory)))))


def fastp_command(executable, inputs, outputs, destination, threads, value):
    argv = [executable, '--in1', str(inputs[0]), '--out1', str(outputs[0]), '--thread', str(threads),
            '--json', str(destination / 'fastp.json'), '--html', str(destination / 'fastp.html'),
            '--length_required', str(value['min_length']), '--qualified_quality_phred', str(value['qualified_quality']),
            '--unqualified_percent_limit', str(value['unqualified_percent']), '--n_base_limit', '5', '--dont_eval_duplication', '--disable_trim_poly_g', '--dont_overwrite']
    if len(inputs) == 2:
        argv += ['--in2', str(inputs[1]), '--out2', str(outputs[1])]
        if value['adapter_trimming']: argv += ['--detect_adapter_for_pe']
    if not value['adapter_trimming']: argv += ['--disable_adapter_trimming']
    if not value['quality_filtering']: argv += ['--disable_quality_filtering']
    return argv


def seqkit_command(executable, mode, source, output, threads, value, ids):
    exact = mode == 'seqkit-sample' and value.get('count') is not None
    command = 'sample2' if exact else mode.removeprefix('seqkit-').replace('filter', 'seq').replace('extract', 'grep')
    argv = [executable, command, '--threads', str(threads)]
    if mode == 'seqkit-stats': argv += ['--tabular']
    elif mode == 'seqkit-sample':
        argv += (['--number', str(value['count']), '--two-pass'] if exact else ['--proportion', str(value['fraction'])]) + ['--rand-seed', str(value['seed'])]
    elif mode == 'seqkit-filter':
        argv += ['--min-len', str(value['min_length'])]
        if value['max_length'] is not None: argv += ['--max-len', str(value['max_length'])]
    elif mode == 'seqkit-extract': argv += ['--pattern-file', str(ids)]
    return [*argv, '--out-file', str(output), str(source)]


async def execute(manager, run, metrics, errors):
    """Called only while RunManager holds its existing shared resource slot."""
    from .store import save_json
    directory = manager.directory(run['id'])
    value = run['processing']['options']
    paths = await asyncio.to_thread(manager.checked_inputs, run)
    pair_rows = [{'id': row['pair_key'], 'r1': row['path'], 'r2': row['mate']} for row in run['input_pairing'] if row.get('paired') and row['read'] == 'R1'] if any(len(unit['inputs']) == 2 for unit in run['processing']['units']) else []
    manager.update(run, stage='Validating source FASTQs')
    validation = await validate(manager, run, paths, pair_rows, 'source')
    if validation is None: return
    run['processing']['input_validation'] = validation
    valid = {row['path']: row for row in validation['files']}
    failed_pairs = {row['r1']: row['error'] for row in validation['pairs'] if row['state'] != 'passed'}
    pending = []
    for unit in run['processing']['units']:
        if run['id'] in manager.cancelled: return
        try:
            if any(valid[path]['state'] != 'passed' for path in unit['inputs']):
                raise ValueError('Input FASTQ validation failed: ' + '; '.join(valid[path]['error'] or 'Incomplete scan' for path in unit['inputs'] if valid[path]['state'] != 'passed'))
            if run['mode'] == 'seqkit-sample' and value.get('count') is not None and value['count'] > valid[unit['inputs'][0]]['records_scanned']:
                kind = 'read pairs' if len(unit['inputs']) == 2 else 'reads'
                raise ValueError(f"Requested {value['count']} {kind}; only {valid[unit['inputs'][0]]['records_scanned']} are available. No clamping or replacement is performed.")
            if unit['inputs'][0] in failed_pairs: raise ValueError(failed_pairs[unit['inputs'][0]])
            await asyncio.to_thread(manager.checked_inputs, run)
            unit.update(state='running')
            manager.update(run, stage=f"{run['mode']} · {unit['id']}")
            destination = manager.stores.subdirectory(run['id'], 'processing/' + unit['id'])
            source = [Path(path) for path in unit['inputs']]
            raw_records = []
            if run['mode'] == 'fastp' and value['compare_qc']:
                raw_records = stage_records(source, unit['id'], 'raw')
                unit['raw_qc'] = raw_records
                await manager.fastqc_results(run, raw_records, metrics, errors, 'raw')
            if run['id'] in manager.cancelled: return
            suffix = '.fastq.gz' if value['gzip'] else '.fastq'
            outputs = [destination / ((f'processed_R{index+1}' if len(source) == 2 else 'processed') + suffix) for index in range(len(source))]
            if run['mode'] == 'seqkit-stats': outputs = [destination / 'stats.tsv']
            ids = manager.stores.subdirectory(run['id'], 'processing/private', exist_ok=True) / 'identifiers.txt'
            if run['mode'] == 'seqkit-extract': ids.write_text('\n'.join(value['identifiers']) + '\n')
            tool = 'fastp' if run['mode'] == 'fastp' else 'seqkit'
            synchronized = run['mode'] in {'seqkit-filter', 'seqkit-extract'} and len(source) == 2
            if synchronized:
                config = ids.parent / (unit['id'] + '-selection-config.json')
                result = destination / 'selection.json'
                save_json(config, {'inputs': list(map(str, source)), 'outputs': list(map(str, outputs)),
                                   'snapshots': [valid[str(path)]['source_snapshot'] for path in source],
                                   'min_length': value['min_length'], 'max_length': value['max_length'],
                                   'gzip': value['gzip'], 'result': str(result), 'operation': 'identifiers' if run['mode'] == 'seqkit-extract' else 'length', 'identifiers': value['identifiers']})
                commands = [[sys.executable, '-m', 'qualidock.paired_reads', '--config', str(config)]]
                tool = 'QualiDock synchronized FASTQ selector'
            else:
                commands = [fastp_command(run['tools'][tool]['executable'], source, outputs, destination, run['threads'], value)] if tool == 'fastp' else [seqkit_command(run['tools'][tool]['executable'], run['mode'], path, output, run['threads'], value, ids) for path, output in zip(source, outputs)]
            for argv in commands:
                code = await manager.command(run, tool, argv, directory)
                if run['id'] in manager.cancelled: return
                if code:
                    detail = json.loads(bounded_text(local_file(directory, str(result.relative_to(directory))))).get('error') if synchronized and result.exists() else None
                    raise ValueError(detail or f'{tool} exited with code {code}; see analysis log')
            if synchronized:
                unit['selection'] = json.loads(bounded_text(local_file(directory, str(result.relative_to(directory)))))
                if unit['selection'].get('missing_identifiers'):
                    run['warnings'].append(f"{unit['id']}: {len(unit['selection']['missing_identifiers'])} requested identifiers not found; see selection.json")
                if unit['selection']['input_records'] != valid[unit['inputs'][0]]['records_scanned']:
                    raise ValueError('Selection input count differs from validated sources')
            await asyncio.to_thread(manager.checked_inputs, run)
            for path in outputs: local_file(directory, str(path.relative_to(directory)))
            if tool == 'fastp':
                report = local_file(directory, str((destination / 'fastp.json').relative_to(directory)))
                await asyncio.to_thread(fastp_metadata, report)
                details = json.loads(bounded_text(report))
                unit['fastp'] = {key: details.get(key) for key in ('summary', 'filtering_result', 'adapter_cutting', 'read1_before_filtering', 'read2_before_filtering', 'read1_after_filtering', 'read2_after_filtering')}
                if any(sum(valid[path][scanned] for path in unit['inputs']) != details['summary']['before_filtering'][reported] for scanned, reported in [('records_scanned','total_reads'),('bases_scanned','total_bases')]):
                    raise ValueError('fastp input read/base totals differ from validated source records')
            if run['mode'] != 'seqkit-stats':
                pairs = [{'id': unit['id'], 'r1': str(outputs[0]), 'r2': str(outputs[1])}] if len(outputs) == 2 else []
                checked = await validate(manager, run, outputs, pairs, unit['id'])
                if checked is None: return
                if checked['result'] != 'passed': raise ValueError('Derived FASTQ validation failed; outputs are not published')
                unit['output_validation'] = checked
                if run['mode'] == 'seqkit-sample' and value.get('count') is not None:
                    if any(row['records_scanned'] != value['count'] for row in checked['files']):
                        raise ValueError('SeqKit output does not contain the exact requested count')
                    observed = checked['files'][0]['records_scanned']
                    unit['selection'] = {'processor': 'SeqKit sample2 --two-pass', 'version': run['tools']['seqkit']['version'],
                                         'operation': 'exact-count', 'record_unit': 'read_pairs' if len(outputs) == 2 else 'reads',
                                         'input_records': valid[unit['inputs'][0]]['records_scanned'], 'retained_records': observed,
                                         'removed_records': valid[unit['inputs'][0]]['records_scanned']-observed, 'seed': value['seed']}
                    save_json(destination / 'selection.json', unit['selection'])
                if synchronized and any(row['records_scanned'] != unit['selection']['retained_records'] for row in checked['files']):
                    raise ValueError('Selection output counts differ from validated records')
                if tool == 'fastp' and any(sum(row[scanned] for row in checked['files']) != unit['fastp']['summary']['after_filtering'][reported] for scanned, reported in [('records_scanned','total_reads'),('bases_scanned','total_bases')]):
                    raise ValueError('fastp output read/base totals differ from validated derived records')
                for index, path in enumerate(outputs):
                    pending.append({'id': unit['id'] + f':{index+1}', 'unit_id': unit['id'], 'path': str(path.relative_to(directory)),
                                    'source': unit['inputs'][index], 'stage': 'processed', 'paired': len(outputs) == 2,
                                    'read': f'R{index+1}' if len(outputs) == 2 else None,
                                    'snapshot': snapshot(path.stat()), 'sha256': checked['files'][index]['sha256'],
                                    'records': checked['files'][index]['records_scanned'], 'bases': checked['files'][index]['bases_scanned']})
                if tool == 'fastp' and value['compare_qc']:
                    records = stage_records(outputs, unit['id'], 'processed')
                    unit['processed_qc'] = records
                    await manager.fastqc_results(run, records, metrics, errors, 'processed')
            else:
                unit['statistics'] = list(csv.DictReader(io.StringIO(bounded_text(outputs[0])), delimiter='\t'))
                if len(unit['statistics']) != 1: raise ValueError('SeqKit statistics did not contain exactly one input row')
            for entry in pending:
                if entry['unit_id'] == unit['id'] and snapshot(local_file(directory, entry['path']).stat()) != entry['snapshot']:
                    raise ValueError('Derived FASTQ changed during QC; outputs are not published')
            unit.update(state='completed', outputs=[str(path.relative_to(directory)) for path in outputs])
        except (ValueError, OSError, KeyError, TypeError) as exc:
            unit.update(state='failed', error=str(exc))
            errors.append(f"{unit['id']}: {exc}")
        manager.update(run)
    if run['id'] in manager.cancelled: return
    # Successful processing survives optional QC/report failures; unfinished FASTQs never publish.
    completed = {unit['id'] for unit in run['processing']['units'] if unit['state'] == 'completed'}
    manager.update(run, derived_datasets=[entry for entry in pending if entry['unit_id'] in completed], sample_count=len(metrics['samples']))
    if run['mode'] == 'fastp' and value['multiqc'] and completed:
        manager.stores.subdirectory(run['id'], 'multiqc', exist_ok=True)
        manager.update(run, stage='MultiQC · raw / processed / fastp')
        reports = [directory / record['report'] for unit in run['processing']['units'] if unit['id'] in completed for stage in ('raw_qc','processed_qc') for record in unit.get(stage,[]) if record['state'] == 'completed']
        reports += [directory / 'processing' / identity / 'fastp.json' for identity in sorted(completed)]
        file_list, config = directory / 'multiqc-inputs.txt', directory / 'multiqc-processing-config.json'
        if any('\n' in str(path) or '\r' in str(path) for path in reports): raise ValueError('MultiQC report paths cannot contain newlines')
        file_list.write_text(''.join(str(path)+'\n' for path in reports))
        save_json(config, {'use_filename_as_sample_name': ['fastp']})
        code = await manager.command(run, 'multiqc', [run['tools']['multiqc']['executable'], '--file-list', str(file_list), '--outdir', str(directory/'multiqc'), '--force', '--data-format','json','--no-version-check','--dirs','--dirs-depth','3','--fullnames','--config',str(config)], directory)
        if run['id'] in manager.cancelled: return
        if code or not (directory/'multiqc/multiqc_report.html').is_file(): errors.append(f'MultiQC failed (exit {code}); successful processing is preserved')
        else:
            try:
                structured = directory/'multiqc/multiqc_data/multiqc_data.json'
                metrics['multiqc'] = await asyncio.to_thread(parse_multiqc, structured)
                mapping = await asyncio.to_thread(source_mappings, structured)
                actual = {row['sample'] for row in metrics['multiqc']['rows']}
                for path in reports:
                    names = mapping.get(str(path), set()) & actual
                    report_id = str(path.relative_to(directory))
                    if len(names) == 1:
                        row = run['report_input_map'].setdefault(report_id, {'id': report_id, 'source_report': str(path)})
                        row['multiqc_name'] = next(iter(names))
                    else:
                        run['warnings'].append(f'No unique MultiQC source mapping for {report_id}; inspect the original report')
            except (ValueError,OSError): errors.append('MultiQC structured output unavailable; original report is preserved')
    metrics['processing'] = deepcopy(run['processing'])
    await asyncio.to_thread(save_json, directory/'metrics.json', metrics)
