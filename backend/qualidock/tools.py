"""Bounded, asynchronous runtime detection; never installs or changes tools."""
import asyncio
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
from .files import approved_file


PROBE_TIMEOUT = 10
RSEQC_ENV = {'PYTHONPATH':'', 'PYTHONHOME':'', 'PYTHONNOUSERSITE':'1', 'PYTHONSAFEPATH':'1'}
# Explicit probes prevent new tools inheriting MultiQC's compatibility rules.
TOOL_SPECS = {
    'fastqc': ('--version', (0, 12, 1), (0, 14, 0), '0.12.1–0.13.x'),
    'multiqc': ('--version', (1, 25, 0), (2, 0, 0), '1.25 or newer, below 2'),
    'fastp': ('--version', (0, 23, 0), (2, 0, 0), '0.23 or newer, below 2'),
    'seqkit': ('version', (2, 6, 0), (3, 0, 0), '2.6 or newer, below 3'),
    'nanoq': ('--version', (0, 10, 0), (0, 10, 1), 'tested nanoq 0.10.0'),
    'nanoplot': (None, (1, 48, 0), (1, 48, 1), 'tested NanoPlot 1.48.0'),
    'mosdepth': ('--version', (0, 3, 14), (0, 3, 15), 'mosdepth 0.3.14 with verified HTSlib 1.24 version reporting'),
    'samtools': ('--version', (1, 24, 0), (1, 24, 1), 'qualified SAMtools 1.24 / HTSlib 1.24'),
    'rseqc_infer': ('--version', (5, 5, 0), (5, 5, 1), 'RSeQC 5.0.5 (CLI 5.05)'),
    'rseqc_distribution': ('--version', (5, 5, 0), (5, 5, 1), 'RSeQC 5.0.5 (CLI 5.05)'),
    'rseqc_genebody': ('--version', (5, 5, 0), (5, 5, 1), 'RSeQC 5.0.5 (CLI 5.05)'),
    'java': ('--version', (17, 0, 0), (18, 0, 0), 'qualified Java 17'),
    'picard': ('--version', (3, 5, 0), (3, 5, 1), 'qualified Picard 3.5.0 JAR'),
    'fastq_screen': ('--version', (0, 16, 0), (0, 17, 0), 'FastQ Screen 0.16.x'),
    'bowtie2': ('--version', (2, 4, 0), (3, 0, 0), 'Bowtie2 2.4 or newer, below 3'),
    'falco': ('--version', (2, 0, 3), (2, 1, 0), 'Falco 2.0.3–2.0.x'),
}


def nanoplot_metadata_probe(path):
    """Older CLI imports can install Chrome even for --version: never run them."""
    with Path(path).open('rb') as stream:
        script = stream.read(4096).decode('utf-8')
    if not script.startswith('#!') or 'from nanoplot.NanoPlot import main' not in script:
        raise ValueError('Configure the standard NanoPlot Python console entrypoint; shell/binary wrappers are not safely probed')
    command = shlex.split(script.splitlines()[0][2:])
    if len(command) == 2 and command[0] == '/usr/bin/env':
        command = command[1:]
    if len(command) != 1 or not re.fullmatch(r'python(?:[0-9.]+)?', Path(command[0]).name):
        raise ValueError('NanoPlot requires a standard Python console entrypoint')
    interpreter = shutil.which(command[0])
    if not interpreter:
        raise ValueError('NanoPlot Python interpreter is unavailable')
    # Preserve the venv interpreter path (do not resolve its binary symlink).
    return [interpreter, '-I', '-c', "from importlib.metadata import version; print('NanoPlot ' + version('NanoPlot'))"]


def locate_tool(name, executable):
    # A JAR is a readable input to Java, not an executable shell launcher.
    located = shutil.which(executable, mode=os.R_OK if name == 'picard' else os.F_OK | os.X_OK)
    return str(Path(located).absolute()) if located and Path(located).is_file() else None


async def version_response(argv, env):
    """Bound both subprocesses and output, including dependency-only probes."""
    process = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True, env=env)
    try:
        async def output():
            chunks, size = [], 0
            while chunk := await process.stdout.read(min(4096, 16385-size)):
                size += len(chunk)
                if size > 16384:
                    raise ValueError('Version response exceeds 16 KiB')
                chunks.append(chunk)
            await process.wait()
            return b''.join(chunks).decode('utf-8', errors='replace').strip()
        return await asyncio.wait_for(output(), timeout=PROBE_TIMEOUT), process.returncode
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


async def rseqc_dependencies(path, env):
    # Inspect the configured script's own Python environment, never the web
    # server's pysam or an unrelated samtools executable on PATH.
    with Path(path).open('rb') as stream:
        first = stream.readline(4097).decode('utf-8').strip()
    if len(first) > 4096 or not first.startswith('#!'):
        raise ValueError('RSeQC requires a Python console script with an inspectable interpreter')
    command = shlex.split(first[2:])
    if len(command) == 2 and command[0] == '/usr/bin/env':
        command = command[1:]
    if len(command) != 1 or not re.fullmatch(r'python(?:[0-9.]+)?', Path(command[0]).name):
        raise ValueError('RSeQC requires a standard Python console script')
    interpreter = shutil.which(command[0])
    if not interpreter:
        raise ValueError('RSeQC Python interpreter is unavailable')
    code = "import json,pysam;from importlib.metadata import version;print(json.dumps({'rseqc':version('RSeQC'),'pysam':version('pysam'),'htslib':pysam.__htslib_version__}))"
    response, status = await version_response([interpreter, '-I', '-c', code], env)
    if status:
        raise ValueError('Cannot verify HTSlib in the configured RSeQC Python environment')
    data = json.loads(response)
    if data != {'rseqc':'5.0.5', 'pysam':'0.24.1', 'htslib':'1.24'}:
        raise ValueError('RSeQC requires qualified RSeQC 5.0.5 / pysam 0.24.1 / HTSlib 1.24')
    return {'python_executable':interpreter, 'pysam_version':data['pysam'], 'htslib_version':data['htslib']}


