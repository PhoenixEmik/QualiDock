"""Bounded, asynchronous runtime detection; never installs or changes tools."""
import asyncio
import os
from pathlib import Path
import re
import shutil
import signal


PROBE_TIMEOUT = 10
# Explicit probes prevent new tools inheriting MultiQC's compatibility rules.
TOOL_SPECS = {
    'fastqc': ('--version', (0, 12, 1), (0, 14, 0), '0.12.1–0.13.x'),
    'multiqc': ('--version', (1, 25, 0), (2, 0, 0), '1.25 or newer, below 2'),
    'fastp': ('--version', (0, 23, 0), (2, 0, 0), '0.23 or newer, below 2'),
    'seqkit': ('version', (2, 6, 0), (3, 0, 0), '2.6 or newer, below 3'),
    'nanoq': ('--version', (0, 10, 0), (0, 10, 1), 'tested nanoq 0.10.0'),
    'nanoplot': ('--version', (1, 48, 0), (1, 48, 1), 'tested NanoPlot 1.48.0'),
    'fastq_screen': ('--version', (0, 16, 0), (0, 17, 0), 'FastQ Screen 0.16.x'),
    'bowtie2': ('--version', (2, 4, 0), (3, 0, 0), 'Bowtie2 2.4 or newer, below 3'),
    'falco': ('--version', (2, 0, 3), (2, 1, 0), 'Falco 2.0.3–2.0.x'),
}


async def detect_tool(name: str, executable: str) -> dict:
    probe, minimum, maximum, expected = TOOL_SPECS[name]
    located = shutil.which(executable)
    path = str(Path(located).absolute()) if located else None
    result = {"name": name, "executable": path or executable, "available": bool(path), "compatible": False, "version": None, "error": None}
    if not path:
        result["error"] = f"{name} is unavailable. Configure its executable path or load it on PATH."
        return result
    process = None
    try:
        env = os.environ.copy()
        for key in ("QUALIDOCK_TOKEN", "password"):
            env.pop(key, None)
        process = await asyncio.create_subprocess_exec(path, probe, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True, env=env)
        async def output():
            chunks, size = [], 0
            while True:
                chunk = await process.stdout.read(min(4096, 16385 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > 16384:
                    raise ValueError("Version response exceeds 16 KiB")
                chunks.append(chunk)
            await process.wait()
            return b"".join(chunks).decode("utf-8", errors="replace").strip()
        response = await asyncio.wait_for(output(), timeout=PROBE_TIMEOUT)
        label = {'fastq_screen': r'FastQ Screen', 'bowtie2': r'bowtie2(?:-align-[sl])?'}.get(name, re.escape(name))
        match = re.search(r"(?i)\b" + label + r"(?:,?\s+(?:version|v))?\s*([0-9]+(?:\.[0-9]+){1,2})\b", response)
        if name == 'nanoplot':
            # Do not truncate e.g. 1.48.1rc1 to 1.48 and admit an untested build.
            match = re.fullmatch(r'NanoPlot\s+([0-9]+\.[0-9]+\.[0-9]+)', response, re.IGNORECASE)
        if name == 'falco' and not match:
            match = re.fullmatch(r'([0-9]+(?:\.[0-9]+){1,2})', response)
        if process.returncode or not match:
            raise ValueError(f"Cannot detect {name} version (exit {process.returncode}): {response[:300]}")
        result["version"] = match[1]
        version = tuple(int(part) for part in match[1].split("."))
        version = (*version, *([0] * (3 - len(version))))
        result["compatible"] = minimum <= version < maximum
        if not result["compatible"]:
            result["error"] = f"Unsupported {name} version {match[1]}; expected {expected}."
    except (OSError, ValueError, asyncio.TimeoutError) as exc:
        result["error"] = str(exc) or f"{name} version detection timed out."
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
    return result
