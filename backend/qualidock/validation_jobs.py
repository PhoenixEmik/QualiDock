"""Managed integrity tasks share the existing executor and resource slot."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import pwd
import sys
import uuid

from .integrity import VERSION, snapshot
from .store import now, save_json

ACTIVE = {"queued", "running"}
from .outcomes import plan
from .files import PathViolation
from . import datasets


def interrupted(run):
    record = run.get('integrity')
    if not record or record.get('state') not in ACTIVE:
        return False
    record.update(state='interrupted', result='not_evaluated', finished_at=now(), error='Previous session ended before validation completed')
    if record.get('current_file'):
        record['current_file']['state'] = 'not_evaluated'
    return True


class ValidationJobs:
    def __init__(self, manager):
        self.manager = manager
        self.tasks = {}
        self.cancelled = set()

    def prepare(self, run, mode):
        if run['mode'] in {'samtools','mosdepth','rseqc-infer','rseqc-distribution','picard'}:
            raise ValueError('FASTQ integrity checks do not apply to alignment inputs; inspect SAMtools evidence')
        manager = self.manager
        paths = run.get('sample_input_paths', run['inputs'])
        if run['mode'] == 'multiqc' and not run.get('sample_input_paths'):
            raise ValueError('Imported QC reports alone cannot establish integrity of absent source FASTQs')
        if not paths or len(paths) > 500:
            raise ValueError('Integrity validation requires 1–500 original FASTQ references')
        source = manager.runs.get(run.get('source_run_id'), run)
        snapshots = {entry['path']: entry for entry in source.get('input_metadata', [])}
        samples = []
        metrics = manager.directory(run['id']) / 'metrics.json'
        if metrics.is_file() and not metrics.is_symlink():
            samples = json.loads(metrics.read_text()).get('samples', [])
        derived = datasets.registered(manager, source.get("input_datasets"))
        files = []
        for entry in plan([Path(path) for path in paths]):
            entry = {key: entry[key] for key in ('id', 'path', 'name')}
            original = snapshots.get(entry['path'])
            try:
                path = datasets.resolve(manager, entry['path'], derived)
                if str(path) != entry['path']:
                    raise ValueError('Source path now resolves to another location')
                manager.readable_fastq(path)
                entry['snapshot'] = snapshot(path.stat())
                if original and any(entry['snapshot'].get(key) != original.get(key, entry['snapshot'].get(key)) for key in entry['snapshot']):
                    raise ValueError('Input changed since QC execution; rerun QC before validating this result')
                entry['qc_input_snapshot_verified'] = bool(original and all(key in original for key in ('size','mtime_ns')))
            except (ValueError, OSError) as exc:
                entry['preflight_error'] = str(exc)
            matched = [sample for sample in samples if run.get('report_input_map', {}).get(sample['id'], {}).get('path') == entry['path']]
            if not matched and len([p for p in paths if Path(p).name == entry['name']]) == 1:
                matched = [sample for sample in samples if sample['name'] == entry['name']]
            encoding = matched[0].get('encoding', '') if len(matched) == 1 and entry.get('qc_input_snapshot_verified') else ''
            if encoding == 'Sanger / Illumina 1.9' or encoding in {'Illumina 1.8', 'Sanger'}:
                entry.update(phred_offset=33, encoding_source=encoding)
            elif encoding in {'Illumina 1.3', 'Illumina 1.5'}:
                entry.update(phred_offset=64, encoding_source=encoding)
            files.append(entry)
        records = run.get('input_pairing', [])
        pairs = []
        for entry in records:
            if entry.get('paired') and entry.get('read') == 'R1':
                mate = next((record for record in records if record['path'] == entry.get('mate') and record.get('mate') == entry['path'] and record.get('read') == 'R2'), None)
                if mate:
                    pairs.append({'id': entry['pair_key'], 'r1': entry['path'], 'r2': mate['path'], 'lane': entry.get('lane'), 'chunk': entry.get('chunk'), 'source': entry.get('source', 'auto')})
        return {'version': VERSION, 'mode': mode, 'quick_reads': 10000, 'files': files, 'pairs': pairs}

    async def start(self, run_id, mode):
        manager = self.manager
        run = manager.runs[run_id]
        if manager.closing or run['state'] in ACTIVE:
            raise ValueError('Wait until QC finishes before starting an integrity scan')
        if run_id in self.tasks or len(self.tasks) >= 20:
            raise ValueError('An integrity scan is already queued/running or the scan queue is full')
        if mode not in {'full', 'quick'}:
            raise ValueError('Select full or quick validation')
        config = await asyncio.to_thread(self.prepare, run, mode)
        if manager.closing or run_id in self.tasks:
            raise ValueError('Session is stopping or validation already started')
        task_id = 'integrity-' + uuid.uuid4().hex
        parent = manager.directory(run_id) / 'integrity'
        if parent.is_symlink() or parent.resolve() != parent:
            raise PathViolation('Integrity output directory contains symlink components')
        parent.mkdir(exist_ok=True, mode=0o700)
        directory = parent / task_id
        directory.mkdir(mode=0o700)
        save_json(directory / 'config.json', config)
        history = list(run.get('integrity_history', []))
        if run.get('integrity'):
            history.append({key: run['integrity'].get(key) for key in ('task_id', 'mode', 'state', 'result', 'started_at', 'finished_at', 'artifact')})
        manager.update(run, integrity_history=history, integrity={
            'task_id': task_id, 'validator': 'QualiDock FASTQ integrity', 'version': VERSION,
            'state': 'queued', 'result': 'not_evaluated', 'mode': mode, 'quick_read_limit': 10000,
            'total_files': len(config['files']), 'configured_pairs': len(config['pairs']),
            'requested_at': now(), 'started_at': None, 'finished_at': None,
            'requested_by': {'uid': os.getuid(), 'unix_user': pwd.getpwuid(os.getuid()).pw_name},
            'files': [], 'pairs': [], 'error': None,
            'artifact': str((directory / 'validation.json').relative_to(manager.directory(run_id)))})
        self.tasks[run_id] = asyncio.create_task(self.execute(run, config, directory, task_id))
        return run['integrity']

    def read(self, path):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Integrity progress is not a bounded regular result')
        return json.loads(path.read_text())

    async def execute(self, run, config, directory, task_id):
        manager = self.manager
        command = None
        try:
            async with manager.slot:
                if task_id in self.cancelled:
                    return
                manager.stores.resolve(str(manager.directory(run['id']).parent))
                manager.update(run, integrity={**run['integrity'], 'state': 'running', 'started_at': now()})
                argv = [sys.executable, '-m', 'qualidock.integrity_worker', '--config', str(directory / 'config.json'), '--output', str(directory / 'result.json')]
                execution = {'argv': argv, 'started_at': now(), 'finished_at': None, 'exit_code': None}
                command = asyncio.create_task(manager.executor.execute(task_id, argv, directory, directory / 'validation.log', 1))
                last = None
                while not command.done():
                    path = directory / 'result.json'
                    if path.exists() and task_id not in self.cancelled:
                        stamp = path.stat().st_mtime_ns
                        if stamp != last:
                            result = await asyncio.to_thread(self.read, path)
                            manager.update(run, integrity={**run['integrity'], **result, 'current_file': result.get('current_file'), 'state': 'running', 'execution': execution})
                            last = stamp
                    await asyncio.wait({command}, timeout=.5)
                code = await command
                execution.update(exit_code=code, finished_at=now(), resources=getattr(manager.executor, 'observations', {}).get(task_id))
                if task_id in self.cancelled:
                    return
                result = await asyncio.to_thread(self.read, directory / 'result.json') if (directory / 'result.json').exists() else {}
                complete = code == 0 and result.get('finished_at') and len(result.get('files', [])) == len(config['files'])
                final = {**run['integrity'], **result, 'execution': execution, 'current_file': None,
                                               'state': 'completed' if complete else 'failed',
                                               'result': result.get('result', 'not_evaluated') if complete else 'not_evaluated',
                                               'error': None if complete else f'Integrity worker exited {code} without complete coverage', 'finished_at': now()}
                save_json(directory / 'validation.json', final)
                manager.update(run, integrity=final)
        except Exception as exc:
            if task_id not in self.cancelled:
                try:
                    final = {**run['integrity'], 'state': 'failed', 'result': 'not_evaluated', 'error': str(exc), 'finished_at': now(), 'current_file': None}
                    save_json(directory / 'validation.json', final)
                    manager.update(run, integrity=final)
                except (OSError, ValueError):
                    run['integrity'].update(state='failed', result='not_evaluated', error=str(exc), finished_at=now())
                    manager.revision += 1
        finally:
            if command and not command.done():
                await manager.executor.cancel(task_id)
                await asyncio.gather(command, return_exceptions=True)
            try:
                manager.refresh_reports(run)
            except (OSError, ValueError):
                pass
            self.tasks.pop(run['id'], None)

    async def cancel(self, run_id, state='cancelled'):
        run = self.manager.runs[run_id]
        record = run.get('integrity')
        if not record or record.get('state') not in ACTIVE:
            return record
        self.cancelled.add(record['task_id'])
        await self.manager.executor.cancel(record['task_id'])
        result = deepcopy(record)
        result.update(state=state, result='not_evaluated', error='Scan stopped before full validation completed', finished_at=now())
        if result.get('current_file'):
            result['current_file']['state'] = 'not_evaluated'
        save_json(self.manager.directory(run_id) / record['artifact'], result)
        self.manager.update(run, integrity=result)
        self.manager.refresh_reports(run)
        return result

    async def close(self):
        for run_id in list(self.tasks):
            try:
                await self.cancel(run_id, 'interrupted')
            except (OSError, ValueError):
                record = self.manager.runs[run_id]['integrity']
                self.cancelled.add(record['task_id'])
                await self.manager.executor.cancel(record['task_id'])
                record.update(state='interrupted', result='not_evaluated', finished_at=now())
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
