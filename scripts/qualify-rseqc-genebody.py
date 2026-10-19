#!/usr/bin/env python3
"""Qualify genuine RSeQC geneBody_coverage.py outputs; no application feature yet.

This tool-study creates a TEST-ONLY BAM copy and index. It never writes an
index beside the caller's source alignment or modifies the annotation.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parse_profile(path):
    """Require an unambiguous original 1..100 percentile table."""
    with Path(path).open("rb") as stream:
        payload = stream.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise ValueError("Gene-body percentile report exceeds 1 MiB")
    lines = payload.decode("utf-8").splitlines()
    if len(lines) != 2:
        raise ValueError("Single-input qualification requires header and one sample row")
    header = lines[0].split("\t")
    if header != ["Percentile", *map(str, range(1, 101))]:
        raise ValueError("Unexpected RSeQC percentile positions or number of columns")
    sample = lines[1].split("\t")
    if len(sample) != 101 or not sample[0] or any(c.isspace() for c in sample[0]):
        raise ValueError("Invalid RSeQC sample row/identity")
    try:
        values = [float(v) for v in sample[1:]]
    except ValueError as exc:
        raise ValueError("Invalid RSeQC percentile values") from exc
    if not all(math.isfinite(v) and v >= 0 for v in values):
        raise ValueError("Gene-body coverage must be finite and nonnegative")
    return {"sample": sample[0], "percentiles": 100, "first": sample[1],
            "last": sample[-1], "minimum": min(values), "maximum": max(values),
            "all_zero": not any(values), "raw_sha256": digest(path)}


def checked(command, root, label, timeout):
    execution = subprocess.run(command, text=True, errors="replace",
                               capture_output=True, timeout=timeout, check=False)
    (root / (label + ".stdout.txt")).write_text(execution.stdout)
    (root / (label + ".stderr.txt")).write_text(execution.stderr)
    if execution.returncode:
        raise RuntimeError(f"{label}: upstream tool exited {execution.returncode}; "
                           f"inspect {label}.stderr.txt and {label}.stdout.txt")
    return execution


def qualify(args):
    source = Path(args.bam).resolve(strict=True)
    annotation = Path(args.bed).resolve(strict=True)
    destination = Path(args.output).absolute()
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    original = {"bam": digest(source), "bed": digest(annotation)}
    # Stage only tiny, test-owned input for qualification. User FASTQ/BAM paths
    # are never copied by the actual QualiDock analysis runtime.
    copied = destination / "input.bam"
    shutil.copyfile(source, copied)
    if digest(copied) != original["bam"]:
        raise ValueError("Test-copy BAM differs from original")
    index = destination / "input.bam.bai"
    checked([args.samtools, "index", "-o", str(index), str(copied)],
            destination, "samtools-index", args.timeout)
    if not index.is_file():
        raise ValueError("Samtools produced no index for the test-owned copy")
    probe = checked([args.rseqc, "--version"], destination, "rseqc-version", args.timeout)
    if "geneBody_coverage.py" not in probe.stdout + probe.stderr:
        raise ValueError("Upstream executable identity could not be verified")
    prefix = destination / "gene-body"
    command = [args.rseqc, "-i", str(copied), "-r", str(annotation),
               "-o", str(prefix), "-l", "100", "-f", "png"]
    checked(command, destination, "gene-body", args.timeout)
    report = destination / "gene-body.geneBodyCoverage.txt"
    if not report.is_file():
        raise ValueError("Genuine RSeQC percentile table was not generated")
    profile = parse_profile(report)
    if digest(source) != original["bam"] or digest(annotation) != original["bed"]:
        raise ValueError("Original BAM/BED12 changed during upstream tool qualification")
    evidence = {
        "status": "qualified-percentile-table",
        "scope": "test-only indexed BAM copy; not an integrated QualiDock QC mode",
        "command": command, "input_sha256": original, "test_index": index.name,
        "profile": profile,
        "upstream_plot_files": sorted(p.name for p in destination.glob("gene-body.*")
                                      if p.suffix.lower() in {".png", ".pdf", ".jpeg"}),
        "limitations": [
            "These observations are not large-BAM/NFS/Lustre resource acceptance",
            "An upstream exit code or generated R script is not proof a scientific plot was rendered",
            "The source fixture contains explicit synthetic RNA alignment geometry",
        ],
    }
    (destination / "qualification.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bam", type=Path, required=True)
    parser.add_argument("--bed", type=Path, required=True)
    parser.add_argument("--rseqc", required=True)
    parser.add_argument("--samtools", default="samtools")
    parser.add_argument("--output", type=Path, required=True,
                        help="New private test-evidence directory; never overwrites")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    result = qualify(args)
    print(f"Qualified genuine {result['profile']['percentiles']}-position RSeQC table: "
          f"{args.output}/qualification.json")
