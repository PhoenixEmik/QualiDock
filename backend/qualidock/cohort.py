"""Read-only, provenance-aware projections of existing QC/validation evidence.

No QC execution, FASTQ processing, biological inference or replacement QC model.
"""
from collections import defaultdict, OrderedDict
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

from .catalog import CatalogConflict
from .delivery import integer, sum_known
from .metrics import bounded_text
from .release_policy import digest

METRICS = {
    'reads': {'name': 'Read records', 'unit': 'reads', 'description': 'R1 and R2 are separate read records; not read pairs.'},
    'bases': {'name': 'Sequenced bases', 'unit': 'bases', 'description': 'Full source counts, or explicitly reported fixed length × read records. Rounded kbp/Mbp labels are never expanded.'},
    'q20_percent': {'name': 'Q20 bases', 'unit': '%', 'description': '100 × Q20 base count / quality base count from complete current validation with known encoding.'},
    'q30_percent': {'name': 'Q30 bases', 'unit': '%', 'description': '100 × Q30 base count / quality base count from complete current validation with known encoding.'},
    'length_min': {'name': 'Minimum read length', 'unit': 'bp', 'description': 'Minimum of the observed/reported file length range; not a mean.'},
    'length_max': {'name': 'Maximum read length', 'unit': 'bp', 'description': 'Maximum of the observed/reported file length range; not a mean.'},
    'gc_percent': {'name': 'GC content (FastQC reported)', 'unit': '%', 'description': 'Original Basic Statistics %GC, at FastQC reported precision; protocol context matters.'},
    'deduplicated_percent': {'name': 'Estimated deduplicated fraction (FastQC reported)', 'unit': '%', 'description': 'Original Total Deduplicated Percentage; no new duplicate-rate calculation.'},
    'adapter_bin_percent': {'name': 'Adapter content at reported bin', 'unit': '%', 'description': 'Exact reported adapter category and position bin. Not a newly inferred global adapter rate. Without a saved configuration identity, cross-analysis definitions remain unverified.'},
}
MAX_REFERENCES = 5000
MAX_FILES = 2000


def finite(value):
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def length_range(value):
    match = re.fullmatch(r'(\d+)(?:-(\d+))?', value or '')
    if not match:
        return None
    lower, upper = int(match[1]), int(match[2] or match[1])
    return (lower, upper) if 0 <= lower <= upper <= 2**53 - 1 else None


def module(sample, name):
    return next((entry for entry in sample.get('modules', []) if entry['name'].lower() == name.lower() and entry.get('available', True)), None)


