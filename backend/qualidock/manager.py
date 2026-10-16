from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import re
from copy import deepcopy
import uuid
import zipfile

from .config import Settings
from .executor import Executor, LocalExecutor
from .files import FileAccess, FASTQ, PathViolation
from .metrics import parse_report, parse_multiqc
from .import_formats import fastp_metadata, source_mappings
from .reports import discover, metadata
from .tools import detect_tool
from . import processing, datasets
from .store import ResultStores, now, save_json
from .sample_metadata import validate_configuration
from .outcomes import plan, batches, stop, counts

ACTIVE = {"queued", "running"}
TERMINAL = {"completed", "failed", "partial", "cancelled", "interrupted"}




class RunManager:
    def __init__(self, settings: Settings, executor: Executor | None = None):
        self.settings = settings
        self.files = FileAccess(settings.roots)
        self.stores = ResultStores(settings.output, settings.output_roots)
        self.executor = executor or LocalExecutor(max(256, settings.memory_mb - 256))
        self.runs: dict[str, dict] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.cancelled: set[str] = set()
        self.lock = None
        self.slot = asyncio.Semaphore(1)
        self.revision = 0
        self.closing = False
        self.tool_info = {}
        self.tool_lock = asyncio.Lock()
        self.tool_signature = None
        self.tool_checked_at = 0.0
        from .validation_jobs import ValidationJobs
        self.validation = ValidationJobs(self)

    def start(self):
        self.stores.start()
        self.lock = self.stores.locks[self.stores.default]
        try:
            for root in self.stores.roots:
                for path in root.glob("*/manifest.json"):
                    if path.is_symlink() or path.parent.is_symlink():
                        continue
                    try:
                        run = json.loads(path.read_text())
                        if run["id"] != path.parent.name or not re.fullmatch('[a-f0-9]{32}', run['id']):
                            continue
                        if run.get('output_directory', str(path.parent)) != str(path.parent):
                            continue
                        if run['id'] in self.runs:
                            raise RuntimeError('Duplicate analysis ID in configured result stores')
                        self.stores.paths[run['id']] = path.parent
                        self.stores.directory(run['id'])
                        from .validation_jobs import interrupted
                        recovered_validation = interrupted(run)
                        if run["state"] in ACTIVE:
                            if run.get('processing'):
                                run['derived_datasets'] = []
                                for unit in run['processing']['units']:
                                    if unit['state'] in ACTIVE: unit.update(state='interrupted', error='Previous session ended')
                            run.update(state="interrupted", finished_at=now(), stage="Session ended", error="The previous web session ended before this analysis finished.")
                            stop(run.get('input_outcomes', []), 'interrupted', 'Previous session ended before a complete outcome was recorded')
                            save_json(path, run)
                        elif recovered_validation:
                            save_json(path, run)
                        self.runs[run["id"]] = run
                    except (OSError, ValueError, KeyError):
                        continue
        except Exception:
            self.stores.close()
            raise

    def directory(self, run_id: str) -> Path:
        if run_id not in self.runs:
            raise KeyError(run_id)
        return self.stores.directory(run_id)

    def update(self, run: dict, **changes):
        updated = {**run, **changes, "updated_at": now()}
        try:
            self.stores.resolve(str(self.directory(run['id']).parent))
            save_json(self.directory(run["id"]) / "manifest.json", updated)
        except OSError as exc:
            raise PathViolation('Cannot persist analysis metadata: output location is unavailable or unwritable') from exc
        run.update(updated)
        self.revision += 1

    def list(self):
        return sorted(self.runs.values(), key=lambda r: r["created_at"], reverse=True)

    async def detect_tools(self):
        signature = []
        for name in (self.settings.fastqc, self.settings.multiqc, self.settings.fastp, self.settings.seqkit):
            executable = shutil.which(name)
            try:
                stat = Path(executable).stat() if executable else None
                signature.append((name, executable, stat.st_mtime_ns if stat else None))
            except OSError:
                signature.append((name, None, None))
        async with self.tool_lock:
            if signature != self.tool_signature or time.monotonic() - self.tool_checked_at >= 60:
                names = ("fastqc", "multiqc", "fastp", "seqkit")
                detected = await asyncio.gather(*(detect_tool(name, getattr(self.settings, name)) for name in names))
                self.tool_info = dict(zip(names, detected))
                self.tool_signature = signature
                self.tool_checked_at = time.monotonic()
        return self.tool_info

    def input_access(self, source_run_id=None):
        if source_run_id:
            source = self.runs[source_run_id]
            if source["state"] in ACTIVE:
                raise ValueError("Wait until the source analysis finishes")
            directory = self.directory(source_run_id)
            fastqc = directory / "fastqc"
            if fastqc.is_symlink() or not fastqc.resolve().is_relative_to(directory.resolve()):
                raise PathViolation("Saved FastQC directory is unavailable")
            return FileAccess([fastqc])
        return self.files

    async def create(self, name: str, mode: str, raw_paths: list[str], threads: int, source_run_id=None, *, input_pairing=None, sample_groups=None, output_root=None, rerun_of=None, processing_options=None, input_datasets=None):
        if mode not in {'both', 'fastqc', 'multiqc', *processing.MODES}:
            raise ValueError('Invalid analysis mode')
        operation_options = processing.options(mode, processing_options)
        if self.closing:
            raise ValueError("Session is stopping")
        if self.settings.memory_mb < 1024:
            raise ValueError("Allocate at least 1024 MB to start an analysis")
        if threads < 1 or threads > self.settings.max_threads:
            raise ValueError(f"This session allows at most {self.settings.max_threads} analysis threads")
        if len([r for r in self.runs.values() if r["state"] in ACTIVE]) >= 20:
            raise ValueError("The analysis queue is full")
        await self.detect_tools()
        if rerun_of:
            previous = self.runs[rerun_of]
            if previous.get('source_run_id') and mode == 'multiqc' and raw_paths == previous['inputs']:
                source_run_id = previous['source_run_id']
            if raw_paths == previous['inputs'] and input_datasets is None:
                input_datasets = previous.get('input_datasets')
        access = self.input_access(source_run_id)
        if mode == 'multiqc' and input_datasets:
            raise ValueError('Derived FASTQs are inputs for QC or processing, not existing-report imports')
        derived = datasets.registered(self, input_datasets)
        paths = list(dict.fromkeys(datasets.resolve(self, p, derived) if not source_run_id else access.resolve(p) for p in raw_paths))
        if set(derived) - set(map(str, paths)):
            raise ValueError('Derived dataset references must belong to the selected inputs')
        if not paths or len(paths) > 500:
            raise ValueError("Select between 1 and 500 inputs")
        report_inputs = []
        import_summary = {}
        supplied_pairing = input_pairing
        input_pairing = []
        normalized_groups = []
        pairing_note = None
        if mode == "multiqc":
            try:
                report_inputs = await asyncio.to_thread(discover, paths, access, import_summary)
            except OSError as exc:
                raise ValueError(f"Cannot read QC report inputs: {exc.strerror or exc}") from exc
        else:
            if any(not p.is_file() or not FASTQ.search(p.name) for p in paths):
                raise ValueError("FastQC requires .fastq, .fq, .fastq.gz, or .fq.gz files")
            configuration = await asyncio.to_thread(self.sample_configuration, paths, supplied_pairing, sample_groups, input_datasets)
            input_pairing = configuration['input_pairing'] if not configuration.get('pairing_note') or supplied_pairing is not None else []
            normalized_groups = configuration['sample_groups']
            pairing_note = configuration.get('pairing_note')
        sample_input_paths = [str(path) for path in paths] if mode != 'multiqc' else []
        if mode == 'multiqc' and source_run_id:
            source = self.runs[source_run_id]
            input_pairing = deepcopy(source.get('input_pairing', []))
            normalized_groups = deepcopy(source.get('sample_groups', []))
            sample_input_paths = source.get('sample_input_paths', source['inputs'])
        operation_units = processing.units({'mode': mode, 'inputs': list(map(str, paths)), 'input_pairing': input_pairing}, operation_options) if mode in processing.MODES else []
        required = processing.required(mode, operation_options, operation_units) if mode in processing.MODES else ["fastqc"] if mode == "fastqc" else ["multiqc"] if mode == "multiqc" else ["fastqc", "multiqc"]
        for tool in required:
            info = self.tool_info.get(tool)
            executable = getattr(self.settings, tool)
            if shutil.which(executable) is None:
                raise ValueError(f"QC tool is unavailable: {Path(executable).name}. Install it or configure its executable path.")
            if info and not info["compatible"]:
                raise ValueError(info["error"])
        processing.check_features(mode, operation_options, self.tool_info)
        if self.closing or len([r for r in self.runs.values() if r["state"] in ACTIVE]) >= 20:
            raise ValueError("Session is stopping or the analysis queue is full")
        run_id = uuid.uuid4().hex
        directory = self.stores.allocate(run_id, output_root)
        for sub in ("fastqc", "multiqc", "inputs"):
            (directory / sub).mkdir(mode=0o700)
        (directory / "analysis.log").touch(mode=0o600)
        default_name = (mode + ' · ' + paths[0].name)[:120] if mode in processing.MODES else 'Untitled analysis'
        default_name = ''.join(character for character in default_name if ord(character) >= 32)
        run = {"schema_version": 2, "id": run_id, "name": name.strip() or default_name, "mode": mode,
               "state": "queued", "stage": "Waiting for resources", "created_at": now(), "updated_at": now(),
               "started_at": None, "finished_at": None, "threads": threads, "inputs": [str(p) for p in paths],
               "input_metadata": [{**metadata(p), "kind": "directory" if p.is_dir() else "file", "device": p.stat().st_dev, "inode": p.stat().st_ino} for p in paths],
               "input_pairing": input_pairing, "sample_groups": normalized_groups, "input_datasets": deepcopy(input_datasets or []),
               "input_provenance": list(derived.values()), "sample_input_paths": sample_input_paths,
               "input_outcomes": plan(paths) if mode not in {'multiqc', *processing.MODES} else [], "report_input_map": {},
               "output_root": str(directory.parent), "output_directory": str(directory), "rerun_of": rerun_of,
               "pairing_note": pairing_note,
               "report_inputs": report_inputs, "import_summary": import_summary, "source_run_id": source_run_id, "tools": {tool: dict(self.tool_info.get(tool, {})) for tool in required},
               "executions": [], "parameters": {"threads": threads, "memory_mb": self.settings.memory_mb, "executor": "local"},
               "progress": 0, "error": None, "warnings": [], "reports": [], "sample_count": 0}
        if mode in processing.MODES:
            run['processing'] = {'schema_version': 1, 'options': operation_options, 'units': operation_units, 'quality_encoding': 'Phred+33' if mode == 'fastp' else None}
            run['derived_datasets'] = []
        self.runs[run_id] = run
        self.update(run)
        self.tasks[run_id] = asyncio.create_task(self.execute(run))
        return run

    @staticmethod
    def readable_fastq(path):
        if not path.is_file() or not FASTQ.search(path.name) or not path.stat().st_mode & 0o444 or not os.access(path, os.R_OK):
            raise ValueError(f'FASTQ is unavailable or unreadable: {path.name}')
        with path.open('rb') as stream:
            stream.read(0)

    def sample_configuration(self, raw_paths, pairing=None, groups=None, input_datasets=None):
        derived = datasets.registered(self, input_datasets)
        paths = [datasets.resolve(self, str(path), derived) for path in raw_paths]
        if set(derived) - set(map(str, paths)):
            raise ValueError('Derived references must be selected')
        if not paths or len(paths) > 500 or len(set(paths)) != len(paths):
            raise ValueError('Select 1–500 distinct FASTQ files')
        for path in paths:
            self.readable_fastq(path)
        note = None
        try:
            automatic = self.files.pairing([p for p in paths if str(p) not in derived]) + datasets.pairing(derived)
        except (OSError, ValueError):
            automatic = [{'path': str(path), 'name': path.name, 'paired': False, 'read': None, 'mate': None, 'pair_key': None} for path in paths]
            note = 'Automatic pairing unavailable. Review manual assignments or analyze reads individually.'
        allowed = {str(path) for path in paths}
        for record in automatic:
            if record['path'] not in derived: record['source'] = 'auto'
            if record.get('mate') not in allowed:
                record.update(paired=False, mate=None, pair_key=None)
        # Normalize only file references, never reinterpret user relationship metadata.
        if pairing is not None:
            pairing = deepcopy(pairing)
            for record in pairing:
                if isinstance(record, dict):
                    for key in ('path', 'mate'):
                        if record.get(key): record[key] = str(datasets.resolve(self, record[key], derived))
        if groups is not None:
            groups = deepcopy(groups)
            for group in groups:
                if isinstance(group, dict) and isinstance(group.get('files'), list):
                    group['files'] = [str(datasets.resolve(self, path, derived)) for path in group['files']]
        detected_groups = None
        if derived:
            ordinary = [p for p in paths if str(p) not in derived]
            detected_groups = (validate_configuration(ordinary, [r for r in automatic if r['path'] not in derived])['sample_groups'] if ordinary else []) + datasets.groups(self, derived)
        result = validate_configuration(paths, automatic, pairing, groups, detected_groups=detected_groups)
        result['pairing_note'] = note
        return result

    def rename(self, run_id, name):
        name = name.strip()
        if not name or len(name) > 120 or any(ord(c) < 32 for c in name):
            raise ValueError('Analysis names must contain 1–120 printable characters')
        run = self.runs[run_id]
        self.update(run, name=name)
        return run

    def configuration(self, run_id):
        run = self.runs[run_id]
        access = self.input_access(run.get('source_run_id'))
        derived = datasets.registered(self, run.get('input_datasets'))
        paths = [datasets.resolve(self, path, derived) if not run.get('source_run_id') else access.resolve(path) for path in run['inputs']]
        entries = []
        for path in paths:
            if run['mode'] != 'multiqc': self.readable_fastq(path)
            entry = access._entry(path.parent, path.name)
            if not entry: raise ValueError('An original input is unavailable')
            entries.append(entry)
        self.stores.resolve(str(self.directory(run_id).parent))
        return {'name': (run['name'] + ' · rerun')[:120], 'mode': run['mode'], 'paths': [str(path) for path in paths], 'entries': entries,
                'threads': min(run.get('threads', 1), self.settings.max_threads), 'input_pairing': run.get('input_pairing') or None,
                'sample_groups': run.get('sample_groups') or None, 'output_root': str(self.directory(run_id).parent), 'rerun_of': run_id,
                'processing_options': deepcopy(run.get('processing', {}).get('options')), 'input_datasets': [{'run_id': row['run_id'], 'dataset_id': row['dataset_id'], 'path': path} for path, row in derived.items()]}

    def checked_inputs(self, run):
        paths = []
        access = self.input_access(run.get("source_run_id"))
        derived = datasets.registered(self, run.get('input_datasets'))
        for metadata in run["input_metadata"]:
            path = datasets.resolve(self, metadata['path'], derived) if not run.get('source_run_id') else access.resolve(metadata['path'])
            if metadata.get("kind") == "directory":
                if not path.is_dir():
                    raise ValueError("Input directory is unavailable")
                paths.append(path)
                continue
            self.readable_fastq(path) if run['mode'] != 'multiqc' else None
            stat = path.stat()
            if not path.is_file() or stat.st_size != metadata["size"] or stat.st_mtime_ns != metadata["mtime_ns"] or any(key in metadata and getattr(stat, attribute) != metadata[key] for key, attribute in (("device", "st_dev"), ("inode", "st_ino"))):
                raise ValueError(f"Input changed while queued: {path.name}")
            paths.append(path)
        return paths

    async def command(self, run, tool, argv, directory):
        execution = {"tool": tool, "argv": argv, "started_at": now(), "finished_at": None, "exit_code": None}
        run.setdefault("executions", []).append(execution)
        self.update(run)
        try:
            code = await self.executor.execute(run["id"], argv, directory, directory / "analysis.log", run["threads"])
            execution["exit_code"] = code
            return code
        finally:
            execution["finished_at"] = now()
            observation = getattr(self.executor, "observations", {}).get(run["id"])
            if observation:
                execution["resources"] = dict(observation)
            self.update(run)

    async def fastqc_results(self, run, records, metrics, errors, stage=None):
        """Shared FastQC batches/parser; caller owns the existing run resource slot."""
        run_id, directory = run["id"], self.directory(run["id"])
        parsed_by_path = {}
        for batch in batches(records):
            if run_id in self.cancelled:
                break
            destination = self.stores.subdirectory(run_id, batch[0]['output_directory'], exist_ok=True)
            for record in batch:
                record.update(state='unknown', error='Submitted to FastQC; individual start is not reported by the tool')
            completed = counts(records)['completed']
            self.update(run, stage=f"FastQC · {completed} of {len(records)} inputs completed")
            command = [run["tools"]["fastqc"]["executable"], "--outdir", str(destination), "--threads", str(run["threads"]), "--memory", "512", "--format", "fastq", *[record['path'] for record in batch]]
            code = await self.command(run, "fastqc", command, directory)
            if code and run_id not in self.cancelled:
                errors.append(f"FastQC exited with code {code}. See analysis log.")
            for record in batch:
                record.update(exit_code=code, finished_at=now())
                path = directory / record['report']
                try:
                    if path.is_symlink() or not path.resolve().is_relative_to(directory):
                        raise ValueError('FastQC artifact escaped its output directory')
                    sample = await asyncio.to_thread(parse_report, path, record['report'])
                    if sample['name'] != record['name']:
                        raise ValueError('FastQC reported filename does not match the original input')
                    record.update(state='completed', error=None)
                    parsed_by_path[path] = sample
                    metrics['samples'].append(sample)
                    run['report_input_map'][sample['id']] = {'path': record['path'], 'id': record['id'], **({'processing_stage': stage} if stage else {})}
                except (ValueError, OSError, zipfile.BadZipFile, UnicodeError, RuntimeError, NotImplementedError) as exc:
                    if run_id in self.cancelled:
                        record.update(state='interrupted' if run['state'] == 'interrupted' else 'cancelled', error='Tool stopped before a usable report was recorded')
                    else:
                        record.update(state='failed', error=f'No usable FastQC result: {exc}')
                        errors.append(f"{record['name']} ({record['id']}): {record['error']}")
            await asyncio.to_thread(save_json, directory / 'metrics.json', metrics)
            self.update(run, sample_count=len(metrics['samples']), stage=f"FastQC · {len(metrics['samples'])} of {len(records)} inputs completed")
            self.refresh_reports(run)
        return parsed_by_path

    async def execute(self, run):
        run_id = run["id"]
        directory = self.stores.paths[run_id]
        metrics = {"schema_version": 2, "samples": []}
        errors = []
        try:
            async with self.slot:
                if run_id in self.cancelled:
                    return
                self.update(run, state="running", stage="Preparing inputs", started_at=now())
                tools = await self.detect_tools()
                required = processing.required(run["mode"], run["processing"]["options"], run["processing"]["units"]) if run.get("processing") else ["fastqc"] if run["mode"] == "fastqc" else ["multiqc"] if run["mode"] == "multiqc" else ["fastqc", "multiqc"]
                self.update(run, tools={name: dict(tools[name]) for name in required})
                with (directory / "analysis.log").open("a") as stream:
                    for name in required:
                        stream.write(f"{name}: {tools[name]['version'] or 'version unavailable'} ({tools[name]['executable']})\n")
                        if not tools[name]["compatible"]:
                            raise ValueError(tools[name]["error"])
                if run.get('processing'):
                    processing.check_features(run['mode'], run['processing']['options'], tools)
                    await processing.execute(self, run, metrics, errors)
                    if run_id not in self.cancelled:
                        completed = any(unit['state'] == 'completed' for unit in run['processing']['units'])
                        self.update(run, state='partial' if completed and errors else 'failed' if errors or not completed else 'completed',
                                    stage='Finished', progress=100, finished_at=now(), error=' '.join(errors) or None)
                    return
                paths = await asyncio.to_thread(self.checked_inputs, run)
                if run_id in self.cancelled:
                    return
                parsed_by_path = {}
                if run["mode"] != "multiqc":
                    parsed_by_path = await self.fastqc_results(run, run['input_outcomes'], metrics, errors)
                    reports = list(parsed_by_path)
                    metrics['samples'] = []  # Reuse the common import/aggregation parser below.
                else:
                    reports = []
                    access = self.input_access(run.get("source_run_id"))
                    records = run.get("report_inputs") or await asyncio.to_thread(discover, paths, access)
                    def snapshot():
                        for index, record in enumerate(records):
                            destination = directory / "inputs" / str(index)
                            destination.mkdir()
                            for entry in [record, *record.get("companions", [])]:
                                source = access.resolve(entry["path"])
                                if source.is_symlink() or metadata(source) != {key: entry[key] for key in ("path", "size", "mtime_ns")}:
                                    raise ValueError(f"Input changed while queued: {source.name}")
                                copied = destination / source.name
                                shutil.copyfile(source, copied)
                                if metadata(source) != {key:entry[key] for key in ('path','size','mtime_ns')} or copied.stat().st_size != entry['size']:
                                    raise ValueError('QC report changed during snapshot')
                                if entry is record:
                                    with copied.open('rb') as stream:
                                        record['snapshot_sha256'] = hashlib.file_digest(stream,'sha256').hexdigest()
                                    record['snapshot_artifact'] = str(copied.relative_to(directory))
                            report = destination / Path(record["path"]).name
                            run['report_input_map'][str(report.relative_to(directory))] = {'source_report': record['path'], 'id': 'report_' + hashlib.sha256(record['path'].encode()).hexdigest()[:24]}
                            if run.get('source_run_id'):
                                source_run = self.runs[run['source_run_id']]
                                source_report = str(Path(record['path']).relative_to(self.directory(source_run['id'])))
                                mapping = source_run.get('report_input_map', {}).get(source_report)
                                if mapping:
                                    run['report_input_map'][str(report.relative_to(directory))] = {key: value for key, value in mapping.items() if key != 'multiqc_name'}
                            reports.append(report)
                    await asyncio.to_thread(snapshot)
                successful = []
                imported_fastp = {}
                sample_names = set()
                multiqc_names = {}
                namespaced = False
                for path in reports:
                    try:
                        if path.suffix.lower() == '.json':
                            details = await asyncio.to_thread(fastp_metadata,path)
                            imported_fastp[str(path.relative_to(directory))] = details
                            successful.append(path)
                            continue
                        sample = parsed_by_path.get(path) or await asyncio.to_thread(parse_report, path, str(path.relative_to(directory)))
                        metrics["samples"].append(sample)
                        sample_name = FASTQ.sub("", sample["name"])
                        namespaced = namespaced or sample_name in sample_names
                        successful.append(path)
                        sample_names.add(sample_name)
                        multiqc_names[sample['id']] = sample_name
                    except (ValueError, OSError, zipfile.BadZipFile, UnicodeError, RuntimeError, NotImplementedError) as exc:
                        errors.append(f"Cannot parse {path.name}: {exc}")
                await asyncio.to_thread(save_json, directory / "metrics.json", metrics)
                self.update(run, sample_count=len(metrics["samples"]), warnings=[warning for sample in metrics["samples"] for warning in sample.get("warnings", [])])
                if run_id in self.cancelled:
                    return
                if run["mode"] != "fastqc":
                    if not successful:
                        errors.append("No supported QC reports were produced for MultiQC.")
                    else:
                        self.stores.subdirectory(run_id, "multiqc", exist_ok=True)
                        self.update(run, stage="MultiQC")
                        # An explicit list includes only successfully parsed, run-local QC reports.
                        file_list = directory / "multiqc-inputs.txt"
                        if any("\n" in str(path) or "\r" in str(path) for path in successful):
                            raise ValueError("MultiQC report paths cannot contain newlines")
                        file_list.write_text("".join(str(path) + "\n" for path in successful))
                        extra_options = []
                        if imported_fastp:
                            # fastp defaults to names parsed from upstream commands.
                            # Use physical report filenames and per-snapshot directories
                            # to prevent unrelated reports being silently overwritten.
                            config = directory / 'multiqc-import-config.json'
                            save_json(config, {'use_filename_as_sample_name':['fastp']})
                            extra_options = ['--config',str(config),'--dirs','--dirs-depth','1','--fullnames']
                        if namespaced and not imported_fastp:
                            multiqc_names = {str(path.relative_to(directory)): path.parent.name + " | " + multiqc_names[str(path.relative_to(directory))] for path in successful}
                            if len(set(multiqc_names.values())) != len(successful):
                                raise ValueError("MultiQC sample namespaces are ambiguous; individual FastQC results are preserved")
                        code = await self.command(run, "multiqc", [run["tools"]["multiqc"]["executable"], "--file-list", str(file_list), "--outdir", str(directory / "multiqc"), "--force", "--data-format", "json", "--no-version-check", *extra_options, *(["--dirs", "--dirs-depth", "1"] if namespaced and not imported_fastp else [])], directory)
                        if code:
                            errors.append(f"MultiQC exited with code {code}. See analysis log.")
                        elif not (directory / "multiqc/multiqc_report.html").is_file():
                            errors.append("MultiQC did not produce an HTML report.")
                if run_id in self.cancelled:
                    return
                structured = directory / "multiqc/multiqc_data/multiqc_data.json"
                if run["mode"] != "fastqc":
                    if not structured.exists():
                        metrics["multiqc"] = {"status": "missing", "message": "MultiQC structured JSON was not generated; inspect the log and official report.", "columns": [], "rows": []}
                    else:
                        try:
                            metrics["multiqc"] = await asyncio.to_thread(parse_multiqc, structured)
                        except (ValueError, OSError, UnicodeError, TypeError) as exc:
                            metrics["multiqc"] = {"status": "invalid", "message": f"Cannot parse MultiQC General Statistics: {exc}", "columns": [], "rows": []}
                    if metrics["multiqc"]["status"] != "available":
                        run["warnings"].append(metrics["multiqc"]["message"])
                if run['mode'] != 'fastqc' and metrics.get('multiqc', {}).get('status') == 'available':
                    actual_names = {row['sample'] for row in metrics['multiqc']['rows']}
                    if imported_fastp:
                        source_names = await asyncio.to_thread(source_mappings,structured)
                        multiqc_names = {}
                        for path in successful:
                            report = str(path.relative_to(directory))
                            names = source_names.get(str(path), set()) & actual_names
                            if len(names) == 1:
                                multiqc_names[report] = next(iter(names))
                            else:
                                errors.append(f'MultiQC did not provide an unambiguous data-source mapping for {report}')
                    for report, name in multiqc_names.items():
                        if name in actual_names and report in run['report_input_map']:
                            run['report_input_map'][report]['multiqc_name'] = name
                    missing = set(multiqc_names.values()) - actual_names
                    if missing:
                        errors.append('MultiQC omitted expected report samples: ' + ', '.join(sorted(missing)))
                await asyncio.to_thread(save_json, directory / "metrics.json", metrics)
                expected = sum(record.get("kind","fastqc") == "fastqc" for record in run.get("report_inputs", [])) if run["mode"] == "multiqc" else len(paths)
                if len(metrics["samples"]) != expected:
                    errors.append(f"Parsed {len(metrics['samples'])} of {expected} expected FastQC results.")
                if imported_fastp and not all(run.get('report_input_map',{}).get(report,{}).get('multiqc_name') for report in imported_fastp):
                    errors.append('Some imported fastp sources have no verified MultiQC sample mapping; inspect the preserved original reports')
                if run.get('import_summary',{}).get('unsupported_files'):
                    run['warnings'].append(f"Excluded {run['import_summary']['unsupported_files']} unsupported files during bounded report discovery")
                state = "partial" if errors and (metrics["samples"] or metrics.get('multiqc',{}).get('status') == 'available') else "failed" if errors else "completed"
                self.update(run, state=state, stage="Finished", progress=100, finished_at=now(), error=" ".join(errors) or None)
        except Exception as exc:
            if run_id not in self.cancelled:
                changes = dict(state="partial" if metrics["samples"] or any(unit["state"] == "completed" for unit in run.get("processing", {}).get("units", [])) else "failed", sample_count=len(metrics["samples"]), stage="Stopped", error=str(exc), finished_at=now())
                try:
                    self.stores.resolve(str(self.directory(run_id).parent))
                    if metrics["samples"]:
                        await asyncio.to_thread(save_json, directory / "metrics.json", metrics)
                    self.update(run, **changes)
                    with (directory / "analysis.log").open("a") as stream:
                        stream.write(f"\nQualiDock: {exc}\n")
                except (OSError, ValueError):
                    # Surface storage loss in the live UI even when persistence is
                    # impossible. Restart will identify its saved active state.
                    run.update(**changes, updated_at=now())
                    self.revision += 1
        finally:
            if run.get('processing'):
                for unit in run['processing']['units']:
                    if unit['state'] in {'queued', 'running'}:
                        unit.update(state=run['state'] if run['state'] in {'cancelled','interrupted'} else 'failed', error='Processing stopped before completion')
                    for key in ('raw_qc', 'processed_qc'):
                        stop(unit.get(key, []), run['state'], 'Analysis stopped before QC completion')
                if run['state'] in {'cancelled','interrupted','failed'}: run['derived_datasets'] = []
            pending = run.get('input_outcomes', [])
            if any(record['state'] in {'queued', 'unknown', 'running'} for record in pending):
                terminal = run['state'] if run['state'] in {'cancelled', 'interrupted'} else 'unknown'
                stop(pending, terminal, 'No complete per-file outcome was recorded before the analysis stopped')
            try:
                self.refresh_reports(run)
            except (OSError, ValueError):
                run.setdefault('warnings', []).append('Results location is unavailable; artifact indexing could not be persisted.')
                self.revision += 1
            self.tasks.pop(run_id, None)

    def refresh_reports(self, run):
        directory = self.directory(run["id"])
        allowed = {".html", ".zip", ".json", ".log", ".txt", ".tsv", ".csv", ".yaml", ".parquet", ".png", ".svg"}
        reports = []
        registered = {record['path'] for record in run.get('reports', [])}
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(directory.resolve()) and path.suffix in allowed:
                relative = str(path.relative_to(directory))
                if relative.startswith('processing/private/'):
                    continue
                if relative.startswith('processing/'):
                    unit_id = Path(relative).parts[1]
                    if not any(unit['id'] == unit_id and unit['state'] == 'completed' for unit in run.get('processing', {}).get('units', [])):
                        continue
                if '/' in relative and Path(relative).parts[0] not in {'fastqc','multiqc','inputs','integrity','processing'} and relative not in registered:
                    continue  # Historical namespaces remain read-only registered artifacts.
                reports.append({"path": relative, "size": path.stat().st_size})
        self.update(run, reports=reports)

    async def cancel(self, run_id: str):
        run = self.runs[run_id]
        if run["state"] not in ACTIVE:
            return run
        self.cancelled.add(run_id)
        await self.executor.cancel(run_id)
        if run.get('processing'): run['derived_datasets'] = []
        stop(run.get('input_outcomes', []), 'cancelled', 'Analysis cancelled before a complete per-file outcome was recorded')
        self.update(run, state="cancelled", stage="Cancelled", finished_at=now())
        return run

    async def close(self):
        self.closing = True
        unfinished = [(run_id, run) for run_id, run in self.runs.items() if run["state"] in ACTIVE]
        self.cancelled.update(run_id for run_id, _ in unfinished)
        for run_id, run in unfinished:
            await self.executor.cancel(run_id)
            stop(run.get('input_outcomes', []), 'interrupted', 'Session ended before a complete per-file outcome was recorded')
            changes = dict(state="interrupted", stage="Session ended", finished_at=now(), error="The web session ended. Start a new analysis to rerun these inputs.")
            try:
                self.update(run, **changes)
            except (OSError, ValueError):
                run.update(**changes, updated_at=now())
        await self.validation.close()
        if self.tasks:
            await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        self.stores.close()

    def artifact(self, run_id, raw: str):
        run = self.runs[run_id]
        derived = next((entry for entry in run.get('derived_datasets', []) if entry['path'] == raw), None)
        if derived:
            if run['state'] not in {'completed','partial'}: raise PathViolation('Derived dataset is not published')
            path = processing.local_file(self.directory(run_id), raw)
            if processing.snapshot(path.stat()) != derived['snapshot']: raise PathViolation('Derived dataset changed since processing completed')
            return path
        if raw not in {report["path"] for report in run["reports"]}:
            raise PathViolation("File is not a registered result artifact")
        directory = self.directory(run_id)
        path = directory / raw
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(directory.resolve()) or not path.is_file():
            raise PathViolation("Artifact is unavailable")
        return path
