# Core FASTQ processing

FastQC, MultiQC, fastp and SeqKit use the same RunManager queue, LocalExecutor,
resource slot, cancellation, locked output roots, atomic manifests and artifact
registry. There is no project catalog dependency or separate processing engine.
The four primary views are Workspace, Quality Control, Read Processing and Results.

## Workflow and derived reuse

Select FASTQs in Workspace, choose QC or Read Processing, and run. Tool settings
have defaults; advanced parameters are optional. New length/extraction setups keep confirmed mates
together by default; the checkbox also allows independent-file processing. Old
reruns without this option retain their independent behavior. Essential thresholds,
sampling method/count/seed and gzip output are visible; relationship review is
available for every operation that can preserve pairs. fastp writes separate derived
FASTQs, JSON and HTML, with optional before/after FastQC and combined MultiQC.
Results show reported counts, bases, Q20/Q30 fractions and filtering statistics;
these fractions come from fastp, never from FastQC per-base means.

In a processing result, select all outputs, a verified pair or individual files,
and choose **Use as input**. The normal setup opens with those files selected.
Choose FastQC or Read Processing to continue. No FASTQ is copied. A selected
single mate remains unpaired; unrelated units and lanes are never merged.

- `GET /api/runs/{id}/datasets` discovers published outputs as a validated draft.
- `POST /api/runs/{id}/reuse` with `{"dataset_ids":["u0001:1","u0001:2"]}`
  prepares a selected draft without executing tools.
- `POST /api/runs` and `/api/sample-configuration` accept optional
  `input_datasets: [{run_id, dataset_id}]` alongside exact input paths.
- Saved manifests add optional `input_datasets` and `input_provenance`. The
  latter retains source analysis/dataset, original source path, checksum, file
  snapshot, counts, lane and chunk. Following source IDs recovers the chain.
  Old manifests need no migration. Rerun restores and revalidates these references.

Only exact registered derived FASTQs from completed/partial analyses are allowed.
The existing artifact validator checks the owned result directory, canonical path,
symlink containment and saved size/mtime/device/inode. References are revalidated
when creating, preparing, queuing and executing. Output roots never become general
browse roots. Unregistered siblings and incomplete/cancelled outputs remain denied.
This is provenance between operations, not a workflow orchestration system.

## Tool contracts

fastp accepts single reads or persisted mutual R1/R2 pairs. Every unit has an
independent destination. Adapter trimming and quality/N-base filtering are enabled
by default. Minimum length, quality threshold, permitted low-quality fraction,
threads and gzip output are configurable. The wrapper explicitly selects Phred+33,
N-base limit 5, no automatic poly-G trimming, and no duplication estimation; it
never merges, corrects or deduplicates reads. Disabling quality filtering also
disables fastp's N-base filter. The defaults and exact argv are persisted.

