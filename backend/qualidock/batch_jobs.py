"""Bounded project orchestration of existing QC and validation, never a QC engine."""
import asyncio
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import uuid

from .catalog import CatalogConflict, encoded
from .integrity import VERSION, snapshot
from .manager import ACTIVE, now
from .metrics import bounded_text
from .release_policy import digest

MAX_FILES = 2000
MAX_UNITS = 20
MAX_ACTIVE = 5


def options(value, manager):
    defaults = {'mode': 'both', 'threads': 1, 'integrity': 'full', 'yield': True,
                'demultiplex': False, 'reuse': True, 'output_root': None}
    if not isinstance(value, dict) or set(value) - set(defaults):
        raise ValueError('Unsupported batch options')
    result = {**defaults, **value}
    if not isinstance(result['mode'], str) or not isinstance(result['integrity'], str) or result['mode'] not in {'fastqc', 'both'} or result['integrity'] not in {'off', 'quick', 'full'}:
        raise ValueError('Choose FastQC/both and off/quick/full integrity')
    if type(result['threads']) is not int or not 1 <= result['threads'] <= manager.settings.max_threads:
        raise ValueError('Thread count exceeds the allocated resources')
    if any(type(result[key]) is not bool for key in ('yield', 'demultiplex', 'reuse')):
        raise ValueError('Batch switches require booleans')
    if result['output_root'] is not None and not isinstance(result['output_root'], str):
        raise ValueError('Output root requires an explicitly configured directory')
    result['output_root'] = str(manager.stores.resolve(result['output_root']))
    return result


def relationships(files, entities):
    """Only unique explicit project declarations establish an analysis pair."""
    buckets = defaultdict(list)
    for file in files:
        declared = file['declared']
        buckets[(file['sample_id'], declared.get('lane'), declared.get('chunk'), declared.get('library_identifier'))].append(file)
    paired = {}
    warnings = []
    for key, members in buckets.items():
        roles = {file['declared'].get('read') for file in members}
        if len(members) == 2 and roles == {'R1', 'R2'}:
            for file in members:
                mate = next(other for other in members if other is not file)
                paired[file['path']] = {'mate': mate['path'], 'pair_key': 'project:' + digest(key), 'read': file['declared']['read']}
        elif any(file['declared'].get('read') in {'R1', 'R2'} for file in members):
            warnings.append('Incomplete/ambiguous declared pair: ' + key[0] + '; reads remain unpaired')
    records = []
    groups = {}
    for file in files:
        pair = paired.get(file['path'])
        declaration = file['declared']
        records.append({'path': file['path'], 'source': 'manual', 'assignment': 'paired' if pair else 'single' if declaration.get('read') == 'SE' else 'unpaired',
                        'paired': bool(pair), 'read': pair['read'] if pair else None,
                        'mate': pair['mate'] if pair else None, 'pair_key': pair['pair_key'] if pair else None,
                        'lane': declaration.get('lane'), 'chunk': declaration.get('chunk')})
        group = groups.setdefault(file['sample_id'], {'id': file['sample_id'], 'display_name': ''.join(c for c in entities[file['sample_id']]['declared']['display_name'] if ord(c) >= 32)[:120] or file['sample_id'], 'source': 'manual', 'files': []})
        group['files'].append(file['path'])
    return records, list(groups.values()), warnings


def pair_signature(records):
    return sorted((row['path'], row.get('mate') if row.get('paired') else None,
                   row.get('read') if row.get('paired') else None) for row in records)


