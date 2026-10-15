from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import time
import uuid
import zipfile

from .config import Settings
from .executor import Executor, LocalExecutor
from .files import FileAccess, FASTQ, PathViolation
from .metrics import parse_report, parse_multiqc
from .reports import discover, metadata
from .tools import detect_tool

ACTIVE = {"queued", "running"}
TERMINAL = {"completed", "failed", "partial", "cancelled", "interrupted"}


def now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path: Path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class RunManager:
    def __init__(self, settings: Settings, executor: Executor | None = None):
        self.settings = settings
        self.files = FileAccess(settings.roots)
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

    def start(self):
        self.settings.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = (self.settings.output / ".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.lock.close()
            raise RuntimeError("Another QualiDock session owns this results directory") from exc
        for path in self.settings.output.glob("*/manifest.json"):
            if path.is_symlink() or path.parent.is_symlink():
                continue
            try:
                run = json.loads(path.read_text())
                if run["id"] != path.parent.name or len(run["id"]) != 32:
                    continue
                if run["state"] in ACTIVE:
                    run.update(state="interrupted", finished_at=now(), stage="Session ended",
                               error="The previous web session ended before this analysis finished.")
                    save_json(path, run)
                self.runs[run["id"]] = run
            except (OSError, ValueError, KeyError):
                continue

    def directory(self, run_id: str) -> Path:
        if run_id not in self.runs:
            raise KeyError(run_id)
        directory = self.settings.output / run_id
        if directory.is_symlink() or not directory.resolve().is_relative_to(self.settings.output.resolve()):
            raise PathViolation("Result directory is unavailable")
        return directory

    def update(self, run: dict, **changes):
        run.update(changes, updated_at=now())
        save_json(self.directory(run["id"]) / "manifest.json", run)
        self.revision += 1

    def list(self):
        return sorted(self.runs.values(), key=lambda r: r["created_at"], reverse=True)

    async def detect_tools(self):
        signature = []
        for name in (self.settings.fastqc, self.settings.multiqc):
            executable = shutil.which(name)
            try:
                stat = Path(executable).stat() if executable else None
                signature.append((name, executable, stat.st_mtime_ns if stat else None))
            except OSError:
                signature.append((name, None, None))
        async with self.tool_lock:
            if signature != self.tool_signature or time.monotonic() - self.tool_checked_at >= 60:
                fastqc, multiqc = await asyncio.gather(detect_tool("fastqc", self.settings.fastqc), detect_tool("multiqc", self.settings.multiqc))
                self.tool_info = {"fastqc": fastqc, "multiqc": multiqc}
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

    async def create(self, name: str, mode: str, raw_paths: list[str], threads: int, source_run_id=None):
        if self.closing:
            raise ValueError("Session is stopping")
        if self.settings.memory_mb < 1024:
            raise ValueError("Allocate at least 1024 MB to start an analysis")
        if threads > self.settings.max_threads:
            raise ValueError(f"This session allows at most {self.settings.max_threads} analysis threads")
        if len([r for r in self.runs.values() if r["state"] in ACTIVE]) >= 20:
            raise ValueError("The analysis queue is full")
        await self.detect_tools()
        access = self.input_access(source_run_id)
        paths = list(dict.fromkeys(access.resolve(p) for p in raw_paths))
        if not paths or len(paths) > 500:
            raise ValueError("Select between 1 and 500 inputs")
        report_inputs = []
        input_pairing = []
        pairing_note = None
        if mode == "multiqc":
            try:
                report_inputs = await asyncio.to_thread(discover, paths, access)
            except OSError as exc:
                raise ValueError(f"Cannot read QC report inputs: {exc.strerror or exc}") from exc
        else:
            if any(not p.is_file() or not FASTQ.search(p.name) for p in paths):
                raise ValueError("FastQC requires .fastq, .fq, .fastq.gz, or .fq.gz files")
            stems = [FASTQ.sub("", p.name) for p in paths]
            if len(stems) != len(set(stems)):
                raise ValueError("Input filenames must have unique FASTQ stems to avoid output collisions")
            try:
                input_pairing = await asyncio.to_thread(access.pairing, paths)
            except (ValueError, OSError):
                # Pairing is optional display metadata. A directory index limit
                # or an unavailable mate must not prevent valid FastQC inputs.
                pairing_note = "Pairing could not be confirmed; reads remain available individually."
        required = ["fastqc"] if mode == "fastqc" else ["multiqc"] if mode == "multiqc" else ["fastqc", "multiqc"]
        for tool in required:
            info = self.tool_info.get(tool)
            executable = getattr(self.settings, tool)
            if shutil.which(executable) is None:
                raise ValueError(f"QC tool is unavailable: {Path(executable).name}. Install it or configure its executable path.")
            if info and not info["compatible"]:
                raise ValueError(info["error"])
        if self.closing or len([r for r in self.runs.values() if r["state"] in ACTIVE]) >= 20:
            raise ValueError("Session is stopping or the analysis queue is full")
        run_id = uuid.uuid4().hex
        directory = self.settings.output / run_id
        directory.mkdir(mode=0o700)
        for sub in ("fastqc", "multiqc", "inputs"):
            (directory / sub).mkdir(mode=0o700)
        (directory / "analysis.log").touch(mode=0o600)
        run = {"schema_version": 2, "id": run_id, "name": name.strip() or "Untitled analysis", "mode": mode,
               "state": "queued", "stage": "Waiting for resources", "created_at": now(), "updated_at": now(),
               "started_at": None, "finished_at": None, "threads": threads, "inputs": [str(p) for p in paths],
               "input_metadata": [{**metadata(p), "kind": "directory" if p.is_dir() else "file"} for p in paths],
               "input_pairing": input_pairing,
               "pairing_note": pairing_note,
               "report_inputs": report_inputs, "source_run_id": source_run_id, "tools": {tool: dict(self.tool_info.get(tool, {})) for tool in required},
               "executions": [], "parameters": {"threads": threads, "memory_mb": self.settings.memory_mb, "executor": "local"},
               "progress": 0, "error": None, "warnings": [], "reports": [], "sample_count": 0}
        self.runs[run_id] = run
        self.update(run)
        self.tasks[run_id] = asyncio.create_task(self.execute(run))
        return run

    def checked_inputs(self, run):
        paths = []
        access = self.input_access(run.get("source_run_id"))
        for metadata in run["input_metadata"]:
            path = access.resolve(metadata["path"])
            if metadata.get("kind") == "directory":
                if not path.is_dir():
                    raise ValueError("Input directory is unavailable")
                paths.append(path)
                continue
            stat = path.stat()
            if not path.is_file() or stat.st_size != metadata["size"] or stat.st_mtime_ns != metadata["mtime_ns"]:
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

    async def execute(self, run):
        run_id = run["id"]
        directory = self.directory(run_id)
        metrics = {"schema_version": 2, "samples": []}
        errors = []
        try:
            async with self.slot:
                if run_id in self.cancelled:
                    return
                self.update(run, state="running", stage="Preparing inputs", started_at=now())
                tools = await self.detect_tools()
                required = ["fastqc"] if run["mode"] == "fastqc" else ["multiqc"] if run["mode"] == "multiqc" else ["fastqc", "multiqc"]
                self.update(run, tools={name: dict(tools[name]) for name in required})
                with (directory / "analysis.log").open("a") as stream:
                    for name in required:
                        stream.write(f"{name}: {tools[name]['version'] or 'version unavailable'} ({tools[name]['executable']})\n")
                        if not tools[name]["compatible"]:
                            raise ValueError(tools[name]["error"])
                paths = await asyncio.to_thread(self.checked_inputs, run)
                if run_id in self.cancelled:
                    return
                if run["mode"] != "multiqc":
                    self.update(run, stage="FastQC", progress=10)
                    command = [run["tools"]["fastqc"]["executable"], "--outdir", str(directory / "fastqc"), "--threads", str(run["threads"]), "--memory", "512", "--format", "fastq", *map(str, paths)]
                    code = await self.command(run, "fastqc", command, directory)
                    if code:
                        errors.append(f"FastQC exited with code {code}. See analysis log.")
                    reports = sorted((directory / "fastqc").glob("*_fastqc.zip"))
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
                                shutil.copyfile(source, destination / source.name)
                            reports.append(destination / Path(record["path"]).name)
                    await asyncio.to_thread(snapshot)
                successful = []
                sample_names = set()
                for path in reports:
                    try:
                        sample = await asyncio.to_thread(parse_report, path, str(path.relative_to(directory)))
                        metrics["samples"].append(sample)
                        # MultiQC cleans FASTQ suffixes from sample names. Avoid silently overwriting duplicates.
                        sample_name = FASTQ.sub("", sample["name"])
                        if run["mode"] != "fastqc" and sample_name in sample_names:
                            errors.append(f"Duplicate sample name not aggregated by MultiQC: {sample['name']}")
                        else:
                            successful.append(path)
                            sample_names.add(sample_name)
                    except (ValueError, OSError, zipfile.BadZipFile, UnicodeError, RuntimeError, NotImplementedError) as exc:
                        errors.append(f"Cannot parse {path.name}: {exc}")
                await asyncio.to_thread(save_json, directory / "metrics.json", metrics)
                self.update(run, sample_count=len(metrics["samples"]), warnings=[warning for sample in metrics["samples"] for warning in sample.get("warnings", [])], progress=65)
                if run_id in self.cancelled:
                    return
                if run["mode"] != "fastqc":
                    if not successful:
                        errors.append("No FastQC reports were produced for MultiQC.")
                    else:
                        self.update(run, stage="MultiQC", progress=75)
                        # An explicit list includes only successfully parsed, run-local QC reports.
                        file_list = directory / "multiqc-inputs.txt"
                        if any("\n" in str(path) or "\r" in str(path) for path in successful):
                            raise ValueError("MultiQC report paths cannot contain newlines")
                        file_list.write_text("".join(str(path) + "\n" for path in successful))
                        code = await self.command(run, "multiqc", [run["tools"]["multiqc"]["executable"], "--file-list", str(file_list), "--outdir", str(directory / "multiqc"), "--force", "--data-format", "json", "--no-version-check"], directory)
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
                await asyncio.to_thread(save_json, directory / "metrics.json", metrics)
                expected = len(run.get("report_inputs", [])) if run["mode"] == "multiqc" else len(paths)
                if len(metrics["samples"]) != expected:
                    errors.append(f"Parsed {len(metrics['samples'])} of {expected} expected FastQC results.")
                state = "partial" if errors and metrics["samples"] else "failed" if errors else "completed"
                self.update(run, state=state, stage="Finished", progress=100, finished_at=now(), error=" ".join(errors) or None)
        except Exception as exc:
            if run_id not in self.cancelled:
                if metrics["samples"]:
                    await asyncio.to_thread(save_json, directory / "metrics.json", metrics)
                self.update(run, state="partial" if metrics["samples"] else "failed", sample_count=len(metrics["samples"]), stage="Stopped", error=str(exc), finished_at=now())
                with (directory / "analysis.log").open("a") as stream:
                    stream.write(f"\nQualiDock: {exc}\n")
        finally:
            self.refresh_reports(run)
            self.tasks.pop(run_id, None)

    def refresh_reports(self, run):
        directory = self.directory(run["id"])
        allowed = {".html", ".zip", ".json", ".log", ".txt", ".tsv", ".csv", ".yaml", ".parquet", ".png", ".svg"}
        reports = []
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(directory.resolve()) and path.suffix in allowed:
                reports.append({"path": str(path.relative_to(directory)), "size": path.stat().st_size})
        self.update(run, reports=reports)

    async def cancel(self, run_id: str):
        run = self.runs[run_id]
        if run["state"] not in ACTIVE:
            return run
        self.cancelled.add(run_id)
        await self.executor.cancel(run_id)
        self.update(run, state="cancelled", stage="Cancelled", finished_at=now())
        return run

    async def close(self):
        self.closing = True
        unfinished = [(run_id, run) for run_id, run in self.runs.items() if run["state"] in ACTIVE]
        self.cancelled.update(run_id for run_id, _ in unfinished)
        for run_id, run in unfinished:
            await self.executor.cancel(run_id)
            self.update(run, state="interrupted", stage="Session ended", finished_at=now(), error="The web session ended. Start a new analysis to rerun these inputs.")
        if self.tasks:
            await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        if self.lock:
            self.lock.close()

    def artifact(self, run_id, raw: str):
        run = self.runs[run_id]
        if raw not in {report["path"] for report in run["reports"]}:
            raise PathViolation("File is not a registered result artifact")
        directory = self.directory(run_id)
        path = directory / raw
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(directory.resolve()) or not path.is_file():
            raise PathViolation("Artifact is unavailable")
        return path
