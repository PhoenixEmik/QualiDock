"""Optional read-only QC adapters; called inside RunManager's existing slot."""
import asyncio
import json
import math
from pathlib import Path

from .integrity import snapshot
from .outcomes import stop
from .processing import local_file, validate
from .metrics import bounded_text
from .store import now, save_json
from . import coverage, alignment, fastq_screen, multiqc, nanoplot, rseqc, picard, picard_rna

MODES = {'nanoq', 'fastq-screen', 'nanoplot', *alignment.MODES}


def options(mode, supplied):
    if mode == 'picard-rna':
        return picard_rna.Options.model_validate(supplied or {}).model_dump()
    if mode == 'picard':
        value = picard.Options.model_validate(supplied or {}).model_dump()
        if value['by_library'] and value['multiqc']:
            raise ValueError('MultiQC insert-size aggregation is unsupported for per-library reports: upstream combines overlapping populations. Original per-library reports remain available without MultiQC.')
        return value
    if mode in rseqc.MODES:
        model = rseqc.GeneBodyOptions if mode == 'rseqc-genebody' else rseqc.InferOptions if mode == 'rseqc-infer' else rseqc.Options
        value = model.model_validate(supplied or {}).model_dump()
        return value
    if mode == 'mosdepth':
        return coverage.Options.model_validate(supplied or {}).model_dump()
    if mode == 'samtools':
        return alignment.Options.model_validate(supplied or {}).model_dump()
    if mode == 'nanoplot':
        return nanoplot.Options.model_validate(supplied or {}).model_dump()
    if mode == 'fastq-screen':
        return fastq_screen.Options.model_validate(supplied or {}).model_dump()
    if supplied:
        raise ValueError('QC options require FastQ Screen; nanoq is report-only without filtering or fast mode')
    return {}


def required(mode, value):
    if mode in {'picard','picard-rna'}:
        return ['samtools','java','picard', *(['multiqc'] if value['multiqc'] else [])]
    if mode in rseqc.MODES:
        return ['samtools', rseqc.TOOLS[mode], *(['multiqc'] if value['multiqc'] else [])]
    if mode == 'mosdepth':
        return ['samtools', 'mosdepth']
    if mode == 'samtools':
        return ['samtools', *(['multiqc'] if value['multiqc'] else [])]
    if mode == 'nanoplot':
        return ['nanoplot']
    return ['nanoq'] if mode == 'nanoq' else ['fastq_screen', 'bowtie2', *(['multiqc'] if value['multiqc'] else [])]


