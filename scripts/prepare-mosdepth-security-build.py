#!/usr/bin/env python3
"""Test-build-only instrumentation; never changes mosdepth's QC algorithms."""
import json
from pathlib import Path
import sys


def prepare(root):
    root = Path(root).resolve()
    library = root/'samtools-1.24/htslib-1.24'/('libhts.dylib' if sys.platform == 'darwin' else 'libhts.so')
    if not library.is_file():
        raise ValueError('Build the authenticated HTSlib 1.24 shared library first')
    bindings = root/'hts-nim-0.3.31/src/hts/private/hts_concat.nim'
    original = bindings.read_text()
    name = '"libhts.dylib"' if sys.platform == 'darwin' else '"libhts.so"'
    if original.count(name) != 1:
        raise ValueError('Unexpected hts-nim library-loading source')
    bindings.write_text(original.replace(name, json.dumps(str(library))))
    source = root/'mosdepth-0.3.14/mosdepth.nim'
    original = source.read_text()
    before = 'let version = "mosdepth 0.3.14"'
    if original.count(before) != 1:
        raise ValueError('Unexpected mosdepth version-reporting source')
    source.write_text(original.replace(before, 'let version = "mosdepth 0.3.14\\nUsing htslib " & htslibVersion()'))


if __name__ == '__main__':
    prepare(sys.argv[1])
