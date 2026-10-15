#!/usr/bin/env python3
"""Actual Linux tool/process validation. Never replaces RSS, affinity or QC executables."""
import argparse
import asyncio
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

from qualidock.config import Settings
from qualidock.executor import LocalExecutor
from qualidock.manager import RunManager
from qualidock.resources import cgroup_limits


def group_snapshot(group):
    result = []
    for stat in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = stat.read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) != group or fields[0] in {'Z', 'X'}:
                continue
            pid = int(stat.parent.name)
            argv = (stat.parent / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            result.append({'pid': pid, 'state': fields[0], 'rss_bytes': int(fields[21]) * os.sysconf('SC_PAGE_SIZE'), 'affinity': sorted(os.sched_getaffinity(pid)), 'command': argv})
        except (OSError, ValueError, IndexError):
            continue
    return result


async def until(predicate, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(0.05)
    raise AssertionError('Timed out waiting for real process/lifecycle condition')


async def observe(manager, run, tool):
    def found():
        process = manager.executor.processes.get(run['id'])
        if not process:
            return None
        snapshot = group_snapshot(process.pid)
        for item in snapshot:
            command = item['command']
            real = 'java' in Path(command[0]).name if tool == 'fastqc' else 'qualidock.worker' not in command and any(Path(arg).name == 'multiqc' for arg in command)
            if real:
                assert all(len(p['affinity']) <= run['threads'] for p in snapshot), snapshot
                return {'group': process.pid, 'processes': snapshot}
        return None
    return await until(found)


async def main(output):
    assert sys.platform == 'linux' and os.geteuid() != 0, 'Run as an ordinary Linux user'
    assert shutil.which('fastqc') and shutil.which('multiqc'), 'Install actual QC tools before validation'
    evidence = {'environment': {'kernel': platform.release(), 'platform': platform.platform(), 'uid': os.getuid(), 'affinity': sorted(os.sched_getaffinity(0)), 'cgroup': Path('/proc/self/cgroup').read_text(), 'limits': cgroup_limits()}, 'checks': {}}
    output.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='qualidock-linux-') as temporary:
            directory = Path(temporary)
            inputs = directory / 'inputs'; inputs.mkdir()
            fixture_root = Path(__file__).resolve().parents[1] / 'backend/tests/fixtures/fastqc-0.13.0'
            small = inputs / 'small.fastq.gz'; shutil.copyfile(fixture_root / 'coverage_R1.fastq.gz', small)
            large = inputs / 'long.fastq.gz'
            # Small on disk but slow enough to observe and cancel genuine Java processing.
            record = b'@QUALIDOCK:1:FLOWCELL:1:1101:1000:1 1:N:0:ACGT\n' + b'ACGT' * 37 + b'AC\n+\n' + b'I' * 150 + b'\n'
            with gzip.open(large, 'wb', compresslevel=1) as stream:
                for _ in range(1000): stream.write(record * 1000)
            original = {p.name: (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in (small, large)}
            settings = Settings(roots=[inputs], output=directory/'results', frontend=directory/'frontend', cpus=1, memory_mb=1024)
            manager = RunManager(settings); manager.start()
            try:
                evidence['tools'] = await manager.detect_tools()
                first = await manager.create('Cancel actual FastQC', 'fastqc', [str(large)], 1)
                observed = await observe(manager, first, 'fastqc')
                following = await manager.create('Queued after cancellation', 'fastqc', [str(small)], 1)
                assert following['state'] == 'queued'
                task = manager.tasks[first['id']]
                await manager.cancel(first['id']); await task
                await until(lambda: not group_snapshot(observed['group']), 10)
                await until(lambda: following['id'] not in manager.tasks)
                assert first['state'] == 'cancelled' and following['state'] == 'completed', following
                evidence['checks']['fastqc_cancel_and_queue'] = {'observation': observed, 'state': first['state'], 'following_state': following['state'], 'executions': following['executions']}
                aggregate = await manager.create('Cancel actual MultiQC', 'multiqc', [str(manager.directory(following['id'])/'fastqc')], 1, source_run_id=following['id'])
                observed = await observe(manager, aggregate, 'multiqc')
                task = manager.tasks[aggregate['id']]
                await manager.cancel(aggregate['id']); await task
                await until(lambda: not group_snapshot(observed['group']), 10)
                assert aggregate['state'] == 'cancelled'
                evidence['checks']['multiqc_cancel'] = {'observation': observed, 'state': aggregate['state']}
                broken = inputs/'broken.fastq'; broken.write_text('@broken\nACGT\n+\n')
                invalid = await manager.create('Malformed input', 'fastqc', [str(broken)], 1)
                await until(lambda: invalid['id'] not in manager.tasks)
                evidence['checks']['malformed_input'] = {'state': invalid['state'], 'error': invalid['error']}
                assert invalid['state'] == 'failed' and following['state'] == 'completed', evidence['checks']['malformed_input']
                limited = LocalExecutor(64)
                code = await limited.execute('over-budget', [sys.executable, '-c', 'import time; data=bytearray(192*1024*1024); time.sleep(30)'], directory, output/'memory-overrun.log', 1)
                assert code == 137 and limited.observations['over-budget']['peak_sampled_rss_bytes'] > 64*1024*1024
                assert await limited.execute('after-overrun', [sys.executable, '-c', 'print("healthy after memory failure")'], directory, output/'memory-overrun.log', 1) == 0
                evidence['checks']['memory_overrun'] = {'exit_code': code, **limited.observations['over-budget']}
                slow = await manager.create('Graceful shutdown', 'fastqc', [str(large)], 1)
                observed = await observe(manager, slow, 'fastqc')
                queued = await manager.create('Queued at shutdown', 'fastqc', [str(small)], 1)
                await manager.close()
                await until(lambda: not group_snapshot(observed['group']), 10)
                assert slow['state'] == queued['state'] == 'interrupted'
                recovered = RunManager(settings); recovered.start()
                assert recovered.runs[following['id']]['state'] == 'completed'
                assert recovered.runs[slow['id']]['state'] == 'interrupted'
                await recovered.close()
                evidence['checks']['graceful_shutdown_and_restart'] = {'observation': observed, 'running': slow['state'], 'queued': queued['state'], 'historical': 'completed'}
                # Separate actual server parent: SIGKILL must activate the worker guardian.
                abrupt = directory/'abrupt'; abrupt.mkdir()
                parent_code = '''import asyncio,json,sys
from pathlib import Path
from qualidock.config import Settings
from qualidock.manager import RunManager
async def main():
 base=Path(sys.argv[1]); source=Path(sys.argv[2])
 manager=RunManager(Settings(roots=[source.parent],output=base/'results',frontend=base/'frontend',cpus=1,memory_mb=1024));manager.start()
 run=await manager.create('Abrupt parent death','fastqc',[str(source)],1)
 while run['id'] not in manager.executor.processes: await asyncio.sleep(0.02)
 (base/'started.json').write_text(json.dumps({'run_id':run['id'],'group':manager.executor.processes[run['id']].pid}))
 await asyncio.Event().wait()
asyncio.run(main())
'''
                with (output/'abrupt-parent.log').open('w') as log:
                    parent = subprocess.Popen([sys.executable, '-c', parent_code, str(abrupt), str(large)], stdout=log, stderr=log)
                    try:
                        await until(lambda: (abrupt/'started.json').is_file())
                        started = json.loads((abrupt/'started.json').read_text())
                        await until(lambda: any('java' in Path(item['command'][0]).name for item in group_snapshot(started['group'])))
                        before = group_snapshot(started['group'])
                        parent.kill(); await asyncio.to_thread(parent.wait, 10)
                        await until(lambda: not group_snapshot(started['group']), 10)
                        restored = RunManager(Settings(roots=[inputs],output=abrupt/'results',frontend=abrupt/'frontend',cpus=1,memory_mb=1024)); restored.start()
                        assert restored.runs[started['run_id']]['state'] == 'interrupted'
                        await restored.close()
                        evidence['checks']['guardian_and_abrupt_recovery'] = {'observation': before, 'state': 'interrupted', 'live_group_members_after': []}
                    finally:
                        if parent.poll() is None: parent.kill(); parent.wait(timeout=10)
                assert original == {p.name: (p.stat().st_size,p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()) for p in (small,large)}
                evidence['checks']['inputs_unchanged'] = True
                await asyncio.to_thread(subprocess.run, [sys.executable, str(Path(__file__).with_name('benchmark-analysis.py')), '--input', str(small), '--output', str(output/'benchmark-smoke'), '--mode', 'fastqc', '--threads', '1', '--memory-mb', '1024'], check=True)
                measured = json.loads((output/'benchmark-smoke/benchmark.json').read_text())
                assert measured['input_integrity_unchanged'] and measured['run']['state'] == 'completed'
                evidence['checks']['benchmark_command_smoke'] = 'passed'
                for run in manager.runs.values():
                    source = manager.directory(run['id'])
                    target = output/run['id']; target.mkdir()
                    for name in ('manifest.json','analysis.log'):
                        shutil.copyfile(source/name, target/name)
            finally:
                await manager.close()
        evidence['status'] = 'passed'
    except Exception as exc:
        evidence['status'] = 'failed'; evidence['error'] = repr(exc)
        raise
    finally:
        (output/'linux-execution.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print('QUALIDOCK_LINUX_EVIDENCE=' + json.dumps(evidence))
    print('PASS: actual Linux FastQC/Java/MultiQC affinity, cancellation, queue recovery, RSS limit, graceful shutdown, guardian and persisted history')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    asyncio.run(main(parser.parse_args().output))
