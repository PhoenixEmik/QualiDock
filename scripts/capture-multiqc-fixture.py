#!/usr/bin/env python3
"""Generate a small genuine MultiQC General Statistics fixture from public synthetic inputs."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess

from qualidock.metrics import parse_multiqc

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
inputs = root / 'backend/tests/fixtures/fastqc-0.13.0'
args.output.mkdir(parents=True, exist_ok=True)
listing = args.output.resolve() / 'input-reports.txt'
reports = sorted(inputs.glob('*_fastqc/fastqc_data.txt'))
assert len(reports) == 2
listing.write_text(''.join(str(path) + '\n' for path in reports))
version = subprocess.check_output(['multiqc', '--version'], text=True).strip()
match = re.search(r'version\s+(\d+(?:\.\d+)+)', version)
assert match, version
command = ['multiqc', '--file-list', str(listing), '--outdir', str(args.output.resolve()), '--force', '--data-format', 'json', '--no-version-check']
subprocess.run(command, check=True)
original = args.output / 'multiqc_data/multiqc_data.json'
raw = json.loads(original.read_text())
# Copy the actual JSON subtrees verbatim in value; exclude paths, timestamps, plots and HTML.
fixture = {key: raw[key] for key in ('config_version', 'report_general_stats_headers', 'report_general_stats_data')}
path = args.output / f'multiqc-{match[1]}-general-stats.json'
path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
parsed = parse_multiqc(path)
assert parsed['status'] == 'available' and len(parsed['rows']) == 2, parsed
assert {row['sample'] for row in parsed['rows']} == {'coverage_R1', 'coverage_R2'}, parsed
provenance = {'multiqc_version': match[1], 'fastqc_version': '0.13.0', 'command': 'multiqc --file-list input-reports.txt --outdir OUTPUT --force --data-format json --no-version-check', 'inputs': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in reports}, 'fixture_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
(args.output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
print('QUALIDOCK_FIXTURE_BASE64=' + base64.b64encode(path.read_bytes()).decode())
print('QUALIDOCK_FIXTURE_PROVENANCE=' + json.dumps(provenance))
print(f'PASS: genuine MultiQC {match[1]} General Statistics contain two distinct read files')
