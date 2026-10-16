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
Tool detection now has explicit probe/version specifications instead of treating
all tools other than FastQC/Kraken2 as MultiQC.

Processing adapters declare validated options and derived outputs, call the
existing manager command method, and run within its slot. Source FASTQ files
remain read-only. Each operation gets a unique, owned run directory. Derived
FASTQs are separate registered datasets, not files discovered indiscriminately.
Incomplete/cancelled outputs are not published as successful datasets.

Existing QC modes, manifests, report IDs and secure HTML previews are preserved.
Administrative catalog services are not dependencies of read processing setup.