class BatchJobs:
    def __init__(self, manager):
        self.manager = manager
        self.catalog = manager.catalog
        self.tasks = {}
        self.records = {}
        self.cancelled = set()
        self.guard = asyncio.Lock()

    def recover(self):
        with self.catalog.transaction(True) as db:
            for row in db.execute('SELECT * FROM batch_attempts').fetchall():
                record = json.loads(row['record'])
                if record['state'] in ACTIVE:
                    record.update(state='interrupted', finished_at=now(), error='Previous session ended; explicitly retry after reviewing current inputs')
                    for unit in record['units']:
                        for stage in unit['stages'].values():
                            if stage['state'] in ACTIVE or stage['state'] == 'pending':
                                stage.update(state='not_evaluated', reason='Session ended before this stage completed')
                    db.execute('UPDATE batch_attempts SET record=? WHERE id=?', (encoded(record), record['id']))
                    self.catalog.event(db, row['project_id'], record['id'], 'batch_interrupted', {'plan_id': row['plan_id']})

    def context(self, project_id, sample_ids, sequencing_run_ids, config, tools):
        for values in (sample_ids, sequencing_run_ids):
            if values is not None and (not isinstance(values, list) or not 1 <= len(values) <= 100 or len(set(values)) != len(values) or any(not isinstance(value, str) for value in values)):
                raise ValueError('Select 1–100 distinct stable cohort IDs, or the entire project')
        sample_ids = sorted(sample_ids) if sample_ids is not None else None
        sequencing_run_ids = sorted(sequencing_run_ids) if sequencing_run_ids is not None else None
        with self.catalog.transaction() as db:
            project = self.catalog.entity(db, project_id, 'project')
            if project['declared']['status'] != 'active':
                raise ValueError('Restore the project before planning work')
            for ids, kind in [(sample_ids, 'sample'), (sequencing_run_ids, 'sequencing_run')]:
                for entity_id in ids or []:
                    self.catalog.entity(db, entity_id, kind, project_id)
            where = 'a.project_id=?'
            args = [project_id]
            for column, ids in [('sample_id', sample_ids), ('sequencing_run_id', sequencing_run_ids)]:
                if ids is not None:
                    where += ' AND a.' + column + ' IN (' + ','.join('?' for _ in ids) + ')'
                    args.extend(ids)
            rows = []
            for row in db.execute('SELECT a.*,l.analysis_id FROM associations a JOIN analysis_links l ON l.id=a.analysis_link_id WHERE ' + where + ' ORDER BY a.id', args):
                if self.manager.runs.get(row['analysis_id'], {}).get('batch_origin') and row['revision'] == 1:
                    continue
                rows.append(dict(row))
                if len(rows) > 5000:
                    raise ValueError('Select a narrower cohort: at most 5000 source associations per plan')
            entities = {value: self.catalog.entity(db, value) for row in rows for value in (row['sample_id'], row['sequencing_run_id'])}
        inventories = {}
        delivery_revisions = {}
        files = defaultdict(list)
        skipped = []
        for row in rows:
            if any(entities[row[key]]['declared']['status'] != 'active' for key in ('sample_id', 'sequencing_run_id')):
                skipped.append({'file_id': row['file_id'], 'reason': 'Archived sample/run'}); continue
            try:
                if row['analysis_id'] not in inventories:
                    inventory = self.manager.delivery.inspect(row['analysis_id'])
                    delivery_revisions[row['analysis_id']] = inventory.get('delivery_revision', 0)
                    inventories[row['analysis_id']] = {f['file_id']: f for f in inventory['files']}
                source = inventories[row['analysis_id']][row['file_id']]
                if not source['input_available']:
                    raise ValueError('Source FASTQ is unavailable')
                declared = json.loads(row['declared'])
                # Metadata organization must not silently truncate lane identities.
                if any(value is not None and (len(value) > 80 or any(ord(c) < 32 for c in value)) for value in (declared.get('lane'), declared.get('chunk'))):
                    raise ValueError('Lane/chunk declaration exceeds analysis metadata limits; correct it first')
                files[source['path']].append({'file_id': row['file_id'], 'filename': source['filename'], 'path': source['path'],
                    'sample_id': row['sample_id'], 'sequencing_run_id': row['sequencing_run_id'], 'declared': declared,
                    'source_snapshot': source['source_snapshot'], 'source_analysis_id': row['analysis_id'],
                    'association_id': row['id'], 'association_revision': row['revision']})
            except (KeyError, OSError, ValueError):
                skipped.append({'file_id': row['file_id'], 'reason': 'Source FASTQ/reference unavailable or incompatible; inspect its analysis'})
        for ids, column, kind in [(sample_ids, 'sample_id', 'sample'), (sequencing_run_ids, 'sequencing_run_id', 'sequencing run')]:
            referenced = {row[column] for row in rows}
            for entity_id in ids or []:
                if entity_id not in referenced:
                    skipped.append({'entity_id': entity_id, 'reason': 'Selected ' + kind + ' has no confirmed FASTQ references in this cohort'})
        selected = []
        for members in files.values():
            signatures = {digest({'sample_id': file['sample_id'], 'sequencing_run_id': file['sequencing_run_id'],
                                  'binding': {key: file['declared'].get(key) for key in ('lane', 'chunk', 'library_identifier', 'read')},
                                  'source_snapshot': file['source_snapshot']}) for file in members}
            # Confirmation provenance is retained in the audit trail; differing
            # user_confirmed/user_assigned labels are not conflicting identities.
            if len(signatures) != 1:
                skipped.append({'file_id': members[0]['file_id'], 'reason': 'Conflicting confirmed identities for the same source; explicitly resolve associations'}); continue
            selected.append({**members[0], 'source_analysis_ids': sorted({file['source_analysis_id'] for file in members}),
                             'association_revisions': sorted((file['association_id'], file['association_revision']) for file in members)})
        if len(selected) > MAX_FILES:
            raise ValueError('Select at most 2000 distinct FASTQ files per batch')
        selected.sort(key=lambda f: (f['sequencing_run_id'], f['sample_id'], f['path']))
        context = {'project_id': project_id, 'project_revision': project['revision'], 'sample_ids': sample_ids,
                   'sequencing_run_ids': sequencing_run_ids, 'options': config, 'tools': tools,
                   'entities': entities, 'files': selected, 'skipped': skipped,
                   'delivery_revisions': delivery_revisions,
                   'tool_executables': self.manager.tool_signature, 'resources': {'memory_mb': self.manager.settings.memory_mb, 'max_threads': self.manager.settings.max_threads}}
        return context

    def proof(self, run_id, unit, plan):
        """Exact scope, execution, pairing and persisted actual metrics; no guessing."""
        manager = self.manager
        run = manager.runs[run_id]
        if run['state'] != 'completed' or run['mode'] != plan['options']['mode'] or run['threads'] != plan['options']['threads']:
            raise ValueError('QC execution state/options do not match')
        paths = run.get('sample_input_paths', run['inputs'])
        if set(paths) != {file['path'] for file in unit['files']} or len(paths) != len(unit['files']):
            raise ValueError('Only complete matching analysis input scopes are reusable')
        if pair_signature(run.get('input_pairing', [])) != pair_signature(unit['input_pairing']):
            raise ValueError('Pairing configuration differs; use a new QC analysis')
        for tool, version in plan['tools'].items():
            if run.get('tools', {}).get(tool, {}).get('version') != version:
                raise ValueError('Tool versions differ or are unknown')
        data = manager.delivery.inspect(run_id)
        if len(data['files']) != len(unit['files']) or any(not file['qc_snapshot_matches'] or not file['report_id'] for file in data['files']):
            raise ValueError('QC source identity or parsed result is missing/stale')
        if {file['path']: file['source_snapshot'] for file in data['files']} != {file['path']: file['source_snapshot'] for file in unit['files']}:
            raise ValueError('Source fingerprint changed')
        metrics = manager.artifact(run_id, 'metrics.json')
        result = {'analysis_id': run_id, 'metrics_sha256': hashlib.sha256(bounded_text(metrics).encode()).hexdigest()}
        # Official output references must remain registered and accessible too.
        required = [entry['path'] for entry in run.get('reports', []) if entry['path'].endswith(('_fastqc.html', '_fastqc.zip')) or entry['path'] == 'multiqc/multiqc_report.html']
        if len(required) < 2 * len(unit['files']) + (plan['options']['mode'] == 'both'):
            raise ValueError('Official QC artifacts are missing')
        for path in required:
            manager.artifact(run_id, path)
        return result

    async def preview(self, project_id, sample_ids=None, sequencing_run_ids=None, requested=None):
        config = options(requested or {}, self.manager)
        detected = await self.manager.detect_tools()
        names = ['fastqc', 'multiqc'] if config['mode'] == 'both' else ['fastqc']
        if any(not detected.get(name, {}).get('compatible') or not detected[name].get('version') for name in names):
            raise ValueError('Required QC tools must be available, compatible and have detected versions')
        tools = {name: detected[name]['version'] for name in names}
        context = await asyncio.to_thread(self.context, project_id, sample_ids, sequencing_run_ids, config, tools)
        fingerprint = digest(context)
        by_run = defaultdict(list)
        for file in context['files']:
            by_run[file['sequencing_run_id']].append(file)
        units = []
        for run_id, files in by_run.items():
            for offset in range(0, len(files), 500):
                subset = files[offset:offset + 500]
                pairing, groups, warnings = relationships(subset, context['entities'])
                unit = {'id': 'unit-' + digest([run_id, [f['file_id'] for f in subset]])[:24], 'sequencing_run_id': run_id,
                        'display_name': context['entities'][run_id]['declared']['display_name'], 'files': subset,
                        'input_pairing': pairing, 'sample_groups': groups, 'warnings': warnings,
                        'reuse': None, 'reuse_reason': 'New QC required: no exact matching completed scope/tool/options/source proof'}
                if config['reuse']:
                    sources = {a for file in subset for a in file['source_analysis_ids']}
                    sources.update(run['id'] for run in self.manager.runs.values() if run.get('batch_origin', {}).get('project_id') == project_id and set(run.get('sample_input_paths', [])) == {f['path'] for f in subset})
                    candidates = sorted(sources, key=lambda a: self.manager.runs.get(a, {}).get('created_at', ''), reverse=True)
                    for candidate in candidates:
                        try:
                            unit['reuse'] = await asyncio.to_thread(self.proof, candidate, unit, {'options': config, 'tools': tools})
                            unit['reuse_reason'] = 'Reuse exact complete scope and matching source/tool/options/pairing proof'; break
                        except (OSError, ValueError, KeyError):
                            continue
                units.append(unit)
        if len(units) > MAX_UNITS:
            raise ValueError('Select at most 20 run/chunk units per batch')
        plan = {'id': 'bpl_' + uuid.uuid4().hex, 'project_id': project_id, 'fingerprint': fingerprint,
                'created_at': now(), 'sample_ids': sample_ids, 'sequencing_run_ids': sequencing_run_ids,
                'options': config, 'tools': tools, 'units': units, 'skipped': context['skipped'],
                'source_bytes': sum(file['source_snapshot']['size'] for file in context['files']),
                'file_count': len(context['files']), 'expected_outputs': ['Individual FastQC HTML/ZIP', 'Native metrics.json'] + (['Combined MultiQC report and structured data per unit'] if config['mode'] == 'both' else []),
                'io_note': 'Compressed source sizes, not a runtime/traffic estimate. QC and integrity read source data separately; full integrity scans every byte. No source copies. Reuse can avoid QC reads.',
                'release_state': 'not_evaluated'}
        with self.catalog.transaction(True) as db:
            db.execute('INSERT INTO batch_plans VALUES(?,?,?,?,?)', (plan['id'], project_id, plan['created_at'], fingerprint, encoded(plan)))
            self.catalog.event(db, project_id, plan['id'], 'batch_planned', {'fingerprint': fingerprint, 'file_count': plan['file_count'], 'units': len(units)})
        return self.public(plan)

    @staticmethod
    def public(plan):
        result = deepcopy(plan)
        for unit in result['units']:
            unit.pop('input_pairing', None); unit.pop('sample_groups', None)
            for file in unit['files']:
                file.pop('path', None)
        return result

    def read_plan(self, project_id, plan_id):
        with self.catalog.transaction() as db:
            row = db.execute('SELECT plan FROM batch_plans WHERE id=? AND project_id=?', (plan_id, project_id)).fetchone()
            if row is None:
                raise ValueError('Unknown project batch plan')
            return json.loads(row[0])

    def read(self, project_id, attempt_id):
        with self.catalog.transaction() as db:
            row = db.execute('SELECT record FROM batch_attempts WHERE id=? AND project_id=?', (attempt_id, project_id)).fetchone()
            if row is None:
                raise ValueError('Unknown project batch attempt')
            result = json.loads(row[0])
        for unit in result['units']:
            run = self.manager.runs.get(unit.get('analysis_id'))
            if run and result['state'] in ACTIVE:
                unit['input_outcomes'] = [{k: row.get(k) for k in ('id', 'name', 'state', 'error', 'exit_code')} for row in run.get('input_outcomes', [])]
                unit['integrity_progress'] = {k: run.get('integrity', {}).get(k) for k in ('state', 'current_file', 'completed_files', 'total_files')}
                # Integrity progress contains private canonical paths internally.
                current = unit['integrity_progress'].get('current_file')
                if isinstance(current, dict):
                    name = next((file['name'] for file in run.get('input_outcomes', []) if file['id'] == current.get('id')), None)
                    unit['integrity_progress']['current_file'] = {k: current.get(k) for k in ('state', 'records_scanned', 'compressed_bytes_read')}
                    unit['integrity_progress']['current_file']['name'] = name
        return result

    def listing(self, project_id, offset=0, limit=25):
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError('Invalid batch page')
        with self.catalog.transaction() as db:
            self.catalog.entity(db, project_id, 'project')
            total = db.execute('SELECT COUNT(*) FROM batch_attempts WHERE project_id=?', (project_id,)).fetchone()[0]
            records = [json.loads(row[0]) for row in db.execute('SELECT record FROM batch_attempts WHERE project_id=? ORDER BY created_at DESC,id LIMIT ? OFFSET ?', (project_id, limit, offset))]
        keys = ('id', 'plan_id', 'state', 'created_at', 'finished_at', 'retry_of', 'error', 'release_state')
        return {'items': [{key: r.get(key) for key in keys} for r in records], 'total': total, 'offset': offset, 'limit': limit}

    def save(self, record, action=None):
        with self.catalog.transaction(True) as db:
            db.execute('UPDATE batch_attempts SET record=? WHERE id=?', (encoded(record), record['id']))
            if action:
                units = []
                for unit in record['units']:
                    stages = {name: {key: stage[key] for key in ('state', 'result', 'task_id', 'proof', 'reused') if key in stage}
                              for name, stage in unit['stages'].items()}
                    units.append({'id': unit['id'], 'analysis_id': unit['analysis_id'], 'owned': unit['owned'], 'stages': stages})
                self.catalog.event(db, record['project_id'], record['id'], action,
                                   {'plan_id': record['plan_id'], 'state': record['state'], 'units': units})
        self.manager.revision += 1

    async def verify(self, plan):
        detected = await self.manager.detect_tools()
        tools = {name: detected.get(name, {}).get('version') if detected.get(name, {}).get('compatible') else None for name in plan['tools']}
        current = await asyncio.to_thread(self.context, plan['project_id'], plan['sample_ids'], plan['sequencing_run_ids'], plan['options'], tools)
        if digest(current) != plan['fingerprint']:
            raise CatalogConflict('Cohort, inputs, tools or metadata changed after preview; create a new plan')

    @staticmethod
    def work_fingerprint(plan):
        # Equivalent all/explicit cohort filters must not enqueue the same work.
        units = []
        for unit in plan['units']:
            units.append({'sequencing_run_id': unit['sequencing_run_id'],
                          'files': sorted((file['file_id'], file['source_snapshot']) for file in unit['files']),
                          'pairs': pair_signature(unit['input_pairing']),
                          'groups': sorted((group['id'], sorted(group['files'])) for group in unit['sample_groups'])})
        return digest({'project_id': plan['project_id'], 'options': plan['options'], 'tools': plan['tools'], 'units': units})

    async def start(self, project_id, plan_id, key, retry_of=None):
        if not isinstance(key, str) or not 8 <= len(key) <= 128 or any(ord(c) < 33 for c in key):
            raise ValueError('Provide a stable 8–128 character idempotency key')
        async with self.guard:
            with self.catalog.transaction() as db:
                old = db.execute('SELECT record FROM batch_attempts WHERE plan_id=? AND request_key=? AND project_id=?', (plan_id, key, project_id)).fetchone()
                if old:
                    return json.loads(old[0])
                submitted = bool(db.execute('SELECT 1 FROM batch_attempts WHERE plan_id=? LIMIT 1', (plan_id,)).fetchone())
            active = list(self.records.values())
            if self.manager.closing or len(self.tasks) >= MAX_ACTIVE:
                raise CatalogConflict('Session is stopping or the five-batch queue is full')
            plan = self.read_plan(project_id, plan_id)
            for attempt in active:
                if attempt['project_id'] == project_id and attempt['state'] in ACTIVE:
                    existing = self.read_plan(project_id, attempt['plan_id'])
                    if self.work_fingerprint(existing) == self.work_fingerprint(plan):
                        raise CatalogConflict('This plan is already active; inspect its existing attempt')
            if not plan['units']:
                raise ValueError('No eligible FASTQs; resolve skipped/unassigned files first')
            await self.verify(plan)
            previous = None
            if retry_of:
                previous = self.read(project_id, retry_of)
                if previous['plan_id'] != plan_id or previous['state'] in ACTIVE:
                    raise ValueError('Retry a terminal attempt belonging to this plan')
            elif submitted:
                raise CatalogConflict('Plan was previously submitted; explicitly retry its terminal attempt')
            units = []
            for unit in plan['units']:
                previous_unit = next((u for u in (previous or {}).get('units', []) if u['id'] == unit['id']), {})
                units.append({'id': unit['id'], 'sequencing_run_id': unit['sequencing_run_id'], 'display_name': unit['display_name'],
                              'analysis_id': None, 'owned': False, 'resume_analysis_id': previous_unit.get('analysis_id') if previous_unit.get('owned') else None,
                              'integrity_task_id': None, 'file_ids': [f['file_id'] for f in unit['files']],
                              'stages': {stage: {'state': 'pending'} for stage in ('qc', 'integrity', 'yield', 'demultiplex')}})
            record = {'id': 'bat_' + uuid.uuid4().hex, 'plan_id': plan_id, 'project_id': project_id,
                      'created_at': now(), 'started_at': None, 'finished_at': None, 'state': 'queued', 'retry_of': retry_of,
                      'units': units, 'error': None, 'release_state': 'not_evaluated'}
            with self.catalog.transaction(True) as db:
                db.execute('INSERT INTO batch_attempts VALUES(?,?,?,?,?,?)', (record['id'], project_id, plan_id, key, record['created_at'], encoded(record)))
                self.catalog.event(db, project_id, record['id'], 'batch_queued', {'plan_id': plan_id, 'retry_of': retry_of})
            self.records[record['id']] = record
            self.tasks[record['id']] = asyncio.create_task(self.execute(record, plan))
            return deepcopy(record)

    def stopped(self, record):
        return self.manager.closing or record['id'] in self.cancelled

    async def execute(self, record, plan):
        manager = self.manager
        try:
            record.update(state='running', started_at=now())
            self.save(record, 'batch_started')
            for unit, configured in zip(record['units'], plan['units']):
                if self.stopped(record):
                    break
                try:
                    await self.verify(plan)
                    # Recheck source identities immediately before each unit.
                    for file in configured['files']:
                        path = manager.files.resolve(file['path']); manager.readable_fastq(path)
                        if snapshot(path.stat()) != file['source_snapshot']:
                            raise ValueError('Source fingerprint changed before execution')
                    reusable = configured['reuse']
                    resume = unit.pop('resume_analysis_id', None)
                    if resume:
                        try:
                            reusable = await asyncio.to_thread(self.proof, resume, configured, plan)
                            unit['owned'] = True
                        except (OSError, ValueError, KeyError):
                            pass
                    if reusable:
                        proof = await asyncio.to_thread(self.proof, reusable['analysis_id'], configured, plan)
                        if proof != reusable:
                            raise ValueError('Previously reusable QC proof changed; preview again')
                        unit.update(analysis_id=proof['analysis_id'])
                        unit['stages']['qc'] = {'state': 'completed', 'reused': True, 'proof': proof}
                    else:
                        unit['stages']['qc'] = {'state': 'running', 'reused': False}
                        self.save(record, 'batch_stage')
                        run = await manager.create('Batch · ' + configured['display_name'][:160], plan['options']['mode'], [f['path'] for f in configured['files']],
                            plan['options']['threads'], input_pairing=configured['input_pairing'], sample_groups=configured['sample_groups'], output_root=plan['options']['output_root'])
                        unit.update(analysis_id=run['id'], owned=True)
                        self.save(record, 'batch_child_created')
                        manager.update(run, batch_origin={'project_id': plan['project_id'], 'plan_id': plan['id'], 'attempt_id': record['id']})
                        while run['state'] in ACTIVE and not self.stopped(record):
                            await asyncio.sleep(.1)
                        if self.stopped(record):
                            break
                        unit['stages']['qc'] = {'state': 'completed' if run['state'] == 'completed' else 'failed', 'execution_state': run['state'], 'reused': False,
                                                'reason': run.get('error')}
                    self.save(record, 'batch_stage')
                    if self.stopped(record):
                        break
                    run = manager.runs[unit['analysis_id']]
                    if unit['owned']:
                        with self.catalog.transaction() as db:
                            linked = db.execute('SELECT project_id FROM analysis_links WHERE analysis_id=?', (run['id'],)).fetchone()
                        if linked is None:
                            assignments = [{k: file[k] for k in ('file_id', 'sample_id', 'sequencing_run_id')} | file['declared'] for file in configured['files']]
                            await asyncio.to_thread(self.catalog.attach, plan['project_id'], run['id'], assignments)
                        elif linked[0] != plan['project_id']:
                            raise ValueError('Generated analysis was linked to another project')
                    unit['input_outcomes'] = [{k: row.get(k) for k in ('id', 'name', 'state', 'error', 'exit_code')} for row in run.get('input_outcomes', [])]
                    mode = plan['options']['integrity']
                    if mode == 'off':
                        unit['stages']['integrity'] = {'state': 'skipped', 'reason': 'Not requested'}
                    elif run['state'] in {'completed', 'partial', 'failed'}:
                        data = await asyncio.to_thread(manager.delivery.inspect, run['id'])
                        integrity = run.get('integrity', {})
                        current = (plan['options']['reuse'] and integrity.get('state') == 'completed' and integrity.get('mode') == mode
                                   and integrity.get('version') == VERSION and all(f['integrity_state'] == 'passed' for f in data['files'])
                                   and pair_signature(run.get('input_pairing', [])) == pair_signature(configured['input_pairing']))
                        if current:
                            unit['stages']['integrity'] = {'state': 'completed', 'result': integrity['result'], 'reused': True, 'task_id': integrity['task_id']}
                        elif run['id'] in manager.validation.tasks or run['id'] in manager.exports.tasks:
                            unit['stages']['integrity'] = {'state': 'not_evaluated', 'reason': 'Another user-requested validation/export owns this analysis; it was not replaced'}
                        else:
                            unit['stages']['integrity'] = {'state': 'running', 'reused': False}
                            task = await manager.validation.start(run['id'], mode)
                            unit['integrity_task_id'] = task['task_id']
                            self.save(record, 'batch_stage')
                            while run['id'] in manager.validation.tasks and not self.stopped(record):
                                await asyncio.sleep(.1)
                            if self.stopped(record):
                                break
                            integrity = run['integrity']
                            unit['stages']['integrity'] = {'state': 'completed' if integrity['state'] == 'completed' and integrity.get('result') == 'passed' else 'failed' if integrity.get('result') == 'failed' or integrity['state'] == 'failed' else 'not_evaluated',
                                                          'result': integrity.get('result'), 'task_id': task['task_id'], 'reused': False}
                    else:
                        unit['stages']['integrity'] = {'state': 'not_evaluated', 'reason': 'QC did not finish in a scannable state'}
                    unit['integrity_files'] = [{k: f.get(k) for k in ('id', 'state', 'coverage', 'records_scanned', 'bases_scanned', 'sha256', 'q20_bases', 'q30_bases', 'quality_bases')} for f in run.get('integrity', {}).get('files', [])]
                    data = await asyncio.to_thread(manager.delivery.inspect, run['id'])
                    unit['stages']['yield'] = {'state': 'completed', 'values': data['yields'], 'scope': 'Existing analysis-local groups/explicit targets; not project expected-yield aggregation'} if plan['options']['yield'] else {'state': 'skipped', 'reason': 'Not requested'}
                    evidence = data.get('demultiplex')
                    unit['stages']['demultiplex'] = ({'state': 'completed' if evidence and evidence.get('state') == 'available' and evidence.get('reconciliation_state') == 'matched' else 'not_evaluated',
                        'reason': 'Uses existing analysis-local demultiplexing evidence only; no evidence is inferred or imported automatically', 'evidence_state': evidence.get('state') if evidence else None}
                        if plan['options']['demultiplex'] else {'state': 'skipped', 'reason': 'Not requested'})
                    if plan['options']['yield']:
                        values = data['yields']
                        unit['stages']['yield']['validation_result'] = 'below_target' if any(v['target_state'] == 'below_target' for v in values) else 'met' if values and all(v['target_state'] == 'met' for v in values) else 'not_evaluated'
                        if any(v['target_state'] == 'below_target' for v in values):
                            unit['stages']['yield']['state'] = 'failed'
                        elif not values or any(v['totals']['reads'] is None for v in values):
                            unit['stages']['yield']['state'] = 'not_evaluated'
                    if evidence and plan['options']['demultiplex']:
                        unit['stages']['demultiplex']['reconciliation_state'] = evidence.get('reconciliation_state')
                        if evidence.get('discrepancies'):
                            unit['stages']['demultiplex'].update(state='failed', discrepancy_count=len(evidence['discrepancies']))
                    self.save(record, 'batch_stage')
                except (OSError, ValueError, KeyError) as exc:
                    for stage in unit['stages'].values():
                        if stage['state'] in {'pending', 'running'}:
                            stage.update(state='failed' if stage['state'] == 'running' else 'not_evaluated', reason=str(exc))
                    self.save(record, 'batch_stage_failed')
            if not self.stopped(record):
                states = [stage['state'] for unit in record['units'] for stage in unit['stages'].values()]
                failures = any(state in {'failed', 'not_evaluated'} for state in states) or bool(plan['skipped'])
                record.update(state='partial' if failures and 'completed' in states else 'failed' if failures else 'completed', finished_at=now())
                self.save(record, 'batch_finished')
        except Exception as exc:
            if not self.stopped(record):
                record.update(state='failed', error=str(exc), finished_at=now())
                self.save(record, 'batch_failed')
        finally:
            self.tasks.pop(record['id'], None)
            self.records.pop(record['id'], None)

    async def cancel(self, project_id, attempt_id, state='cancelled'):
        record = self.read(project_id, attempt_id)
        if record['state'] not in ACTIVE:
            return record
        self.cancelled.add(attempt_id)
        # Only the exact owned task IDs can be cancelled; unrelated manual work survives.
        for unit in record['units']:
            run = self.manager.runs.get(unit.get('analysis_id'))
            if run and unit['owned'] and run['state'] in ACTIVE:
                await self.manager.cancel(run['id'])
            if run and unit.get('integrity_task_id') and run.get('integrity', {}).get('task_id') == unit['integrity_task_id']:
                await self.manager.validation.cancel(run['id'], state)
        task = self.tasks.get(attempt_id)
        if task:
            await asyncio.gather(task, return_exceptions=True)
        record = self.read(project_id, attempt_id)
        for unit in record['units']:
            run = self.manager.runs.get(unit.get('analysis_id'))
            if run and unit['owned'] and run['state'] in ACTIVE:
                await self.manager.cancel(run['id'])
            if run and unit.get('integrity_task_id') and run.get('integrity', {}).get('task_id') == unit['integrity_task_id']:
                await self.manager.validation.cancel(run['id'], state)
        # Load stage results persisted before stopping, never overwrite them with a stale read.
        record = self.read(project_id, attempt_id)
        for unit in record['units']:
            unit.pop('integrity_progress', None)
            run = self.manager.runs.get(unit.get('analysis_id'))
            if run:
                unit['input_outcomes'] = [{k: row.get(k) for k in ('id', 'name', 'state', 'error', 'exit_code')} for row in run.get('input_outcomes', [])]
            for stage in unit['stages'].values():
                if stage['state'] in {'running', 'pending'}:
                    stage.update(state='not_evaluated', reason='Batch stopped before stage completion')
        record.update(state=state, finished_at=now())
        self.save(record, 'batch_' + state)
        return record

    async def close(self):
        for attempt_id in list(self.tasks):
            with self.catalog.transaction() as db:
                row = db.execute('SELECT project_id FROM batch_attempts WHERE id=?', (attempt_id,)).fetchone()
            if row:
                await self.cancel(row[0], attempt_id, 'interrupted')
