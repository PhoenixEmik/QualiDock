# Read-only FASTQ integrity (#13)

Analysis **Overview & logs → FASTQ integrity** can queue a Full validation or a
Quick scan (up to 10,000 records per file). Neither starts FastQC or modifies its
results. Scans share LocalExecutor and its serial resource slot, CPU affinity,
process-group memory monitor, cancellation and parent-death guardian. No new QC
engine, reference database, file copy, trimming or read reordering is involved.

The internal, versioned `QualiDock FASTQ integrity` worker reads each selected
original FASTQ once with bounded buffers. It validates:

- gzip decoding, all gzip members, CRC/ISIZE and truncation through actual EOF;
  gzip is recognized by extension or magic bytes;
- FASTQ @ / + structure, optional repeated identifiers, wrapped sequence/quality
  lines, matching lengths, supported IUPAC nucleotide symbols and printable
  quality ASCII 33–126;
- exact record/base counts and observed minimum/maximum read lengths;
- complete compressed/source-byte SHA-256, separately labeled as **computed source
  checksum, not verification after transfer**;
- configured PE counts and exact normalized first identifier tokens **in original
  order**, using length-framed SHA-256 streams. Only trailing `/1` and `/2` are
  removed; whitespace annotations (including CASAVA fields) are not part of the
  first token. Similar names, equal counts alone, or ambiguous identifier formats
  never establish synchronization. This does not prove biological sample identity.

Quick scans that reach EOF legitimately have full coverage; otherwise they remain
`not_evaluated`, with no complete checksum, CRC or synchronization claim. Completed
files remain visible if a scan is cancelled, but an incomplete/cancelled/interrupted
job cannot have a passed overall result. A completed scan may contain failed files;
job completion and validation verdict are distinct. Pending mates remain not
evaluated until both scans complete; missing configured mates fail explicitly.

Q20/Q30 **base counts** are measured from actual qualities only with a supported
explicit FastQC-reported encoding: Sanger/Illumina 1.9 (Phred+33), or Illumina
1.3/1.5 (Phred+64). The encoding source and offset are preserved. Unknown/Solexa
encodings leave these counts unavailable. No base-quality percentages are inferred
from per-base aggregate statistics. Numeric counts retain actual read/base
meaning and zero values; percent calculations require a nonzero stated denominator.

## Limits and provenance

Sources are resolved under the current input roots, opened as regular files with
no symlink following, and checked against QC input metadata when available.
Device/inode/size/mtime are checked before and after scanning. Changed/missing or
unreadable sources fail clearly. Historical records lacking the original snapshot
can validate current bytes, but do not assert that those bytes were the original
QC input. Metadata matching alone is not a cryptographic historical QC-input hash.
Imported reports without original FASTQ references cannot claim source integrity.

Lines are limited to 1 MiB and reads to 4 MiB. Exceeding supported limits is
`not_evaluated`, not a fabricated success. The supported sequence convention is
IUPAC DNA/RNA FASTQ, not color-space sequencing. Empty files and zero-length records
are represented explicitly; structural validity does not imply sufficient yield.
RAM does not grow with file length. Full validation adds real sequential I/O/CPU
work and can be substantially slower than a quick prefix scan on large datasets;
no shared-storage throughput claim is made without actual measurements.

Each attempt has an independent `integrity/<task ID>/` directory with its config,
progress/result JSON, validation log and final validation JSON. Current state,
coverage, versions, timestamps, original snapshots, the current Unix requester,
quality-encoding provenance and execution/resource observations are saved in the
analysis manifest. Prior attempts retain artifact references. Restart marks active
attempts interrupted, independently of the original QC run's terminal state.

Authenticated APIs are additive: `POST /api/runs/{id}/integrity` with
`{"mode":"full"}` or `{"mode":"quick"}`, and
`POST /api/runs/{id}/integrity/cancel`. Existing analysis states, outputs, charts,
report sandboxing and downloads are unchanged. No validation is automatically
asserted for old manifests. Native browser acceptance exercises full validation
and its downloaded evidence on the genuine committed FastQC fixture inputs.
