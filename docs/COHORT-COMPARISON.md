# Cross-run and project QC comparisons (#23)

**Workspace → Projects → Open project → Compare runs** reads existing saved QC
and integrity evidence. It never runs tools or scans FASTQ data when opening,
filtering, paging, charting or exporting. Start full validation in existing
analysis/batch controls when exact base-quality counts are needed.

Start with the project-wide comparison, select a metric and apply. Optional
expanders provide searchable checkbox selection of samples/runs or up to five
projects (the current project stays included), platform/assay/library/stage,
sequencing-date and whole-file length-range filters. No additional metadata form
is required to browse available evidence. Unknown input stages are explicitly
excluded; users who know the source stage can confirm it for the listed unknown
runs in one revision-checked transaction. This changes declarations only.

## Scientific definitions

- Read records and bases use complete current validation, or defensible original
  FastQC counts/fixed-length × reads. Definitions remain distinct. R1/R2 are
  separate records; there is no implicit conversion to read pairs. Rounded kbp or
  Mbp strings are not expanded into invented exact counts.
- Q20/Q30 are `100 × counted Q20/Q30 bases / counted quality bases`, requiring
  complete current validation with known encoding and nonzero denominator.
  No percentages are inferred from per-base means. Raw count fractions are kept
  in the table/export even when a floating-point percentage is displayed.
- Minimum/maximum length uses the actual saved observed/reported file range,
  never a manufactured average. Length filters select complete files, not reads.
- GC and estimated deduplicated percentage preserve FastQC Basic Statistics and
  `Total Deduplicated Percentage` at their original reported precision. They are
  not recalculated or summed across samples.
- Adapter content is an exact original adapter category at an exact position
  bin, including grouped bins. It is not a global adapter rate. Older/current
  records without an adapter-configuration digest cannot prove cross-analysis
  adapter equivalence; comparison is conservatively restricted to the source
  analysis. Official reports remain the reference for unsupported definitions.

Compatible groups require identical calculator/version/definition, known input
stage, platform, assay and library context. Unknown protocol metadata is labelled
as descriptive and is never evidence of assay suitability. Different stages or
versions are shown as separate selectable groups. Conflicting sample/run/lane
bindings and physical path aliases are excluded rather than guessed or counted
as independent observations. Repeated QC uses the latest eligible saved evidence
for a source file with a single confirmed identity; alternative references remain
traceable. Similar sample labels never establish cross-project biological identity.

File-level values preserve sample, lane, chunk and R1/R2 identities. The optional
run display sums only complete compatible **selected-file scopes** for reads,
bases and counted Q20/Q30 fractions. Q percentages use sums of numerators and
denominators, never averages of percentages. Missing/incompatible members prevent
partial run totals. This does not assert unproven whole-run yield. Per-file source
values and hashes remain in aggregate provenance. Dates are declared sequencing
dates, with the original declaration retained; analysis dates are not substituted.

An optional user-declared minimum Q30 percentage flags a value for **review** by
exact count comparison. No cutoff is enabled by default. This is neither a
FastQC classification nor a definitive sample/assay failure. The genuine-tool
regression includes an explicitly synthetic low-Q30 fixture and a declared test
reference; it is not a production recommendation.

## Bounds, API and exports

Authenticated, CSRF-protected endpoints beneath `api/projects/{project_id}`:

- `POST comparisons/query`: project IDs (1–5), optional explicit sample/run IDs
  (up to 100 each), metric, filters, rule, file/run grouping and exact adapter/bin.
  Up to 100 compatible and 100 excluded rows per page, with compatible definitions,
  explanations and source metadata. Empty explicit selection never means All.
- `POST comparisons/export`: same query plus the viewed fingerprint, CSV/TSV and
  spreadsheet-safe (default) or verbatim mode. All values in the selected group
  are exported, independent of page size; exclusions can be exported separately.
  Changed evidence/context returns 409 instead of silently exporting a different
  comparison. Exports include exact raw values/counts, units, stage, definitions,
  rule and source/analysis/file/report/tool/version/hash provenance, no absolute
  source paths. Existing authorized analysis APIs retain source-path inspection.
- `PATCH comparisons/run-context`: up to 100 explicit run IDs/revisions and
  declared stage/platform/date fields; atomic compare-and-swap, audited through
  existing catalog updates. QC manifests and historical approvals are unchanged.

Cohorts are bounded to 5,000 evidence references and 2,000 distinct input files;
more than 100 incompatible definitions requires narrowing filters. Saved metric
reads use a per-query 16 MiB LRU cache; there is no database migration, persistent
scientific cache or replacement QC model. A request rejects concurrent evidence
or context changes. Charts show one compatible page, with an initial 16-category
window for larger pages; CSV/TSV exports cover the entire selected group. Existing
ECharts resize, legend visibility and PNG/SVG exports are reused.

## Validation and limitations

Backend tests cover exact counts/fractions, missing and zero values, original
FastQC module precision and grouped adapter bins, conflicting stages, filters,
multiple projects and ambiguous identities, atomic metadata correction, stale
exports, authentication/CSRF/formula handling, paging 100 synthetic metadata
records, and restart without original FASTQ modification. Actual FastQC 0.13.0
and full validation confirm a low-Q30 run is flagged against the declared rule
and original reports remain sandboxed. Frontend tests check source labels, units,
actual zero, missing data, independent series colors and bounded default zoom.
Browser regressions exercise real-tool multi-run comparisons, exports, responsive
layout, original report navigation, restart and incompatible-stage separation.

No biological sample is merged across runs/projects by name. No new general
MultiQC plot adapter, universal outlier rule, inferred theoretical distribution,
read resampling, trend regression or automatic release decision is introduced.
Actual test results/CI acceptance are recorded in [NEXT-PHASE.md](NEXT-PHASE.md).
