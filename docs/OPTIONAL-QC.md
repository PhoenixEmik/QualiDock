# Optional QC tools

Optional tools use the same RunManager, LocalExecutor, queue, Unix user, CPU/memory
limits, cancellation, owned output directories, authenticated downloads and
restart recovery as the default FastQC workflow. QualiDock never installs tools.
FastQC remains the default. These integrations do not create processed FASTQs.

## nanoq 0.10.0

Set `QUALIDOCK_NANOQ` to an executable path, or provide `nanoq` on PATH. Version
detection deliberately accepts the verified **0.10.0** contract only. Select
FASTQ/FASTQ.gz files in Workspace, configure **nanoq long-read QC** in Quality
Control, then inspect the saved **QC metrics** and **Reports** tabs. Each file is
evaluated independently; mate counts are not combined into biological samples.
Registered derived inputs use the existing exact dataset authorities.

The command is `nanoq --stats --json --report <owned.json> --input <input>`.
`--stats` suppresses read output; no filters, trimming, `--fast`, stdout FASTQ or
length/quality per-read dumps are requested. Input FASTQs first pass the existing
full streaming validator in a resource-governed, cancellable subprocess. Count,
base and min/max-length totals must match the actual JSON before registration.
Original JSON is retained byte-for-byte; malformed, empty, missing or inconsistent
reports fail. Completed files survive failures of other inputs as partial results.
Unfinished QC namespaces and private validation files are not artifacts.

The native table preserves reported numbers, including nanoq's integer mean
length. N50 is taken directly from nanoq, never recalculated. Threshold counts use
**strict `>`** in upstream 0.10.0, despite an inconsistent source comment saying
`>=`. Mean read quality is based on each read's mean error probability, converted
to Phred, then summarized across reads. nanoq uses Phred+33; this is a tool
convention, not independent encoding detection. These are not FastQC's per-base
mean values or Q20/Q30 **base** percentages. ONT protocol and basecalling affect
quality; no short-read PASS/WARN/FAIL rules or biological interpretations are added.

MultiQC 1.35's nanoq module reads verbose **text** reports, not this JSON schema.
This adapter therefore does not offer aggregation or manufacture a text report.
Original JSON remains downloadable. Existing FastQC/fastp MultiQC is unchanged.

nanoq 0.10.0 retains read length/quality vectors, so memory scales with read count;
it is not a constant-memory algorithm. Existing process-tree limits apply. One
additional full input-validation scan supplies structure, gzip CRC and SHA-256
evidence. Snapshot rechecks detect ordinary changes; they are not a claim that
file size/mtime alone proves immutable content. No large/shared-storage throughput
or peak-memory acceptance is inferred from the small fixtures.

Validation includes genuine upstream ONT records and untouched nanoq output,
plain/gzip, original numerical fidelity, missing dependencies, malformed/oversized
JSON, invalid inputs, collision isolation, partial outcomes, validation cancellation,
downloads, derived authorization and restart. CI provisions only test tools and
exercises actual setup/results/restart interactions in Chromium and Firefox.
