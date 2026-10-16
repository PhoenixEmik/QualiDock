# Authorized large-FASTQ acceptance

Issue #5 requires an actual large dataset on an authorized HPC filesystem. The
small public fixtures and local filename benchmark do not establish 80 GB FASTQ
throughput, NFS/Lustre behavior, or suitable site defaults. No large dataset or
accessible HPC allocation was provided for this validation pass; this gate is
**pending**, and no large-run measurements are asserted.

## Run procedure

Use a regular Unix account inside the intended compute allocation. Load the real
FastQC/MultiQC versions and install QualiDock's existing test extras for TestClient.
Keep the output on private persistent storage with sufficient free space. Enter
actual paths below; no FASTQ is uploaded, moved, or copied into the result store.

```sh
python scripts/benchmark-analysis.py \
  --input /authorized/data/sample_R1.fastq.gz /authorized/data/sample_R2.fastq.gz \
  --output /persistent/private/new-fastqc-benchmark \
  --mode fastqc --threads 4 --memory-mb 8192

python scripts/benchmark-analysis.py \
  --input /authorized/data/sample_R1.fastq.gz /authorized/data/sample_R2.fastq.gz \
  --output /persistent/private/new-combined-benchmark \
  --mode both --threads 4 --memory-mb 8192
```

The resource numbers illustrate command syntax, not recommended HPC defaults.
Requests must fit detected CPU affinity, cgroup and configured allocation limits. Set `QUALIDOCK_MEMORY_MB` to the actual granted allocation before running; the benchmark does not override it.
The output directory must be new. It retains per-run manifests, official reports,
normalized metrics, logs and a `benchmark.json` evidence record. These records can
include input references and scientific summaries: keep them private and redact
site/data identifiers before sharing.

The script measures actual stage changes, wall time, sampled process-group RSS,
CPU ticks, Linux read/write counters, and in-process API latency for job status,
logs and browsing while tools run. CPU/I/O observations can miss final counters
from short-lived processes; RSS is a sampled high-water mark, not an exact peak.
Linux process I/O counters do not measure NFS/Lustre network throughput. Pair
those records with site-approved filesystem monitoring when available.

Input size, mtime, inode and device are checked before/after. `--hash-inputs` adds
streamed SHA-256 validation and two complete source reads; use it only when that
extra shared-storage load is appropriate. It never loads a complete FASTQ into
memory. Record dataset characteristics (read length, read count, compression,
single/paired-end, filesystem, cache conditions) without publishing protected
reads or identifiers.

## Failure and interactive checks

- Repeat a long run in a new output directory with `--cancel-after 30`. Confirm
  cancellation, bounded process cleanup and subsequent queue operation. If the
  tool finishes sooner, the recorded state is completed, not a fabricated cancel.
- Exercise memory pressure only within an allocated, enforced cgroup. The Linux
  CI validator already tests a deliberate bounded overrun with actual `/proc`
  observations; site-specific near-limit Java/MultiQC behavior remains to test.
- Test insufficient space only on a dedicated bounded test volume or quota.
  Never fill a production/shared filesystem. Retain the previous valid manifest,
  capture the error, free only test-owned data, restart and check truthful
  interrupted/failed state and historical reports.
- In the browser, navigate and poll logs while a large analysis runs. Record API
  latency and actual SSE/network behavior behind the site's reverse proxy. The
  benchmark's TestClient timings do not replace live browser or SSE acceptance.
- End and restart the allocated session, and test abrupt parent death. Verify
  no live QC process remains and successful history remains downloadable.
- Compare native charts and official FastQC/MultiQC data; record actual tool
  versions, walltime, RSS, CPU and storage observations in an acceptance record.

Choose CPU/RAM/walltime defaults only after those observations. Explain tradeoffs
under concurrent filesystem load and retain headroom for JVM/Python startup,
FastQC threads, the application, and report parsing. Do not infer site defaults
from small fixtures or from another cluster's limits.

## Native processing benchmarks (#5)

The same script now accepts `fastp`, `seqkit-stats`, `seqkit-sample`,
`seqkit-filter` and `seqkit-extract`. It uses the normal application queue,
validation, resource limits, cancellation and registered artifacts. Set
`QUALIDOCK_FASTP` / `QUALIDOCK_SEQKIT` if executables are not on PATH. Exact
sampling requires SeqKit 2.14+. Paired length/ID selection uses the existing
QualiDock synchronized selector; it does not pretend to execute SeqKit.

Use the same `--input`, new `--output`, resource and optional `--hash-inputs`
arguments as above, adding one of:

| Operation | Arguments |
| --- | --- |
| fastp baseline | `--mode fastp` |
| fastp + before/after QC + MultiQC | `--mode fastp --compare-qc --multiqc` |
| Fraction sampling | `--mode seqkit-sample --fraction 0.25 --seed 73` |
| Exact reads/pairs | `--mode seqkit-sample --count 100000 --seed 73` |
| Independent length selection | `--mode seqkit-filter --min-length 100 --max-length 200` |
| Both-mates length selection | Same plus `--preserve-pairs` |
| Independent exact ID selection | `--mode seqkit-extract --identifiers /private/ids.txt` |
| Both-mates normalized ID selection | Same plus `--preserve-pairs` |

Sampling and fastp use normal persisted mutual pairing detection. Ambiguous names
remain independent; review the evidence's `input_pairing` and processing units.
Counts are per unit (reads or confirmed read pairs), not pooled across files.
`--plain-output` disables output gzip. No source is overwritten or copied as a
prerequisite. A processing run legitimately creates separately owned FASTQs:
evidence verifies **registered** outputs against saved full-validation SHA-256,
and lists incomplete/unpublished files separately. Completed runs with unknown
FASTQs fail the benchmark check. Failed/partial states exit unsuccessfully;
cancellation is recorded separately and never called completed processing.

`validation_scans` records actual scanner bytes, coverage and checksum evidence.
`execution_stages` records tool/validation wall time and sampled RSS from the
executor; `process_counters` adds Linux sampled CPU and available rchar/wchar and
read_bytes/write_bytes. Counters can miss short processes and are lower bounds.
`waited_child_cpu_seconds` measures waited children (including probes/guardians),
not API CPU; cumulative child high-water RSS is **not** a tree peak. Optional QC
stages are explicit, not silently counted as baseline processing. Output audit
hashing adds one full derived-output read; optional source hashing adds two
separately timed full source reads. Neither is processing validation overhead.

Portable small-fixture runs also work on macOS, with Linux-only counters/RSS and
filesystem type marked unavailable. No physical disk/network throughput is
inferred from file sizes or logical scan bytes. The genuine-tool regression
matrix is `backend/tests/test_benchmark.py`; Linux CI additionally exercises the
existing resource/cancellation validator. These tests establish benchmark
implementation correctness only. Authorized large-file, cache/concurrent-load,
NFS/Lustre, insufficient-space and site tuning acceptance remains pending.
