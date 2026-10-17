"""Verified NanoPlot report adapter; execution remains in the existing QC slot."""
import asyncio
import csv
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, StrictBool

from .processing import local_file


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid')
    loglength: StrictBool = False
    individual_plots: StrictBool = False


def stats(path, source):
    if path.is_symlink() or not path.is_file():
        raise ValueError('NanoStats must be a regular report file')
    with path.open('rb') as stream:
        raw = stream.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024:
        raise ValueError('NanoStats exceeds 128 KiB')
    text = raw.decode('utf-8-sig')
    rows = list(csv.reader(text.splitlines(), delimiter='\t'))
    if not rows or len(rows) > 200 or rows[0] != ['Metrics', 'dataset']:
        raise ValueError('Unsupported NanoStats TSV header')
    rows = rows[1:]
    if any(len(row) != 2 or not row[0] or not row[1] for row in rows):
        raise ValueError('Malformed NanoStats table')
    values = dict(rows)
    if len(values) != len(rows):
        raise ValueError('Duplicate NanoStats metric')
    try:
        for key, expected in [('number_of_reads', source['records_scanned']), ('number_of_bases', source['bases_scanned'])]:
            if Decimal(values[key]) != expected:
                raise ValueError('NanoStats totals differ from fully validated FASTQ')
        for key in ['mean_read_length', 'median_read_length', 'read_length_stdev', 'n50', 'mean_qual', 'median_qual']:
            value = Decimal(values[key])
            if not value.is_finite() or value < 0:
                raise ValueError('Invalid NanoStats numerical metric')
    except (InvalidOperation, KeyError) as exc:
        raise ValueError('Missing or invalid NanoStats numerical metric') from exc
    # Keep original reported precision and compound fields, without recalculation.
    return {'columns': ['Metric', 'Reported value'], 'rows': rows}


async def execute(manager, run, row, source):
    directory = manager.directory(run['id'])
    destination = manager.stores.subdirectory(run['id'], f'qc/{row["id"]}', exist_ok=True)
    opts = run['qc']['options']
    argv = [run['tools']['nanoplot']['executable'], '--threads', str(run['threads']),
            '--fastq', row['path'], '--outdir', str(destination), '--tsv_stats',
            '--plots', 'dot', '--format', 'png', '--no_static', '--include-js', 'embedded']
    # Plotly static export in 1.48 may download Chrome. Never enter that path.
    # Legacy scatter also fails on supported modern seaborn; do not offer it.
    if not opts['individual_plots']:
        argv.append('--only-report')
    if opts['loglength']:
        argv.append('--loglength')
    code = await manager.command(run, 'nanoplot', argv, directory)
    row['exit_code'] = code
    if run['id'] in manager.cancelled:
        return None
    if code:
        raise ValueError(f'NanoPlot exited with code {code}; see analysis log')
    result = await asyncio.to_thread(stats, local_file(directory, row['report']), source)
    html = destination / 'NanoPlot-report.html'
    local_file(directory, str(html.relative_to(directory)))
    # A truncated/empty HTML artifact is not successful report generation.
    with html.open('rb') as stream:
        prefix = stream.read(64 * 1024).lower()
        size = stream.seek(0, 2)
        stream.seek(max(0, size - 4096))
        tail = stream.read(4096).lower()
        if b'<html' not in prefix or b'</html>' not in tail:
            raise ValueError('Missing NanoPlot HTML document')
    result['html'] = str(html.relative_to(directory))
    result['plots'] = [str(p.relative_to(directory)) for p in sorted(destination.glob('*.html'))
                       if p != html and not p.is_symlink() and p.stat().st_size > 0]
    return result