def reported_metric(file, run, sample, metric, adapter=None, position=None):
    """Return a scalar projection plus exact raw source; unavailable is never zero."""
    descriptor = METRICS[metric]
    result = {'metric': metric, 'unit': descriptor['unit'], 'value': None, 'raw_value': None,
              'numerator': None, 'denominator': None, 'definition': None, 'reason': None}
    full = file.get('integrity_state') == 'passed' and bool(file.get('sha256'))
    fastqc = sample.get('fastqc_version') or run.get('tools', {}).get('fastqc', {}).get('version')
    validator = run.get('integrity', {}).get('version')
    definition = {'metric': metric, 'unit': descriptor['unit'], 'calculator': None, 'version': None}
    value = None
    if metric in {'q20_percent', 'q30_percent'}:
        numerator = integer(file.get('q20_bases' if metric == 'q20_percent' else 'q30_bases'))
        denominator = integer(file.get('quality_bases'))
        if not full or not validator or not file.get('encoding_source') or numerator is None or not denominator or numerator > denominator:
            result['reason'] = 'Complete current validation with known quality encoding and nonzero quality-base denominator is required'
            return result
        value = 100 * numerator / denominator
        result.update(numerator=numerator, denominator=denominator, raw_value=f'{numerator}/{denominator}')
        definition.update(calculator='QualiDock FASTQ integrity', version=validator, encoding=file['encoding_source'], encoding_report_fastqc_version=fastqc)
    elif metric in {'reads', 'bases'}:
        value = integer(file.get(metric))
        if value is None:
            result['reason'] = 'Exact read/base count unavailable; variable lengths and rounded kbp/Mbp labels are not extrapolated'
            return result
        result['raw_value'] = str(value)
        definition.update(calculator='QualiDock FASTQ integrity' if full else 'FastQC reported counts', version=validator if full else fastqc,
                          basis=file.get('counts_source'))
    elif metric in {'length_min', 'length_max'}:
        interval = length_range(file.get('sequence_length'))
        if interval is None:
            result['reason'] = 'No exact observed/reported file length range'
            return result
        value = interval[0 if metric == 'length_min' else 1]
        result['raw_value'] = file['sequence_length']
        definition.update(calculator='QualiDock FASTQ integrity' if full else 'FastQC Basic Statistics', version=validator if full else fastqc,
                          basis='Observed min/max' if full else 'Reported file length range')
    else:
        if not file.get('qc_snapshot_matches') or not sample:
            result['reason'] = 'Matching current FastQC report/source evidence is unavailable'
            return result
        raw = None
        definition.update(calculator='FastQC', version=fastqc)
        if metric == 'gc_percent':
            raw = sample.get('basic_statistics', {}).get('%GC')
        elif metric == 'deduplicated_percent':
            table = module(sample, 'Sequence Duplication Levels')
            rows = [row for row in (table or {}).get('metadata', []) if len(row) == 2 and row[0].lstrip('#').strip() == 'Total Deduplicated Percentage']
            raw = rows[0][1] if len(rows) == 1 else None
        elif metric == 'adapter_bin_percent':
            table = module(sample, 'Adapter Content')
            if not adapter or not position:
                result['reason'] = 'Select an exact saved adapter category and original position bin'
                return result
            columns = (table or {}).get('columns', [])
            rows = [row for row in (table or {}).get('rows', []) if row and row[0] == position]
            if columns.count(adapter) == 1 and len(rows) == 1 and len(rows[0]) > columns.index(adapter):
                raw = rows[0][columns.index(adapter)]
            definition.update(adapter=adapter, position=position)
            config = run.get('tools', {}).get('fastqc', {}).get('adapter_config_sha256')
            definition['adapter_definition'] = config or 'unverified-across-analyses:' + run['id']
            if not config:
                result['definition_note'] = 'Adapter configuration identity was not recorded. Compatible overlays are restricted to this source analysis; no cross-analysis adapter definition is inferred.'
        number = finite(raw)
        if number is None or not 0 <= number <= 100:
            result['reason'] = 'Requested original FastQC value/category/bin is missing or unsupported'
            return result
        value = float(number)
        result['raw_value'] = raw
    if not definition.get('version'):
        result['reason'] = 'Metric calculator version is unavailable'
        return result
    result.update(value=value, definition=definition)
    return result


def declared_rule(value, metric):
    if value is None:
        return None
    if metric != 'q30_percent' or not isinstance(value, dict) or set(value) != {'minimum_percent'}:
        raise ValueError('Only an explicit minimum Q30 percentage review rule is supported')
    raw = value['minimum_percent']
    threshold = finite(raw)
    if threshold is None or not 0 <= threshold <= 100 or len(str(raw)) > 32:
        raise ValueError('Q30 minimum must be a finite percentage from 0 to 100')
    return {'version': 'declared-q30-minimum-v1', 'metric': metric, 'operator': '<', 'minimum_percent': str(raw),
            'meaning': 'Review signal against a user-declared reference; not FastQC status or definitive assay/sample failure'}


def flag(point, rule):
    if rule is None or point.get('reason') or point.get('value') is None:
        return None
    # Compare the exact saved counts, not a rounded display percentage.
    return 'review' if Decimal(point['numerator']) * 100 < Decimal(rule['minimum_percent']) * point['denominator'] else 'within_declared_reference'


