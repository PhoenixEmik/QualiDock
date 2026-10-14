from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import uuid
import zipfile

from .config import Settings
from .executor import Executor, LocalExecutor
from .files import FileAccess, FASTQ, PathViolation
from .metrics import parse_report

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

    def create(self, name: str, mode: str, raw_paths: list[str], threads: int):
        if self.closing:
            raise ValueError("Session is stopping")
        if self.settings.memory_mb < 1024:
            raise ValueError("Allocate at least 1024 MB to start an analysis")
        if threads > self.settings.max_threads:
            raise ValueError(f"This session allows at most {self.settings.max_threads} analysis threads")
        if len([r for r in self.runs.values() if r["state"] in ACTIVE]) >= 20:
            raise ValueError("The analysis queue is full")
        paths = list(dict.fromkeys(self.files.resolve(p) for p in raw_paths))
        if not paths or len(paths) > 500 or any(not p.is_file() for p in paths):
            raise ValueError("Select between 1 and 500 input files")
        if mode == "multiqc":
            if any(not (p.name.endswith("_fastqc.zip") or p.name == "fastqc_data.txt") for p in paths):
                raise ValueError("MultiQC-only accepts existing FastQC ZIPs or fastqc_data.txt files")
        else:
            if any(not FASTQ.search(p.name) for p in paths):
                raise ValueError("FastQC requires .fastq, .fq, .fastq.gz, or .fq.gz files")
            stems = [FASTQ.sub("", p.name) for p in paths]
            if len(stems) != len(set(stems)):
                raise ValueError("Input filenames must have unique FASTQ stems to avoid output collisions")
        for tool in ([self.settings.fastqc] if mode == "fastqc" else [self.settings.multiqc] if mode == "multiqc" else [self.settings.fastqc, self.settings.multiqc]):
            if shutil.which(tool) is None:
                raise ValueError(f"QC tool is unavailable: {Path(tool).name}. Install it or configure its executable path.")
        run_id = uuid.uuid4().hex
        directory = self.settings.output / run_id
        directory.mkdir(mode=0o700)
        for sub in ("fastqc", "multiqc", "inputs"):
            (directory / sub).mkdir(mode=0o700)
        (directory / "analysis.log").touch(mode=0o600)
        run = {"schema_version": 1, "id": run_id, "name": name.strip() or "Untitled analysis", "mode": mode,
               "state": "queued", "stage": "Waiting for resources", "created_at": now(), "updated_at": now(),
               "started_at": None, "finished_at": None, "threads": threads, "inputs": [str(p) for p in paths],
               "input_metadata": [{"path": str(p), "size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns} for p in paths],
               "progress": 0, "error": None, "warnings": [], "reports": [], "sample_count": 0}
        self.runs[run_id] = run
        self.update(run)
        self.tasks[run_id] = asyncio.create_task(self.execute(run))
        return run

    def checked_inputs(self, run):
        paths = []
        for metadata in run["input_metadata"]:
            path = self.files.resolve(metadata["path"])
            stat = path.stat()
            if not path.is_file() or stat.st_size != metadata["size"] or stat.st_mtime_ns != metadata["mtime_ns"]:
                raise ValueError(f"Input changed while queued: {path.name}")
            paths.append(path)
        return paths

    async def execute(self, run):
        run_id = run["id"]
        directory = self.directory(run_id)
        metrics = {"schema_version": 1, "samples": []}
        errors = []
        try:
            async with self.slot:
                if run_id in self.cancelled:
                    return
                self.update(run, state="running", stage="Preparing inputs", started_at=now())
                paths = self.checked_inputs(run)
                if run["mode"] != "multiqc":
                    self.update(run, stage="FastQC", progress=10)
                    command = [self.settings.fastqc, "--outdir", str(directory / "fastqc"), "--threads", str(run["threads"]), "--memory", "512", "--format", "fastq", *map(str, paths)]
                    code = await self.executor.execute(run_id, command, directory, directory / "analysis.log", run["threads"])
                    if code:
                        errors.append(f"FastQC exited with code {code}. See analysis log.")
                    reports = sorted((directory / "fastqc").glob("*_fastqc.zip"))
                else:
                    reports = []
                    for index, path in enumerate(paths):
                        # Copy only selected report files; never recursively scan user directories or follow their symlinks.
                        destination = directory / "inputs" / str(index)
                        destination.mkdir()
                        target = destination / path.name
                        shutil.copyfile(path, target)
                        reports.append(target)
                for path in reports:
                    try:
                        metrics["samples"].append(parse_report(path, str(path.relative_to(directory))))
                    except (ValueError, OSError, zipfile.BadZipFile, UnicodeError) as exc:
                        errors.append(f"Cannot parse {path.name}: {exc}")
                save_json(directory / "metrics.json", metrics)
                self.update(run, sample_count=len(metrics["samples"]), progress=65)
                if run_id in self.cancelled:
                    return
                if run["mode"] != "fastqc":
                    if not reports:
                        errors.append("No FastQC reports were produced for MultiQC.")
                    else:
                        self.update(run, stage="MultiQC", progress=75)
                        scan = directory / ("inputs" if run["mode"] == "multiqc" else "fastqc")
                        code = await self.executor.execute(run_id, [self.settings.multiqc, str(scan), "--outdir", str(directory / "multiqc"), "--force", "--data-format", "json", "--no-version-check"], directory, directory / "analysis.log", run["threads"])
                        if code:
                            errors.append(f"MultiQC exited with code {code}. See analysis log.")
                        elif not (directory / "multiqc/multiqc_report.html").is_file():
                            errors.append("MultiQC did not produce an HTML report.")
                if run_id in self.cancelled:
                    return
                if len(metrics["samples"]) != len(paths):
                    errors.append(f"Parsed {len(metrics['samples'])} of {len(paths)} expected FastQC results.")
                state = "partial" if errors and metrics["samples"] else "failed" if errors else "completed"
                self.update(run, state=state, stage="Finished", progress=100, finished_at=now(), error=" ".join(errors) or None)
        except Exception as exc:
            if run_id not in self.cancelled:
                self.update(run, state="partial" if metrics["samples"] else "failed", stage="Stopped", error=str(exc), finished_at=now())
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
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(directory.resolve()) and path.suffix in allowed and "inputs" not in path.relative_to(directory).parts:
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
