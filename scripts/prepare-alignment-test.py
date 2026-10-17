#!/usr/bin/env python3
"""Explicit test-fixture generation only; never invoked by the application."""
import argparse
from pathlib import Path
import shutil
import subprocess


def prepare(directory, samtools='samtools'):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1]/'backend/tests/fixtures/samtools-1.22.1'
    reference = directory/'reference.fa'
    shutil.copyfile(fixtures/'reference.fa', reference)
    def command(*args):
        subprocess.run([samtools, *map(str, args)], check=True, capture_output=True)
    command('faidx', reference)
    bam, cram = directory/'input.bam', directory/'input.cram'
    command('view', '-b', '-o', bam, fixtures/'input.sam')
    command('view', '-C', '-T', reference, '-o', cram, fixtures/'input.sam')
    return bam, cram, reference


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samtools', default='samtools')
    args = parser.parse_args()
    prepare(args.output, args.samtools)
