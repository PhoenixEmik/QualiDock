# Native FastQC exploration (Phase 3A)

QC Metrics keeps the existing workspace, sample selector, ECharts renderer,
collapsible Sample Details and official Reports tab. The scientific parser and
all FastQC/MultiQC commands remain unchanged.

## Exploring a result

- The compact module navigation shows all 12 supported modules, additional
  reported modules and their original PASS/WARN/FAIL or unavailable status.
  Clicking a module (including its status) selects the chart/table and focuses
  its heading. Buttons support standard keyboard activation; unavailable modules
  explain what is missing. Original `summary.txt` disagreements remain visible.
- Single Sample retains each report's native charts. Raw Data can be expanded
  below every chart or table and exported as CSV/TSV without another analysis.
  Only 200 rows are mounted per table page, with horizontal scrolling and sticky
  headers. Exports contain all original columns and data rows, not only the page.
  Metadata such as Total Deduplicated Percentage remains visible above the data.
- About this module contains static explanatory notes checked against the
  [official FastQC help](https://www.bioinformatics.babraham.ac.uk/projects/fastqc/Help/).
  Each module links its source. Notes describe what is measured, what the reported
  classification concerns, possible protocol/technical context, and limitations.
  Actual saved classifications remain authoritative; thresholds are not
  recalculated. There are no LLM calls or automated biological conclusions.
- Protocol context includes genomic, RNA-seq, amplicon, targeted and
  methylation-related assays, including Illumina 5-Base Solution. It does not
  assume that different methylation chemistries create the same sequence biases.
  A FastQC warning is not an automatic instruction to trim, filter or discard.

## Pair evidence and compatibility

New FastQC analyses save optional `input_pairing` records in the existing JSON
manifest. `FileAccess.pairing()` reuses the explorer's naming groups, containment
checks and unique-R1/unique-R2 criterion, including ambiguous names elsewhere in
the directory. It reads file metadata, not FASTQ contents. If indexing or mate
inspection is unavailable, valid FastQC inputs still run and a `pairing_note`
explains why comparison is unavailable.

The frontend requires two unique parsed report filenames, two selected input
references, mutual mate paths, distinct R1/R2 designations and the same saved pair
key. It never establishes pairing from filenames alone. Directory, lane and chunk
identity remain in that key; lanes are not merged into artificial combined data.
Choosing another sample/pair changes only client-side visualization.

No schema-version change or migration is needed. Old completed analyses retain
all existing individual views, data and downloads. Historical manifests lacking
pair evidence, single-end reads, missing mates, duplicate/ambiguous matches and
report-only imports remain individually inspectable. Comparison is disabled
rather than inferred. New paired analyses retain their evidence after restart
even if the original input filesystem is no longer mounted. Report-only MultiQC
imports do not acquire biological pairing from report filenames.

## Comparison rules

R1 / R2 Comparison supports quality means, optional reported medians, base
composition, N content, adapter content, GC distributions, mean read-quality
distributions, length distributions and duplication metrics where columns agree.
Checkboxes provide keyboard-accessible series visibility without recreating the
chart or rerunning FastQC. Color identifies the read for single-statistic quality
plots. In composition plots color identifies the nucleotide, while solid/circle
and dashed/triangle styling identify R1 and R2.

Reported labels such as `10-14` remain single bins. Only identical labels with
compatible interval boundaries are aligned. Additional non-overlapping bins can
appear on the common category axis, with a gap for the read that did not report
them. Overlapping bins with different boundaries, ambiguous labels, incompatible
axes, or differing/missing quality encodings use separate original plots with an
explanation. No bin is expanded, resampled, interpolated or silently replaced by
zero. Category widths remain nominal, as in the existing single-read chart; this
is not a reconstructed per-base coordinate series.

Adapters and other multi-column modules overlay only exactly matching named
columns. Unshared categories are explicitly identified and remain in the per-read
raw tables; wholly incompatible categories use separate plots. GC/quality/length
counts remain unscaled, so different read totals are not normalized. Tile labels
do not prove equivalent physical locations, and k-mer/overrepresented-sequence
tables are not forced into a misleading shared series.

## Numerical and export integrity

Single-read quality boxes use the reported 10th percentile, lower quartile,
median, upper quartile and 90th percentile in that order. The mean is a separate
series. An incomplete five-number box is omitted rather than completed with
invented values; its reported fields remain in Raw Data. Comparison tooltips
include both reads' complete original rows, including all quality percentiles.

Raw tables and tooltips retain string precision from `fastqc_data.txt`. ECharts
receives the corresponding JavaScript numbers for plotting; tooltips do not
round-trip values through floating-point display formatting. Blank cells are
explicitly unavailable and zero is retained. CSV/TSV use original header/data
strings with delimiter/quote/newline escaping and CRLF record separators. Exports
omit the FastQC module delimiters/comments and include no recalculated columns;
metadata remains separately visible. Spreadsheet software can interpret numbers
or formula-like text on import: use text import settings when preserving literal
fields. QualiDock does not rewrite those values or execute spreadsheet content.

Per-base summaries do not provide exact Q20/Q30 percentages, and these are not
estimated. Sample Details displays each original filename, count, length, GC,
encoding, version and module-status summary. Comparison displays both files'
details without inventing paired-fragment or combined scientific statistics.

## Verification and remaining gates

Local validation uses the genuine committed FastQC 0.13.0 fixtures, plus real
installed FastQC 0.13.0 and MultiQC 1.35:

- **133 backend tests passed**, including pair evidence, ambiguity involving an
  unselected file, independent lanes/chunks, missing mates, metadata-only access,
  graceful pairing failure, symlink containment, actual tools, persistence and
  existing preview/download security.
- **85 frontend tests passed**, covering all 12 modules, mean/median/percentile fidelity, grouped
  bins, gaps, adapter category differences, historical and ambiguous pair records,
  original CSV/TSV strings, explanatory-note coverage and finite ECharts SVG at
  desktop/narrow widths.
- TypeScript/Vite production build and React server-render checks passed. Render
  checks include both-read details, navigation, raw tables, notes, individual
  fallbacks, escaped filenames and the unchanged Reports interface.
- The explicit Chromium/Firefox suite now includes navigation and focus,
  comparison mode, visibility, medians, raw expansion and actual downloads,
  collapse/resizing, unchanged execution records, and historical records without
  new fields. Automated HTTP browser execution remains pending in this managed
  macOS environment, which denies loopback listeners.
- A Firefox component preview using the production components and genuine fixture
  data was inspected interactively: PASS/WARN/FAIL navigation and heading focus,
  both-read comparison, optional medians, series visibility, composition/read
  styling, exact raw strings, module guidance, collapsible details and returning
  to individual metrics worked. This local-file component check does not replace
  HTTP authentication, download or HTTPS OOD integration tests.

The baseline report-viewer CI at
[`e46ca0d`](https://github.com/PhoenixEmik/QualiDock/actions/runs/38714868496)
passed backend, frontend, real-tool matrix, Linux resources and all three opaque
security cases per browser, but failed six report-rendering waits per browser.
Those waits used the first global Plotly SVG, which can target a hidden General
Statistics violin plot. The suite now navigates to the explicit per-base quality
plot and uses a specific visible toolbox control. This selector correction still
requires a new CI run; do not treat it as a confirmed browser-rendering fix. No
report sandbox or security policy was relaxed, and no scientific assertion was
disabled. Existing [report-viewer restrictions](REPORT-VIEWER.md) remain.

No new runtime or frontend dependency/configuration is required. Playwright is
already a test-only dependency in the existing browser CI. Commands:

```sh
QUALIDOCK_MULTIQC=/path/to/multiqc pytest -q
npm test --prefix frontend
npm run build --prefix frontend
QUALIDOCK_BROWSER=chromium pytest -q tests/browser
QUALIDOCK_BROWSER=firefox pytest -q tests/browser
```

Follow-up priorities are actual Chromium/Firefox and HTTPS OOD acceptance,
explicit user-confirmed provenance for imported/historical pair records, and
broader real-world bin/adapter schemas. No trimming, new QC engines, AI
interpretation, historical trend UI or scheduler integration was added.

## Changed files

- Backend: `backend/qualidock/files.py`, `manager.py`; new
  `backend/tests/test_pairing.py`.
- Existing frontend: `AnalysisDetail.tsx`, `QcModule.tsx`, `QualityChart.tsx`,
  `qc.ts`, `chartOptions.ts`, `types.ts`, `styles.css`.
- New frontend: `pairing.ts`, `comparison.ts`, `comparisonChart.ts`,
  `PairComparison.tsx`, `ModuleNavigation.tsx`, `RawData.tsx`, `rawExport.ts`,
  `ModuleHelp.tsx`, `moduleNotes.ts`, `SampleDetails.tsx`.
- Tests: new `frontend/tests/fastqcFixture.ts`, `native-qc.test.ts`,
  `tests/browser/test_native_qc.py`; updated `tests/browser/test_report_viewer.py`.
- Documentation: this file, README and the report-viewer validation record.
