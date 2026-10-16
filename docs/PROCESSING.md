# FASTQ processing architecture

The next phase prioritizes native fastp and focused SeqKit operations. Projects,
release review and cross-run analytics remain available, optional features.
Issues #24–#25 (delivery expansion) are deferred; no new delivery engine is part
of this phase.

## Architecture review

RunManager already owns the queue, one shared resource slot, LocalExecutor,
process-group cancellation, source snapshots, output-root locks, atomic JSON
manifests and registered report downloads. Those remain the execution and
persistence boundary. No new database or execution engine is needed.

FastQC batching and result parsing previously lived inside its main execution
method. They are extracted once, so processing stages can reuse the same code.
Processing stages retain the existing per-input collision namespaces, including
manual pairs with identical basenames in different directories. Tool detection
now has explicit probe/version specifications instead of treating
all tools other than FastQC/Kraken2 as MultiQC.

Processing adapters declare validated options and derived outputs, call the
existing manager command method, and run within its slot. Source FASTQ files
remain read-only. Each operation gets a unique, owned run directory. Derived
FASTQs are separate registered datasets, not files discovered indiscriminately.
Incomplete/cancelled outputs are not published as successful datasets.

Existing QC modes, manifests, report IDs and secure HTML previews are preserved.
Processing setup requires no project or release records. Startup retains the
existing catalog compatibility guard and result-store ownership locks.

## Running operations

Select FASTQs in Workspace, then open **Read Processing**. fastp defaults to
adapter detection/trimming, quality filtering (Q15, at most 40% unqualified bases),
minimum length 15 bp, gzip output and FastQC before/after. The optional advanced
section controls these thresholds, threads, output root and combined MultiQC.
Only Phred+33 input is supported for native fastp in this phase. QualiDock disables
poly-G trimming, duplication estimation, deduplication, merging and base correction;
these are not hidden processing steps. Quality filtering also applies fastp's
5-N-base limit per read. Disabling quality filtering disables the N-base filter
as well; length filtering remains active.

Each confirmed pair is processed together. Single/unassigned reads are processed
individually. Pair ID/order verification uses the existing full FASTQ scanner,
not filename similarity. Lanes/chunks stay separate. Integrity scanning happens
in a cancellable subprocess under the same resource slot; the server does not
load source FASTQs in memory. The existing scanner's 1 MiB line / 4 MiB read limits
apply. Source and output structure/checksums are preserved as processing provenance.

SeqKit supports per-file `stats --tabular`, seeded fraction `sample`, minimum/
maximum length `seq`, and literal identifier `grep --pattern-file`. Sampling is
probabilistic, not an exact requested count. SeqKit filtering/extraction is per
file: derived outputs are deliberately **not** declared synchronized pairs.
Even matching names or equal counts do not establish mate synchronization.
No reads are concatenated, reordered by QualiDock, or silently repaired.

## Configuration and API

Tools must already exist on PATH or be configured using `QUALIDOCK_FASTP` and
`QUALIDOCK_SEQKIT`. Detection supports fastp 0.23–1.x (`--version`) and SeqKit
2.6–2.x (`version`). Tested versions are recorded in validation evidence; the
compatibility window is not a claim that every release has been exercised.
The application never installs tools. No new Python or JavaScript dependency is
required. CI provisioning is explicit in `scripts/setup-processing-ci.sh`.

Existing `POST /api/runs` adds modes `fastp`, `seqkit-stats`, `seqkit-sample`,
`seqkit-filter`, `seqkit-extract`, with optional `processing_options`. Unknown
option keys, invalid ranges, non-FASTQ paths and unsupported tools are rejected.
FastQC/MultiQC modes retain their contracts. Processing runs add optional JSON
fields `processing` and `derived_datasets`; there is no manifest/database migration.
The existing rerun configuration endpoint restores processing options and inputs.
The history mode filter accepts processing modes, with the same pagination.

Output selection reuses configured `QUALIDOCK_OUTPUT_ROOTS` and exclusive store
locks. A run never accepts an arbitrary output filename or overwrites a source.
Derived files use stable per-unit namespaces. Only successfully processed and fully
validated files become registered datasets. They download through the existing
authenticated, attachment-only endpoint with containment and saved-file snapshot
checks. Private work configs, incomplete reports and unregistered FASTQs are not
downloadable. Cancellation/restart interruption clears dataset publication; stopped
files remain on disk for diagnosis, not as successful results. No automatic cleanup
or destructive deletion is introduced.

## Native before/after comparison

QC Metrics opens a compact Before / After view for processing runs. Choose one
input unit and one read. Totals, bases, GC, Q20/Q30 and filtering/trimming data come
from official fastp JSON. Paired totals count both mates' reads; they are not read
pairs. Retained/removed percentages use the explicit reported before/after counts;
a zero denominator is unavailable. Q20/Q30 rates are never inferred from FastQC.

Raw/processed FastQC modules are shown side by side with their own original bin
labels. No interpolation, expanded positions, pooled quartiles or synthetic GC
reference is used. Existing Raw Data/CSV/TSV controls and official reports remain
available. Native multi-sample analytics and R1/R2 comparisons remain accessible;
processing stage labels and declared dataset provenance distinguish the two stages.
The optional MultiQC report receives successful FastQC ZIPs and fastp JSON via an
explicit list, with directory namespaces and verified structured source mappings.
A MultiQC failure preserves successful fastp output and marks the run partial.

Official HTML stays sandboxed; fastp reports requiring external JavaScript may be
limited in the isolated preview. Original downloads remain the fidelity fallback.
No CSP or authentication protection is weakened for processing.

## Validation

`pytest -q backend/tests/test_processing.py backend/tests/test_processing_real.py`
checks parameter/path boundaries, actual fastp/SeqKit behavior, source checksums,
raw/processed numerical fidelity, malformed/mismatched mates, partial failures,
cancellation, restart and attachment authorization. Actual-tool tests skip absent
tools locally; `QUALIDOCK_REQUIRE_PROCESSING_TESTS=1` makes missing tools fatal in
acceptance jobs. CI also runs the existing QC, report/security, project/release,
resource and browser regressions. Synthetic malformed data is clearly test-only;
production code never fabricates metrics.


## Known limits and follow-up

- Processing is scoped to files in one analysis. Existing project, release and
  cross-run features remain available; this phase adds no delivery/approval work.
- Full source/output validation adds sequential disk reads and checksum work.
  It stays outside the web process and is cancellable, but is not a throughput
  benchmark for very large sequencing runs or remote filesystems.
- fastp supports explicit Phred+33 input only. This phase does not add UMI handling,
  deduplication, correction, mate repair or lane concatenation.
- SeqKit outputs remain independent file datasets. Pair-preserving filtering and
  exact-count paired subsampling would require a separate, tested feature.
- Existing asset bundle size warning remains. No new chart library or component
  framework is introduced; bundle splitting can be addressed independently.

Future work should prioritize measured throughput and a browse-first action for
starting a new operation from a registered derived dataset. Current before/after
FastQC runs already consume registered processing outputs internally without
copying inputs or granting general filesystem access to output roots.

Tool behavior references: [fastp options](https://github.com/OpenGene/fastp),
[fastp filtering implementation](https://github.com/OpenGene/fastp/blob/v1.4.0/src/filter.cpp),
and [SeqKit usage](https://bioinf.shenwei.me/seqkit/usage/).