async def detect_tool(name: str, executable: str, *, java='java') -> dict:
    probe, minimum, maximum, expected = TOOL_SPECS[name]
    path = locate_tool(name, executable)
    result = {"name": name, "executable": path or executable, "available": bool(path), "compatible": False, "version": None, "error": None}
    if not path:
        result["error"] = "Picard JAR is unavailable. Configure QUALIDOCK_PICARD with the original readable JAR." if name == "picard" else f"{name} is unavailable. Configure its executable path or load it on PATH."
        return result
    try:
        env = os.environ.copy()
        for key in ("QUALIDOCK_TOKEN", "password"):
            env.pop(key, None)
        if name.startswith('rseqc_'):
            env.update(RSEQC_ENV)
        if name in {'java','picard'}:
            for key in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS'):
                env.pop(key,None)
        argv = nanoplot_metadata_probe(path) if name == 'nanoplot' else [path, probe]
        if name == 'picard':
            approved_file(Path(path))
            if not path.lower().endswith('.jar'):
                raise ValueError('Configure the original Picard JAR, not a shell launcher')
            runtime = locate_tool('java',java)
            if runtime is None:raise ValueError('Picard requires an existing Java 17 executable')
            result['java_executable'] = runtime
            result['rscript_executable'] = shutil.which('Rscript')
            argv = [runtime,'-Xms32m','-Xmx128m','-XX:ActiveProcessorCount=1','-XX:-UsePerfData','-jar',path,'CollectInsertSizeMetrics','--version']
        if name == 'nanoplot':
            result['version_source'] = 'Python distribution metadata without importing NanoPlot'
        response, status = await version_response(argv, env)
        label = {'fastq_screen': r'FastQ Screen', 'bowtie2': r'bowtie2(?:-align-[sl])?'}.get(name, re.escape(name))
        match = re.search(r"(?i)\b" + label + r"(?:,?\s+(?:version|v))?\s*([0-9]+(?:\.[0-9]+){1,2})\b", response)
        if name == 'nanoplot':
            # Do not truncate e.g. 1.48.1rc1 to 1.48 and admit an untested build.
            match = re.fullmatch(r'NanoPlot\s+([0-9]+\.[0-9]+\.[0-9]+)', response, re.IGNORECASE)
        if name == 'mosdepth':
            match = re.fullmatch(r'mosdepth ([0-9]+\.[0-9]+\.[0-9]+)\nUsing htslib 1\.24', response)
        if name == 'samtools':
            match = re.match(r'samtools (1\.24)\nUsing htslib 1\.24(?:\n|$)', response)
        if name.startswith('rseqc_'):
            script = {'rseqc_infer':'infer_experiment', 'rseqc_distribution':'read_distribution', 'rseqc_genebody':'geneBody_coverage'}[name]
            if name == 'rseqc_genebody': result['rscript_executable'] = shutil.which('Rscript')
            match = re.fullmatch(re.escape(script)+r'\.py (5\.05)', response)
            if match: result['suite_version'] = '5.0.5'
        if name == 'java':
            match = re.search(r'(?m)^(?:openjdk|java)(?: version)?\s+"?([0-9]+(?:\.[0-9]+){1,3})(?:[" +\s]|$)', response)
        if name == 'picard':
            match = re.fullmatch(r'Version:([0-9]+\.[0-9]+\.[0-9]+)',response)
            result['version_probe_exit_code'] = status
        if name == 'falco' and not match:
            match = re.fullmatch(r'([0-9]+(?:\.[0-9]+){1,2})', response)
        if status != (1 if name == 'picard' else 0) or not match:
            raise ValueError(f"Cannot detect {name} version (exit {status}); expected {expected}: {response[:300]}")
        result["version"] = match[1]
        version = tuple(int(part) for part in match[1].split("."))
        version = (*version, *([0] * (3 - len(version))))
        result["compatible"] = minimum <= version < maximum
        if not result["compatible"]:
            result["error"] = f"Unsupported {name} version {match[1]}; expected {expected}."
        if name in {'samtools', 'mosdepth'}:
            if response.splitlines().count('Using htslib 1.24') != 1 or len(re.findall(r'(?m)^Using htslib ', response)) != 1:
                raise ValueError('Ambiguous HTSlib version response')
            result['htslib_version'] = '1.24'
        if name.startswith('rseqc_') and result['compatible']:
            result.update(await rseqc_dependencies(path, env))
    except (OSError, ValueError, TypeError, asyncio.TimeoutError) as exc:
        result.update(compatible=False, error=str(exc) or f"{name} version detection timed out.")
    return result
