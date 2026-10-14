#!/usr/bin/env python3
"""Create small deterministic synthetic FASTQs; never replace an existing file."""
import argparse
import gzip
from pathlib import Path
import random

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path("example-data"))
parser.add_argument("--reads", type=int, default=5000)
args = parser.parse_args()
if not 1 <= args.reads <= 100000:
    parser.error("--reads must be between 1 and 100000")
args.output.mkdir(parents=True, exist_ok=True)
randomizer = random.Random(42)
for sample in ("pilot_01", "pilot_02", "pilot_03"):
    for read in (1, 2):
        path = args.output / f"{sample}_R{read}_001.fastq.gz"
        if path.exists():
            continue
        with path.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            for index in range(args.reads):
                sequence = "".join(randomizer.choices("ACGT", k=150))
                qualities = "".join(chr(33 + randomizer.randint(28 if read == 2 and base > 120 else 32, 40)) for base in range(150))
                compressed.write(f"@{sample}:{index}/{read}\n{sequence}\n+\n{qualities}\n".encode())
        print(path)
