# Delivery manifest and quantity targets

Open an analysis → Overview & logs → **Delivery manifest & yield**. This is an inventory/review aid, not an automatic biological release decision. No source FASTQs are copied, renamed, concatenated or reprocessed when opening this view.

## Inventory and independent expectations

The inventory preserves stable file/sample IDs, original filenames and paths, lane/chunk/read roles, pairing provenance, sizes, reported read lengths and measured counts when available. Existing saved sample groups are reused. Distinct directories with identical filenames remain distinct files. Lane gaps are informational: QualiDock does not invent which lanes should exist.

Import a UTF-8 CSV or JSON expected manifest (1 MiB, 500 rows maximum). CSV headers may be `file_id,path,filename,sample_id,sample_name,lane,chunk,read,expected_reads,expected_bases,sha256`; use only needed columns. JSON accepts an array of those row objects or `{"schema_version":1,"files":[...]}`. Each row needs an exact file ID, path or filename; other supplied identities must also match exactly. Counts are nonnegative whole numbers (maximum 2^53−1); SHA-256 has 64 hexadecimal characters. Read roles are `R1`, `R2`, `SE`, `unpaired`.

A filename shared by several files is **ambiguous**, never silently matched. Scope it with a stable file ID, exact path or sample/lane/chunk/read. Absolute paths supplied in expectations are inert strings: importing an expectation cannot read arbitrary files. Missing, extra, duplicate, ambiguous, count/hash mismatch and unavailable checks are shown separately. Explicit missing/extra/mismatch evidence requires review; an unavailable required observation is **not evaluated**, never a match.

The downloadable identity template contains the **currently selected** file IDs/filenames, without invented expected quantities or hashes. Edit it against an independent delivery agreement; reimporting observed identities is not independent evidence of completeness. Full inventory exports contain additional observation fields and are not the expected-manifest schema.

## Quantities and denominators

- **Reads:** individual FASTQ records; R1 + R2 are two reads, not one pair. Available from saved FastQC counts only while captured input metadata still matches, or from a current full integrity scan.
- **Read pairs:** sum of synchronized mate record counts only when every contributing file is covered by a full, current, successful pair validation with matching identifier order. An unmatched/unknown mate makes the sample pair quantity unavailable.
- **Bases:** actual lengths summed by full scan, or records × an explicitly fixed FastQC-reported integer length. A range such as `35-151` cannot establish base totals.
- **Q20/Q30:** actual qualifying quality characters and the actual counted-quality-base denominator, using an explicitly known quality encoding from FastQC whose captured input snapshot is verified. Historical scans without that association retain structural/count evidence but do not assert Q20/Q30. Never derived from mean per-base Phred values. Empty inputs have zero counts and unavailable percentages.

Only additive counts are summed across unique physical input references within each saved sample group. No distributions, lane quality profiles or unrelated biological samples are merged. File inventory retains lane/read-level observations. If one contributing value is unavailable, its sample total is unavailable rather than an understated partial total.

Choose an explicit per-sample minimum in read records, synchronized pairs or bases. No universal threshold is supplied. Declare the assay/project label and whether the selected FASTQs are raw, processed upstream or unknown. Describe known adapter/UMI/filtering transformations as metadata; QualiDock does not perform those transformations. This denominator describes the **selected FASTQs**, not original demultiplexing clusters or excluded upstream reads. High Q30 does not override a failed quantity target. Unknown metric definitions remain not evaluated.

## Persistence, exports and safety

Expected-manifest submissions, text SHA-256, Unix actor, timestamps and quantity configuration are saved additively in the existing run manifest. Expected submissions have immutable JSON sidecars. Each configuration change increments `delivery_revision`. Historical runs remain readable; missing source files retain their saved QC reports but cannot assert current source quantities or hashes. Imported reports without proven source FASTQ references cannot establish an input delivery.

Manifest JSON and CSV default to logical relative file references (`inputs/<stable-id>/<portable-name>`). These are packaging references, not copied files or a promise that those files exist inside a bundle. Automatic absolute source paths and historical path-based pair IDs are excluded. An explicit **Include private absolute input paths** option adds source paths. Review user-entered free-text names and processing notes before sharing: those are retained, not automatically censored.

CSV defaults to spreadsheet-safe escaped text, with an explicit verbatim option, as described in [EXPORTS.md](EXPORTS.md). Numeric observations and JSON retain source values; missing values are null/blank, not zero. A source SHA-256 is **computed**, not verification after transfer; compare it with independently supplied expected hashes for source-side reconciliation and verify again at the receiving system.

Authenticated endpoints:

- `GET /api/runs/{id}/delivery`
- `GET /api/runs/{id}/expected-template` (attachment)
- `POST /api/runs/{id}/expected-delivery` (`format`, `content`)
- `POST /api/runs/{id}/yield-targets` (`assay`, `input_stage`, `processing_notes`, `targets`)
- `GET /api/runs/{id}/delivery-manifest?format=json|csv&mode=spreadsheet|verbatim&include_paths=false`

All existing download, authentication, CSP and configured input-root protections remain in force. Opening this view reads bounded saved metrics and file metadata; full FASTQ scans are explicit cancellable integrity jobs. There is no database migration or new QC engine.
