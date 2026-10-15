# Native multi-sample QC analytics

QC Metrics now contains Overview, Sample Details and Compare Samples. The main
navigation, execution pipeline, single-file FastQC charts, R1/R2 comparison and
isolated official Reports viewer are unchanged.

## Data and compatibility

Overview reads the existing saved `metrics.json`: MultiQC General Statistics
and individual FastQC module classifications. Verified MultiQC 1.25.1 list
sections and 1.35 section-keyed sections use the existing backend adapter. All
available General Statistics columns can be shown, sorted, searched and exported.
Click a heading for primary sorting; Shift-click adds a sort priority. Exports
include filtered rows and visible columns. Missing cells remain blank in exports
and show Unavailable in the table. Zero remains zero.

Optional MultiQC summary fields `tool` and `version`, and column fields
`raw_unit`, `section` and `hidden`, supplement the existing format. No endpoints,
manifest versions, database migrations or tool execution changes are required.
Historical summaries remain readable without modification. Original source JSON
and reports stay available in Reports. Legacy summaries without metadata display
the version as unavailable; their analysis tool version remains in Overview & logs.

MultiQC display suffixes are not reliable units for saved values: the genuine
fixtures save `total_sequences=400` with a display suffix of `M`. The table keeps
400 and labels this verified FastQC field as reads. Verified percent and bp
fields retain those units when no modifier is supplied. Unknown/modified units
are shown as raw rather than guessing a conversion. Tooltips preserve the
original description, field identifier and display suffix. Values are not rounded
or converted by this adapter; numerical JSON values retain the existing JavaScript
number representation. Verbatim decimal text remains available in FastQC source
exports and original downloadable artifacts.

## Identity and shared selection

The persisted FastQC report identity is the selection key. Original filenames,
analysis ID, tool/version, unique original input path (when available), and report
identity are retained. MultiQC sample names map only to unique exact FastQC
filenames or their FASTQ extension-stripped stems. Ambiguous or unmatched rows
retain separate `multiqc:` identities; they are not guessed into biological
samples. Confirmed R1/R2 labels use the existing mutual saved pairing metadata.
Historical records without pairing metadata remain individual files. Lanes and
chunks are never merged.

Selection is shared across Overview and Compare Samples, with search, Select All,
Clear Selection and single-file Only actions. The initial chart selection uses at
most six files. Selection persists while switching QC views in the same open
analysis; it is not written to manifests or browser storage.

## Status matrix

The scrollable, sticky-heading table presents official PASS/WARN/FAIL and unavailable
module states. Search filenames, filter rows by status, sort by warning/failure
counts, show selected files, or hide modules without warnings/failures. Every cell
is a keyboard-accessible button opening the corresponding existing Sample Details
module. Warning/failure counts describe modules, not a new overall sample verdict.

## Verified comparison adapters

- Per base sequence quality: reported means, original bins and quality encoding.
- Per sequence quality scores: original read counts.
- Per sequence GC content: observed distributions; no theoretical curves inferred.
- Sequence Duplication Levels: original reported percentage definitions.
- Adapter Content: original names; incompatible category sets remain separate.
- Sequence Length Distribution: original bins and counts.

Compatible axis definitions and bins can overlay. Non-identical overlapping bins,
incompatible encodings, or incompatible columns/category sets use separate charts.
Nonoverlapping unmatched bins remain gaps. No values are interpolated, expanded,
resampled, merged or inferred from per-base summaries. Different read totals and
experimental protocols remain relevant when interpreting distributions.

An explicit optional sequence-quality percentage view is available only when every
reported Count is numeric, nonnegative, and sums exactly to the saved positive
FastQC Total Sequences. Percentage = Count / Total Sequences × 100. Tooltips retain
raw counts and the denominator. Other distribution views remain unscaled.

Legends and keyboard-accessible series checkboxes control visibility. Inside/slider
zoom and Reset zoom use original categories. PNG export uses the active canvas;
SVG export renders the current chart options (including zoom/visibility) through
ECharts' existing SVG renderer. Source CSV/TSV exports use long-form original
column/value rows with analysis, tool/version, filename, path and report identity.
They retain the complete selected module data, independent of zoom or normalization.

## Validation and limits

`frontend/tests/analytics.test.ts` uses genuine FastQC 0.13.0 fixtures and MultiQC
1.25.1/1.35 General Statistics exports. It covers raw values, missing cells, units,
sorting/filtering, conservative identity/pairing, status matrices, grouped bins,
normalization eligibility, exports, responsive SVG chart generation and 100
explicitly synthetic schema-derived sample records.

`tests/browser/test_analytics.py` runs against real QC engines and restored records,
including standalone and existing reverse-proxy prefix test cases. It exercises
selection, navigation, controls, CSV/TSV/PNG/SVG downloads and a 390px viewport.
Existing browser tests now wait for lazily rendered Raw Data and evaluate sandbox
probes through a real locator, fixing the previous test API/timing defects without
removing assertions. CI browser screenshots are uploaded with the test results.

Native comparisons currently use saved FastQC modules, not undocumented MultiQC
plot objects. Unsupported results remain accessible in official Reports. Cross-run
comparison, persistent selection preferences and arbitrary MultiQC plugin plots
are outside scope. Hundreds of selected curves can be crowded: the initial six-file
selection and series controls support focused exploration. CSV/TSV contains original
sample strings; use spreadsheet import settings appropriate for untrusted text.
