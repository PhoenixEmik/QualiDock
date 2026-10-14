import asyncio
from abc import ABC, abstractmethod
import os
from pathlib import Path
import signal
import sys


class Executor(ABC):
    @abstractmethod
    async def execute(self, run_id: str, argv: list[str], cwd: Path, log: Path, cpus: int) -> int: ...

    @abstractmethod
    async def cancel(self, run_id: str) -> None: ...


class LocalExecutor(Executor):
    def __init__(self, memory_mb: int):
        self.memory_mb = memory_mb
        self.processes: dict[str, asyncio.subprocess.Process] = {}
        self.cancelled: set[str] = set()

    async def execute(self, run_id, argv, cwd, log, cpus):
        if run_id in self.cancelled:
            return 130
        env = os.environ.copy()
        env.update({k: str(cpus) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")})
        # Do not leak the web session credential into analysis subprocesses.
        env.pop("QUALIDOCK_TOKEN", None)
        env.pop("password", None)  # OOD exports the connection password too.
        with log.open("ab", buffering=0) as output:
            output.write(("\n$ " + repr(argv) + "\n").encode())
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "qualidock.worker", str(cpus), str(os.getpid()), *argv,
                cwd=cwd, env=env, stdout=output, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
            self.processes[run_id] = process
            waiter = asyncio.create_task(process.wait())
            try:
                if run_id in self.cancelled:
                    await self.cancel(run_id)
                    return 130
                while process.returncode is None:
                    rss = await self.group_memory(process.pid)
                    if rss > self.memory_mb * 1024 * 1024:
                        output.write(b"\nResource limit exceeded: analysis process tree used too much memory.\n")
                        await self.cancel(run_id)
                        return 137
                    try:
                        return await asyncio.wait_for(asyncio.shield(waiter), timeout=0.5)
                    except asyncio.TimeoutError:
                        pass
                return await process.wait()
            finally:
                # A tool exiting must not leave a background descendant running.
                await self.stop_group(run_id)
                await waiter
                self.processes.pop(run_id, None)

    @staticmethod
    async def group_memory(group: int) -> int:
        if sys.platform == "linux":
            total = 0
            page_size = os.sysconf("SC_PAGE_SIZE")
            for path in Path("/proc").glob("[0-9]*/stat"):
                try:
                    fields = path.read_text().rsplit(")", 1)[1].split()
                    if int(fields[2]) == group:  # state, ppid, pgrp ... rss
                        total += int(fields[21]) * page_size
                except (OSError, ValueError, IndexError):
                    continue
            return total
        process = await asyncio.create_subprocess_exec("ps", "-axo", "pgid=,rss=", stdout=asyncio.subprocess.PIPE)
        stdout, _ = await process.communicate()
        total = 0
        for line in stdout.decode().splitlines():
            fields = line.split()
            if len(fields) == 2 and int(fields[0]) == group:
                total += int(fields[1]) * 1024
        return total

    async def cancel(self, run_id):
        self.cancelled.add(run_id)
        await self.stop_group(run_id)

    async def stop_group(self, run_id):
        process = self.processes.get(run_id)
        if process is None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(asyncio.shield(process.wait()), timeout=3)
        except asyncio.TimeoutError:
            pass
        # Kill the entire group, including children that outlive the parent.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