def parse_nanoq(path):
    """Verified 0.10.0 JSON, without recalculating reported scientific metrics."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError('nanoq report must be a regular JSON file of at most 1 MiB')
    with path.open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('nanoq report exceeds 1 MiB')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate nanoq JSON field')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError('Expected a nanoq JSON object')
    integers = ('reads', 'bases', 'n50', 'longest', 'shortest', 'mean_length', 'median_length', 'filtered')
    for key in integers:
        if type(value.get(key)) is not int or value[key] < 0:
            raise ValueError(f'Invalid nanoq {key}')
    if not value['reads'] or not value['bases'] or value['filtered']:
        raise ValueError('Empty or filtered nanoq data is not read-only QC evidence')
    for key in ('mean_quality', 'median_quality'):
        number = value.get(key)
        if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 93:
            raise ValueError(f'Unavailable or invalid nanoq {key}; fast/no-quality mode is unsupported')
    for key in ('length_thresholds', 'quality_thresholds'):
        table = value.get(key)
        if not isinstance(table, dict) or not table or any(not k.isdecimal() or type(v) is not int or not 0 <= v <= value['reads'] for k, v in table.items()):
            raise ValueError(f'Invalid nanoq {key}')
    for key in ('n50', 'mean_length', 'median_length'):
        if not value['shortest'] <= value[key] <= value['longest']:
            raise ValueError('Inconsistent nanoq length statistics')
    return value


def records(paths, tool):
    from .outcomes import plan
    result = []
    for row in plan(paths):
        filename = {'rseqc-genebody':row['id']+'.geneBodyCoverage.txt', 'picard':row['id']+'.insert_size_metrics.txt', 'picard-rna':row['id']+'.rna_metrics.txt', 'rseqc-infer':row['id']+'.infer_experiment.txt', 'rseqc-distribution':row['id']+'.read_distribution.txt',
                    'samtools':row['id']+'.stats.txt', 'mosdepth':row['id']+'.mosdepth.summary.txt',
                    'fastq-screen':row['id']+'_screen.txt', 'nanoplot':'NanoStats.txt', 'nanoq':'nanoq.json'}[tool]
        result.append({**{key:row[key] for key in ('id','path','name','state','error','exit_code','finished_at')},
                       'report':f'qc/{row["id"]}/{filename}', 'summary':None})
    return result


async def execute(manager, run, metrics, errors):
    if run['mode'] in alignment.MODES:
        return await alignment.execute(manager, run, metrics, errors)
    directory = manager.directory(run['id'])
    paths = await asyncio.to_thread(manager.checked_inputs, run)
    manager.update(run, stage='Validating FASTQ inputs')
    checked = await validate(manager, run, paths, [], 'source', namespace='qc/private', four_line=run['mode'] == 'fastq-screen')
    if run['id'] in manager.cancelled:
        return
    validated = {row['path']: row for row in checked['files']}
    for row in run['qc']['results']:
        if run['id'] in manager.cancelled:
            break
        try:
            source = validated[row['path']]
            if source['state'] != 'passed' or not source['records_scanned']:
                raise ValueError(source.get('error') or 'Empty or incompletely validated FASTQ')
            # Recheck authorization and queued identity after the validation scan.
            await asyncio.to_thread(manager.checked_inputs, run)
            row['state'] = 'running'
            manager.update(run, stage=f'{run["qc"]["tool"]} · {row["name"]}')
            summary, screen, plots = None, None, None
            if run['mode'] == 'nanoplot':
                plots = await nanoplot.execute(manager, run, row, source)
                if run['id'] in manager.cancelled:
                    break
            elif run['mode'] == 'fastq-screen':
                screen = await fastq_screen.execute(manager, run, row, source)
                if run['id'] in manager.cancelled:
                    break
            else:
                manager.stores.subdirectory(run['id'], f'qc/{row["id"]}', exist_ok=True)
                argv = [run['tools']['nanoq']['executable'], '--stats', '--json', '--report',
                        str(directory / row['report']), '--input', row['path']]
                code = await manager.command(run, 'nanoq', argv, directory)
                if run['id'] in manager.cancelled:
                    break
                row['exit_code'] = code
                if code:
                    raise ValueError(f'nanoq exited with code {code}; see analysis log')
                summary = await asyncio.to_thread(parse_nanoq, local_file(directory, row['report']))
                if (summary['reads'], summary['bases'], summary['shortest'], summary['longest']) != (
                        source['records_scanned'], source['bases_scanned'], source['min_length'], source['max_length']):
                    raise ValueError('nanoq counts or length range differ from validated source records')
            if snapshot(Path(row['path']).stat()) != source['source_snapshot']:
                raise ValueError('Source changed during QC')
            await asyncio.to_thread(manager.checked_inputs, run)
            row.update(state='completed', summary=summary, source_sha256=source['sha256'], error=None)
            if screen is not None:
                row['screen'] = screen
            if plots is not None:
                row['nanoplot'] = plots
            run['report_input_map'][row['report']] = {'id': row['id'], 'path': row['path']}
        except (ValueError, OSError, KeyError, TypeError) as exc:
            row.update(state='failed', summary=None, error=str(exc))
            errors.append(f'{row["name"]}: {exc}')
        row['finished_at'] = now()
        manager.update(run, sample_count=sum(r['state'] == 'completed' for r in run['qc']['results']))
    metrics['qc'] = run['qc']
    if run['id'] not in manager.cancelled and run['qc']['options'].get('multiqc'):
        reports = [directory/row['report'] for row in run['qc']['results'] if row['state'] == 'completed']
        if reports:
            manager.update(run, stage='MultiQC · FastQ Screen')
            problem = await multiqc.execute(manager, run, reports)
            if problem:
                errors.append(problem)
            elif run['id'] not in manager.cancelled:
                metrics['multiqc'] = await multiqc.summary(directory)
                # FastQ Screen contributes its own plot/raw data, not General
                # Statistics. Verify genuine module samples rather than invent GS.
                structured = directory/'multiqc/multiqc_data/multiqc_data.json'
                data = json.loads(await asyncio.to_thread(bounded_text, structured))
                names = data.get('report_saved_raw_data', {}).get('multiqc_fastq_screen', {})
                if not isinstance(names, dict) or len(names) != len(reports):
                    errors.append('MultiQC FastQ Screen module samples unavailable; original reports remain available')
                else:
                    for report, name in (await multiqc.report_names(directory, reports, sample_names=names)).items():
                        if name is None:
                            errors.append(f'No unique MultiQC source mapping for {report}')
                        else:
                            run['report_input_map'][report]['multiqc_name'] = name
    await asyncio.to_thread(save_json, directory / 'metrics.json', metrics)


def stopped(run):
    stop(run.get('qc', {}).get('results', []), run['state'] if run['state'] in {'cancelled', 'interrupted'} else 'failed',
         'QC stopped before a verified result was recorded')