SeqKit supports `stats --tabular`, seeded fraction `sample`, `seq` length filtering
and `grep` literal-ID extraction. Confirmed paired-end **fraction sampling** uses
identical seed/fraction on fully synchronized input files and requires full output
identifier/order validation. Matching counts alone cannot publish paired datasets.
The same seed is reproducible with the same inputs and tool version. The fraction
is a probability, not an exact number of reads. This follows [SeqKit's documented
paired sampling contract](https://bioinf.shenwei.me/seqkit/usage/#sample).

Length filtering accepts `preserve_pairs: true` to evaluate synchronized R1/R2
records together. Both mates must meet the inclusive minimum/maximum lengths;
otherwise both are removed. This uses the existing FASTQ parser through a small
QualiDock selector under LocalExecutor. Its actual processor/version, pair counts,
input/output byte observations and original bytes are retained in `selection.json`.
Full input and output validation is still required. Independent-file filtering
remains the API default for historical configurations. All-paired selection needs
no SeqKit executable; mixed/single-end input still uses normal SeqKit filtering.
Identifier extraction also accepts `preserve_pairs: true`. Requests use exact,
case-sensitive normalized first-token IDs; only terminal `/1` and `/2` are removed,
matching the integrity validator. Both mates are emitted in original order, once
per requested ID. Duplicate requests are collapsed. If a requested normalized ID
occurs repeatedly in the source, extraction fails as ambiguous and publishes
nothing. Missing IDs are listed in `selection.json` and surfaced as warnings;
matched records are retained (including a valid empty result when all are missing).
Independent-file extraction remains unchanged.

Sampling accepts either `fraction` or an optional positive integer `count` (the
count selects exact mode). Exact mode uses verified SeqKit 2.14+ `sample2 --number N
--two-pass --rand-seed S`. Its reservoir stores N record indices, never complete
FASTQs, and emits selected positions in input order. The same seed/validated mate
order selects the same pair positions. The output validator must count exactly N
records per mate. Counts are per processing unit: reads for single-end files,
read pairs for confirmed pairs, never a pooled number across lanes or samples.
Requests larger than a unit's validated input count fail that unit without
clamping or replacement; other independent units may complete. Zero/negative,
non-integer and unsafe JavaScript integer counts are rejected.

SeqKit's older `sample --number` is not used: its result can be approximate and
is not uniform fixed-size sampling. Exact mode is gated at request and execution
time; older compatible installations still support fraction sampling. Independent
Go reference indices and actual FASTQ content comparisons verify the pinned 2.14
sampler. Go is only used to reproduce the test reference, not at runtime.
Statistics is read-only and produces no derived FASTQ. No reads are concatenated
or automatically repaired.

Tools are optional external installations, detected on PATH or with
`QUALIDOCK_FASTQC`, `QUALIDOCK_MULTIQC`, `QUALIDOCK_FASTP`, `QUALIDOCK_SEQKIT`.
Detection supports FastQC 0.12.1–0.13.x, MultiQC 1.25–1.x, fastp 0.23–1.x and
SeqKit 2.6–2.x. Probes never install tools. Acceptance targets use actual FastQC
0.13.0, MultiQC 1.25.1/1.35/latest 1.x, fastp 1.4.0 locally/0.23.4 in CI and
SeqKit 2.14.0 in CI; a compatibility range does not imply every version was tested.

## Validation and I/O

Full structural validation and SHA-256 calculation share one streaming pass per
input/output. Input snapshots are cheaply checked before/after commands. Output
validation includes gzip CRC, read/base totals and full ordered mate identifiers.
fastp's before/after totals must match scanned records and bases before publication.
A failed unit cannot publish apparently successful FASTQs; successful independent
units survive a partial failure. Cancellation/restart clears unpublished outputs.

Each file therefore receives one source validation scan, the processing
operation, and one output validation scan. Optional raw/post FastQC adds external
reads; tools may perform their own additional passes. Chart changes and exports
use persisted reports and never rescan FASTQs. Disabling optional before/after QC
avoids those executions. There is no separate redundant checksum-only pass.

Full validation is deliberately retained when reusing a derived FASTQ. A mutable
shared file's size/mtime/inode alone cannot prove its bytes are unchanged. Reusing
old checksums as fresh checksums would weaken correctness. Future scan reuse should
require a trustworthy immutability/evidence contract; quick scans remain partial,
not substitutes for full validation. Genuine-fixture measurements record actual
scanner bytes, wall/CPU time and memory semantics in CI; external-tool I/O counters
and NFS/Lustre throughput are not guessed from file sizes.

## Tests and limits

`pytest backend/tests/test_processing_real.py backend/tests/test_paired_processing.py`
runs actual tools and the synchronized selector, including source
immutability, single/paired inputs, partial failures, derived chaining outside input
roots, restart/rerun, collision namespaces, paired sampling and malformed IDs.
CI provisions missing tools explicitly; its strict environment makes missing tools
an error. Browser coverage uses Chromium and real processing, reports, downloads,
reuse after restart and narrow layouts. Local missing-SeqKit cases are reported as
skips, not as successful executions. New cases compare complete output records
against independently selected source positions, including wrapped FASTQ, unequal
mate lengths, empty results, ambiguous IDs, mismatched/reordered mates, cancellation,
partial failure, output collisions, symlinks, source immutability and restart/reuse.
The exact sampler is checked against committed independent Go reservoir indices
for two seeds and two counts, then repeated, run at full population and over capacity.
Chromium exercises filtering → derived reuse → exact sampling → ID extraction,
including keyboard submission, missing-ID downloads and a 390 px layout.

Synchronized selection holds only the current two bounded records and requested-ID
metadata. Exact sampling uses O(N) indices in the external tool; selecting a very
large count still needs proportional index memory and remains subject to the
existing memory limit. FASTQ lines/records retain the validator's existing 1 MiB /
4 MiB support bounds. IDs with other conventions must be entered exactly; no
fuzzy normalization, repair or cross-lane merging is performed.

Before/after charts reuse the existing exact FastQC modules and Raw Data exports;
incompatible bins remain on separate axes. Q20/Q30 are unavailable unless actually
reported. Official HTML remains sandboxed. Current ECharts bundle-size warnings
remain; no new library, database or global state framework was added.
