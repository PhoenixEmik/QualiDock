import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import secrets
from .resources import cgroup_limits


def available_cpus() -> int:
    limits = [len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)]
    for key in ("QUALIDOCK_CPUS", "PBS_NP", "NCPUS", "SLURM_CPUS_PER_TASK"):
        if os.environ.get(key):
            limits.append(max(1, int(os.environ[key])))
    quota = cgroup_limits()["cpus"]
    if quota is not None:
        limits.append(quota)
    return min(limits)


def available_memory_mb() -> int:
    # Reserve capacity for the web server. The scheduler/cgroup remains the hard boundary.
    limits = [int(os.environ.get("QUALIDOCK_MEMORY_MB", "4096"))]
    try:
        limits.append(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") // (1024 * 1024))
    except (ValueError, OSError):
        pass
    memory = cgroup_limits()["memory_mb"]
    if memory is not None:
        limits.append(memory)
    return min(limits)


@dataclass
class Settings:
    roots: list[Path]
    output: Path
    frontend: Path
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    prefix: str = ""
    cpus: int = field(default_factory=available_cpus)
    memory_mb: int = field(default_factory=available_memory_mb)
    fastqc: str = "fastqc"
    multiqc: str = "multiqc"
    output_roots: list[Path] = field(default_factory=list)
    secure_cookie: bool = False
    allow_root: bool = False  # Only injected by tests; never exposed as a production option.
    fastp: str = "fastp"
    seqkit: str = "seqkit"
    nanoq: str = "nanoq"
    @property
    def max_threads(self) -> int:
        return max(1, min(self.cpus, (self.memory_mb - 512) // 768, 32))

    @classmethod
    def from_env(cls):
        project = Path(__file__).resolve().parents[2]
        roots = json.loads(os.environ.get("QUALIDOCK_ROOTS", json.dumps([str(project / "example-data")])))
        prefix = os.environ.get("QUALIDOCK_PREFIX", "").rstrip("/")
        if prefix and (not prefix.startswith("/") or ".." in prefix or any(c in prefix for c in "?#\\")):
            raise ValueError("QUALIDOCK_PREFIX must be a URL path such as /node/host/port")
        return cls(
            roots=[Path(root).expanduser().resolve(strict=True) for root in roots],
            output=Path(os.environ.get("QUALIDOCK_OUTPUT", project / "runs")).expanduser().resolve(),
            output_roots=[Path(root).expanduser().absolute() for root in json.loads(os.environ.get("QUALIDOCK_OUTPUT_ROOTS", "[]"))],
            frontend=Path(os.environ.get("QUALIDOCK_FRONTEND", project / "frontend/dist")).resolve(),
            token=os.environ.get("QUALIDOCK_TOKEN") or secrets.token_urlsafe(32),
            prefix=prefix, secure_cookie=os.environ.get("QUALIDOCK_SECURE_COOKIE") == "1",
            fastqc=os.environ.get("QUALIDOCK_FASTQC", "fastqc"),
            multiqc=os.environ.get("QUALIDOCK_MULTIQC", "multiqc"),
            fastp=os.environ.get("QUALIDOCK_FASTP", "fastp"),
            seqkit=os.environ.get("QUALIDOCK_SEQKIT", "seqkit"),
            nanoq=os.environ.get("QUALIDOCK_NANOQ", "nanoq"),
        )
