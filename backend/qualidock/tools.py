"""Bounded, asynchronous runtime detection; never installs or changes tools."""
import asyncio
import os
from pathlib import Path
import re
import shutil
import signal


PROBE_TIMEOUT = 10


async def detect_tool(name: str, executable: str) -> dict:
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
        process = await asyncio.create_subprocess_exec(path, "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True, env=env)
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
        match = re.search(r"(?i)\b" + (r"kraken(?:2)?" if name == "kraken2" else re.escape(name)) + r"(?:,?\s+(?:version|v))?\s*([0-9]+(?:\.[0-9]+){1,2})\b", response)
        if process.returncode or not match:
            raise ValueError(f"Cannot detect {name} version (exit {process.returncode}): {response[:300]}")
        result["version"] = match[1]
        version = tuple(int(part) for part in match[1].split("."))
        version = (*version, *([0] * (3 - len(version))))
        result["compatible"] = (0, 12, 1) <= version < (0, 14, 0) if name == "fastqc" else (2, 1, 0) <= version < (3, 0, 0) if name == "kraken2" else (1, 25, 0) <= version < (2, 0, 0)
        if not result["compatible"]:
            result["error"] = f"Unsupported {name} version {match[1]}; expected " + ("0.12.1–0.13.x." if name == "fastqc" else "2.1 or newer, below 3." if name == "kraken2" else "1.25 or newer, below 2.")
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
