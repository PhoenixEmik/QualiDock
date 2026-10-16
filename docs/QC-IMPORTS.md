# Existing QC-report imports

**MultiQC only** accepts an explicit, bounded allowlist:

- FastQC `*_fastqc.zip` or extracted `fastqc_data.txt`, with existing summary/HTML companions.
- **fastp JSON** with `summary.before_filtering`, `summary.after_filtering`, integer `total_reads`/`total_bases`, `command` and `read1_before_filtering`. Reported `summary.fastp_version` is retained; old reports without that field explicitly have an unknown version. Other JSON schemas, including unsupported fasterp variants, are not treated as fastp.

This imports reports produced elsewhere. QualiDock does **not** run fastp, trim reads or execute a report's command string. A fastp JSON describes an upstream processing operation, possibly multiple reads; it is not a new FASTQ result or evidence of biological sample identity. Before/after-filtering definitions remain distinct.

Select `fastp.json` / `*.fastp.json` in Files view, or enter a results directory in New Analysis. Directory discovery accepts valid fastp JSON with other filenames too. Unknown inputs are excluded with a bounded summary (first 20 reasons); explicitly selecting an unsupported report fails clearly. Only recognized reports are snapshotted and passed to MultiQC. Limits remain 500 reports, 20,000 scanned entries, 64 directory levels and 512 MiB total imports; per-report limits and symlink/containment checks remain enforced.

When a fastp report is included, MultiQC receives a run-local configuration using report filenames, full names and per-snapshot directory prefixes. Thus two reports describing similarly named upstream reads cannot silently overwrite one another. A verified `report_data_sources` mapping in supported MultiQC 1.x JSON links table rows back to exact snapshotted reports. An unknown/ambiguous mapping is reported, never guessed from a command or similar filenames.

QC Metrics → Overview displays MultiQC's saved General Statistics. Unsupported raw units remain unspecified rather than inferred from display suffixes. Imported fastp observations have no fabricated FastQC module classifications, heatmap cells or native FastQC curves. Mixed imports retain the genuine FastQC sample views. The complete MultiQC report and snapshotted JSON remain downloadable; upstream fastp plots remain in MultiQC's official viewer rather than being translated speculatively into native FastQC charts.

Overview & logs lists source format, schema, reported version and snapshot SHA-256. Original source reports are unchanged. Existing manifests without optional import fields retain their historical FastQC handling. Imported reports alone cannot establish source FASTQ integrity or delivery quantities. Standalone and URL-prefixed routes use the existing authenticated artifact registry and report sandbox.

Genuine regression reports, their upstream commit, license and SHA-256 are recorded in `backend/tests/fixtures/imported-qc/README.md`. Real MultiQC integration runs against the project's 1.25.1, 1.35 and latest-1.x CI matrix.
