#!/usr/bin/env python3
"""Explicit test-only construction of two tiny, labeled synthetic reference indexes."""
import argparse
from pathlib import Path
import shutil
import subprocess


def prepare(output, builder):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    fixture = Path(__file__).resolve().parents[1] / 'backend/tests/fixtures/fastq-screen-0.16.0'
    executable = shutil.which(builder)
    if not executable:
        raise ValueError('Actual bowtie2-build required')
    for name in ('alpha', 'beta'):
        source = output / (name+'.fasta')
        shutil.copyfile(fixture/source.name, source)
        with (output/(name+'.build.log')).open('w') as log:
            subprocess.run([executable, str(source), str(output/name)], stdout=log, stderr=log, check=True)
    config = output/'panel.conf'
    config.write_text(''.join(f'DATABASE\t{name}\t{output/name}\n' for name in ('alpha','beta')))
    print(config)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--builder', default='bowtie2-build')
    args = parser.parse_args()
    prepare(args.output, args.builder)