class CohortComparisons:
    def __init__(self, manager):
        self.manager = manager
        self.catalog = manager.catalog

    def bindings(self, project_ids, sample_ids=None, sequencing_run_ids=None):
        with self.catalog.transaction() as db:
            projects = {value: self.catalog.entity(db, value, 'project') for value in project_ids}
            for ids, kind in [(sample_ids, 'sample'), (sequencing_run_ids, 'sequencing_run')]:
                for value in ids or []:
                    entity = self.catalog.entity(db, value, kind)
                    if entity['project_id'] not in projects:
                        raise ValueError('A selected identity does not belong to the selected projects')
            where = 'a.project_id IN (' + ','.join('?' for _ in project_ids) + ')'
            args = list(project_ids)
            for column, ids in [('sample_id', sample_ids), ('sequencing_run_id', sequencing_run_ids)]:
                if ids is not None:
                    if not ids:
                        raise ValueError('Empty explicit selection is not All scope')
                    where += ' AND a.' + column + ' IN (' + ','.join('?' for _ in ids) + ')'
                    args.extend(ids)
            rows = [dict(row) for row in db.execute('SELECT a.*,l.analysis_id FROM associations a JOIN analysis_links l ON l.id=a.analysis_link_id WHERE ' + where + ' ORDER BY a.id LIMIT ?', [*args, MAX_REFERENCES + 1])]
            if len(rows) > MAX_REFERENCES:
                raise ValueError('Narrow the cohort to at most 5000 evidence references')
            entities = {value: self.catalog.entity(db, value) for row in rows for value in (row['sample_id'], row['sequencing_run_id'])}
        return projects, entities, rows

    def prepare(self, project_ids, metric='q30_percent', sample_ids=None, sequencing_run_ids=None, filters=None, rule=None, group_by='file', adapter=None, position=None):
        if not isinstance(project_ids, list) or not 1 <= len(project_ids) <= 5 or len(set(project_ids)) != len(project_ids):
            raise ValueError('Select 1–5 distinct projects')
        if metric not in METRICS or group_by not in {'file', 'run'}:
            raise ValueError('Choose a supported metric and grouping')
        if group_by == 'run' and metric not in {'reads', 'bases', 'q20_percent', 'q30_percent'}:
            raise ValueError('This metric has no defensible run-level aggregation; use file-level reported values')
        rule = declared_rule(rule, metric)
        filters = dict(filters or {})
        if set(filters) - {'platform', 'assay', 'library_type', 'input_stage', 'date_from', 'date_to', 'length_min', 'length_max'}:
            raise ValueError('Unsupported cohort filter')
        for key in ('platform', 'assay', 'library_type', 'input_stage', 'date_from', 'date_to'):
            if key in filters and (not isinstance(filters[key], str) or len(filters[key]) > 200):
                raise ValueError('Context filters require bounded text')
        for key in ('date_from', 'date_to'):
            if filters.get(key):
                filters[key] = date.fromisoformat(filters[key]).isoformat()
        if filters.get('date_from') and filters.get('date_to') and filters['date_from'] > filters['date_to']:
            raise ValueError('Date range is reversed')
        for key in ('length_min', 'length_max'):
            if filters.get(key) is not None and (type(filters[key]) is not int or not 0 <= filters[key] <= 2**53-1):
                raise ValueError('Length range requires nonnegative safe integers')
        if filters.get('length_min') is not None and filters.get('length_max') is not None and filters['length_min'] > filters['length_max']:
            raise ValueError('Length range is reversed')
        projects, entities, rows = self.bindings(project_ids, sample_ids, sequencing_run_ids)
        by_file = defaultdict(list)
        for row in rows:
            by_file[row['file_id']].append(row)
        if len(by_file) > MAX_FILES:
            raise ValueError('Narrow the cohort to at most 2000 distinct source files')
        points, excluded = [], []
        inspections, snapshots, metric_hashes = {}, {}, {}
        facets = {key: set() for key in ('platform', 'assay', 'library_type', 'input_stage')}
        adapters, positions = set(), set()
        unknown_runs = {entity['id']: {'id': entity['id'], 'revision': entity['revision'], 'project_id': entity['project_id'], 'name': entity['declared']['display_name']}
                        for entity in entities.values() if entity['kind'] == 'sequencing_run' and entity['declared'].get('input_stage', 'unknown') not in {'raw_fastq', 'upstream_processed'}}
        # Work on one saved metrics document at a time, not a permanent unbounded cache.
        metric_samples = OrderedDict()
        metric_cache_bytes = 0
        metric_cache_limit = 16 * 1024 * 1024
        def inspect(analysis_id):
            if analysis_id not in inspections:
                run = deepcopy(self.manager.runs[analysis_id])
                snapshots[analysis_id] = run.get('updated_at')
                inspections[analysis_id] = (run, {file['file_id']: file for file in self.manager.delivery.inspect(analysis_id, run)['files']})
            return inspections[analysis_id]
        def sample_for(analysis_id, report_id):
            nonlocal metric_cache_bytes
            if analysis_id in metric_samples:
                samples, size = metric_samples.pop(analysis_id)
                metric_samples[analysis_id] = (samples, size)
                return samples.get(report_id, {})
            samples, size = {}, 0
            try:
                path = self.manager.artifact(analysis_id, 'metrics.json')
                text = bounded_text(path)
                size = len(text.encode())
                metric_hashes[analysis_id] = hashlib.sha256(text.encode()).hexdigest()
                samples = {sample['id']: sample for sample in json.loads(text).get('samples', [])}
            except (OSError, ValueError, KeyError):
                metric_hashes[analysis_id] = None
            if size <= metric_cache_limit:
                while metric_samples and metric_cache_bytes + size > metric_cache_limit:
                    _, (_, removed) = metric_samples.popitem(last=False)
                    metric_cache_bytes -= removed
                metric_samples[analysis_id] = (samples, size)
                metric_cache_bytes += size
            return samples.get(report_id, {})
        for file_id, references in sorted(by_file.items()):
            bindings = {(row['project_id'], row['sample_id'], row['sequencing_run_id'], json.dumps({k: json.loads(row['declared']).get(k) for k in ('lane', 'chunk', 'library_identifier', 'read')}, sort_keys=True)) for row in references}
            row = references[0]
            sample_entity, run_entity = entities[row['sample_id']], entities[row['sequencing_run_id']]
            context = {'project_id': row['project_id'], 'project_name': projects[row['project_id']]['declared']['display_name'],
                'sample_id': sample_entity['id'], 'sample_name': sample_entity['declared']['display_name'],
                'sequencing_run_id': run_entity['id'], 'run_name': run_entity['declared']['display_name'],
                'platform': run_entity['declared'].get('platform', ''), 'assay': sample_entity['declared'].get('assay', ''),
                'library_type': sample_entity['declared'].get('library_type', ''), 'sequenced_at': run_entity['declared'].get('sequenced_at'),
                **{k: json.loads(row['declared']).get(k) for k in ('lane', 'chunk', 'library_identifier', 'read')}}
            raw_date = context['sequenced_at']
            try:
                context['sequenced_at'] = date.fromisoformat(raw_date).isoformat() if raw_date else None
            except (ValueError, TypeError):
                context['sequenced_at'] = None
            context['sequenced_at_declared_raw'] = raw_date
            base = {'id': 'point-' + digest([row['project_id'], file_id])[:24], 'file_id': file_id, 'context': context, 'metric': metric,
                    'unit': METRICS[metric]['unit'], 'value': None, 'raw_value': None, 'reason': None, 'sources': [],
                    'references': [{'analysis_id': r['analysis_id'], 'file_id': file_id, 'filename': json.loads(r['observed']).get('filename'), 'report_id': json.loads(r['observed']).get('report_id')} for r in references]}
            if len(bindings) != 1:
                excluded.append({**base, 'reason': 'Same source file has conflicting project/sample/run/lane identities; narrow the cohort or explicitly resolve associations'})
                continue
            if sample_entity['declared']['status'] != 'active' or run_entity['declared']['status'] != 'active' or projects[row['project_id']]['declared']['status'] != 'active':
                excluded.append({**base, 'reason': 'Archived project/sample/run is outside the active cohort'}); continue
            candidates = sorted({r['analysis_id'] for r in references}, key=lambda value: self.manager.runs.get(value, {}).get('finished_at') or '', reverse=True)
            reason = 'No available current source evidence'
            selected = None
            for analysis_id in candidates:
                try:
                    run, files = inspect(analysis_id)
                    file = files[file_id]
                    if run['state'] in {'queued', 'running'} or not file['input_available']:
                        reason = 'Source analysis is active or original FASTQ is unavailable'; continue
                    sample = sample_for(analysis_id, file.get('report_id'))
                    table = module(sample, 'Adapter Content')
                    adapters.update((table or {}).get('columns', [])[1:])
                    positions.update(r[0] for r in (table or {}).get('rows', []) if r)
                    candidate = reported_metric(file, run, sample, metric, adapter, position)
                    if candidate['reason']:
                        reason = candidate['reason']; continue
                    selected = (analysis_id, run, file, candidate)
                    break
                except (OSError, ValueError, KeyError):
                    reason = 'Saved source/result is missing or inaccessible'
            if selected is None:
                excluded.append({**base, 'reason': reason}); continue
            analysis_id, run, file, value = selected
            project_stage = run_entity['declared'].get('input_stage', 'unknown')
            analysis_stage = run.get('yield_config', {}).get('input_stage', 'unknown')
            project_stage = project_stage if project_stage in {'raw_fastq', 'upstream_processed'} else 'unknown'
            analysis_stage = analysis_stage if analysis_stage in {'raw_fastq', 'upstream_processed'} else 'unknown'
            stage = project_stage if project_stage != 'unknown' else analysis_stage
            context['input_stage'] = stage
            context['stage_source'] = 'Project run declaration' if project_stage != 'unknown' else 'Analysis-local declaration' if analysis_stage != 'unknown' else 'Unknown'
            source = {'analysis_id': analysis_id, 'file_id': file_id, 'filename': file['filename'], 'report_id': file.get('report_id'),
                      'tools': {key: info.get('version') for key, info in run.get('tools', {}).items()},
                      'validator_version': run.get('integrity', {}).get('version'), 'integrity_task_id': run.get('integrity', {}).get('task_id'),
                      'source_snapshot': file.get('source_snapshot'), 'source_sha256': file.get('sha256'),
                      'metrics_sha256': metric_hashes.get(analysis_id), 'counts_source': file.get('counts_source'),
                      'reported_metric': {key: value.get(key) for key in ('metric', 'raw_value', 'numerator', 'denominator', 'definition')},
                      'analysis_created_at': run['created_at'], 'analysis_finished_at': run.get('finished_at')}
            point = {**base, **value, 'sources': [source], 'filename': file['filename'], 'file_count': 1}
            if project_stage != 'unknown' and analysis_stage != 'unknown' and project_stage != analysis_stage:
                point['reason'] = 'Project and analysis-local input-stage declarations conflict'
            elif stage == 'unknown':
                point['reason'] = 'Input stage is unknown; declare raw FASTQ or upstream processed before cross-run comparison'
            for key in facets:
                if context.get(key): facets[key].add(context[key])
            for key in ('platform', 'assay', 'library_type', 'input_stage'):
                if filters.get(key) and context.get(key) != filters[key]:
                    point['reason'] = 'Excluded by declared ' + key + ' filter'
            for key, lower in [('date_from', True), ('date_to', False)]:
                if filters.get(key) and (not context['sequenced_at'] or (context['sequenced_at'] < filters[key] if lower else context['sequenced_at'] > filters[key])):
                    point['reason'] = 'Sequencing date is missing or outside the declared date range; QC execution date is not substituted'
            interval = length_range(file.get('sequence_length'))
            if any(filters.get(key) is not None for key in ('length_min', 'length_max')):
                if interval is None or filters.get('length_min') is not None and interval[0] < filters['length_min'] or filters.get('length_max') is not None and interval[1] > filters['length_max']:
                    point['reason'] = 'Reported entire-file length range is unavailable or outside the filter; reads are not filtered/trimmed'
            definition = {**point['definition'], 'input_stage': stage, 'platform': context['platform'], 'assay': context['assay'], 'library_type': context['library_type']}
            point['definition'] = definition
            point['group_id'] = 'definition-' + digest(definition)[:24]
            point['context_note'] = 'Assay/library/platform metadata is incomplete; values are descriptive and do not establish assay suitability' if any(not context[key] for key in ('platform', 'assay', 'library_type')) else None
            (excluded if point['reason'] else points).append(point)
        # Detect known physical aliases without guessing biology from equal content.
        physical = defaultdict(list)
        for point in points:
            stat = point['sources'][0].get('source_snapshot') or {}
            if 'device' in stat and 'inode' in stat:
                physical[(stat['device'], stat['inode'])].append(point)
        duplicate_ids = {p['id'] for entries in physical.values() if len(entries) > 1 for p in entries}
        excluded.extend({**p, 'reason': 'Multiple selected paths refer to the same physical source file; no independent observations are inferred'} for p in points if p['id'] in duplicate_ids)
        points = [p for p in points if p['id'] not in duplicate_ids]
        if group_by == 'run':
            points, excluded = self.rollup(points, excluded, metric)
        for point in points:
            point['rule_result'] = flag(point, rule)
        groups = defaultdict(list)
        for point in points:
            groups[point['group_id']].append(point)
        summaries = [{'id': key, 'count': len(items), 'definition': items[0]['definition'], 'label': self.group_label(items[0])} for key, items in groups.items()]
        if len(summaries) > 100:
            raise ValueError('More than 100 incompatible definitions; narrow the cohort using context filters')
        summaries.sort(key=lambda item: (-item['count'], item['id']))
        # Reject in-flight changes to selected evidence; unrelated analyses do not starve reads.
        if any(self.manager.runs.get(key, {}).get('updated_at') != stamp for key, stamp in snapshots.items()):
            raise CatalogConflict('Selected source evidence changed while preparing comparison; refresh')
        with self.catalog.transaction() as db:
            if any(self.catalog.entity(db, key)['revision'] != value['revision'] for key, value in {**projects, **entities}.items()):
                raise CatalogConflict('Selected context metadata changed while preparing comparison; refresh')
        result = {'metric': {'id': metric, **METRICS[metric]}, 'group_by': group_by, 'points': points, 'excluded': excluded,
                  'groups': summaries, 'rule': rule, 'unknown_stage_runs': list(unknown_runs.values())[:100], 'unknown_stage_run_total': len(unknown_runs), 'facets': {key: sorted(values) for key, values in facets.items()},
                  'adapter_categories': sorted(adapters)[:100], 'position_bins': sorted(positions)[:1000],
                  'selector_limits': {'adapter_categories': len(adapters) > 100, 'position_bins': len(positions) > 1000}, 'scope_note': 'Selected file-level evidence only; R1/R2 and lanes retain identity. Run totals cover selected files, not unproven whole-run yield.'}
        result['fingerprint'] = digest(result)
        return result

    @staticmethod
    def group_label(point):
        definition = point['definition']
        parts = [definition['calculator'], str(definition['version']), definition['input_stage'], definition.get('assay') or 'assay unspecified', definition.get('library_type') or 'library unspecified', definition.get('platform') or 'platform unspecified']
        if 'adapter_definition' in definition and definition['adapter_definition'].startswith('unverified-across-analyses:'):
            parts.append('adapter definition restricted to one analysis')
        return ' · '.join(parts)

    @staticmethod
    def rollup(points, excluded, metric):
        by_run = defaultdict(list)
        for point in [*points, *excluded]:
            by_run[(point['context']['project_id'], point['context']['sequencing_run_id'])].append(point)
        output, omitted = [], []
        for key, members in by_run.items():
            source = members[0]
            aggregate = {**source, 'id': 'run-point-' + digest(key)[:24], 'file_id': None, 'filename': None,
                         'context': {**source['context'], 'sample_id': None, 'sample_name': 'Selected files', 'read': None, 'lane': None, 'chunk': None},
                         'sources': [entry for point in members for entry in point['sources']],
                         'references': [entry for point in members for entry in point.get('references', [])], 'file_count': len(members), 'raw_value': None,
                         'value': None, 'numerator': None, 'denominator': None}
            if any(point.get('reason') for point in members) or len({point.get('group_id') for point in members}) != 1:
                omitted.append({**aggregate, 'reason': 'At least one selected file is missing/incompatible; no partial or mixed-definition run total is asserted'}); continue
            if metric in {'reads', 'bases'}:
                value = sum_known([{'count': p['value']} for p in members], 'count')
                aggregate.update(value=value, raw_value=str(value) if value is not None else None)
            else:
                numerator = sum_known(members, 'numerator'); denominator = sum_known(members, 'denominator')
                value = 100 * numerator / denominator if numerator is not None and denominator else None
                aggregate.update(value=value, numerator=numerator, denominator=denominator, raw_value=f'{numerator}/{denominator}' if value is not None else None)
            if value is None:
                omitted.append({**aggregate, 'reason': 'Complete exact selected-file totals are unavailable or outside the supported integer range'})
            else:
                output.append(aggregate)
        return output, omitted

    def query(self, *args, offset=0, limit=100, definition_id=None, **kwargs):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Comparison page requires 1–100 rows and nonnegative offset')
        prepared = self.prepare(*args, **kwargs)
        group = definition_id or (prepared['groups'][0]['id'] if prepared['groups'] else None)
        if definition_id and not any(item['id'] == definition_id for item in prepared['groups']):
            raise ValueError('Selected compatible definition is unavailable; refresh')
        selected = [p for p in prepared['points'] if p['group_id'] == group]
        incompatible = [{**p, 'reason': 'Different metric definition/tool version/stage/context from the selected comparison group'} for p in prepared['points'] if p['group_id'] != group]
        excluded = [*prepared['excluded'], *incompatible]
        return {**{key: value for key, value in prepared.items() if key not in {'points', 'excluded'}}, 'selected_group': group,
                'points': selected[offset:offset + limit], 'excluded': excluded[offset:offset + limit], 'total': len(selected),
                'excluded_total': len(excluded), 'offset': offset, 'limit': limit}

    def export(self, *args, fingerprint, definition_id=None, format='csv', mode='spreadsheet', exclusions=False, **kwargs):
        from .delivery import table_export
        prepared = self.prepare(*args, **kwargs)
        if prepared['fingerprint'] != fingerprint:
            raise CatalogConflict('Source values/context changed after viewing; refresh before exporting')
        group = definition_id or (prepared['groups'][0]['id'] if prepared['groups'] else None)
        if definition_id and not any(entry['id'] == definition_id for entry in prepared['groups']):
            raise ValueError('Unknown compatible definition')
        if format not in {'csv', 'tsv'}:
            raise ValueError('Choose CSV or TSV')
        selected = [point for point in prepared['points'] if point['group_id'] == group]
        if exclusions:
            selected = [*prepared['excluded'], *[{**point, 'reason': 'Incompatible with selected definition'} for point in prepared['points'] if point['group_id'] != group]]
        fields = ['project_id', 'project_name', 'sample_id', 'sample_name', 'sequencing_run_id', 'run_name', 'lane', 'chunk', 'read',
                  'metric', 'unit', 'value', 'raw_reported_value_or_count_fraction', 'numerator', 'denominator', 'file_count',
                  'input_stage', 'stage_source', 'platform', 'assay', 'library_type', 'sequencing_date_declared',
                  'definition', 'source_provenance', 'rule', 'rule_result', 'unavailable_or_excluded_reason', 'comparison_fingerprint']
        rows = []
        for point in selected:
            context = point['context']
            rows.append([*[context.get(key) for key in fields[:9]], point['metric'], point['unit'], point.get('value'), point.get('raw_value'),
                         point.get('numerator'), point.get('denominator'), point.get('file_count', 1),
                         *[context.get(key) for key in ('input_stage', 'stage_source', 'platform', 'assay', 'library_type', 'sequenced_at')],
                         json.dumps(point.get('definition'), sort_keys=True), json.dumps(point.get('sources') or point.get('references', []), sort_keys=True),
                         json.dumps(prepared['rule'], sort_keys=True), point.get('rule_result'), point.get('reason'), fingerprint])
        return table_export(fields, rows, mode, '\t' if format == 'tsv' else ',')

    def update_run_context(self, project_ids, records, fields):
        if not records or len(records) > 100 or len({record['id'] for record in records}) != len(records):
            raise ValueError('Select 1–100 distinct sequencing-run records')
        if not fields or set(fields) - {'input_stage', 'platform', 'sequenced_at'}:
            raise ValueError('Only explicit run stage/platform/date context can be updated in bulk')
        with self.catalog.transaction(True) as db:
            for project_id in project_ids:
                project = self.catalog.entity(db, project_id, 'project')
                if project['declared']['status'] != 'active':
                    raise ValueError('Restore archived projects before updating declarations')
            updated = []
            for record in records:
                entity = self.catalog.entity(db, record['id'], 'sequencing_run')
                if entity['project_id'] not in project_ids or entity['declared']['status'] != 'active':
                    raise ValueError('Select active runs belonging to the explicitly selected projects')
                updated.append(self.catalog.edit_record(db, entity['id'], record['revision'], fields, entity['project_id']))
            return {'updated': [{'id': item['id'], 'revision': item['revision']} for item in updated],
                    'meaning': 'User-declared context only; source FASTQs, QC data and historical release decisions are unchanged'}
