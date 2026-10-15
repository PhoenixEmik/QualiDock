# Phase 2: QC engines and reporting

## Implementation

The existing RunManager, LocalExecutor, REST/SSE transport, JSON result store,
React analysis details, and ECharts integration remain in use. Original FASTQ
files are passed by path to FastQC, without loading or copying reads.

- FastQC parsing preserves every module's raw columns, cells, comments, metadata,
  and PASS/WARN/FAIL status. Both `fastqc_data.txt` and optional `summary.txt` are
  read from bounded ZIP members or extracted directories. Disagreements between
  the two files remain visible as warnings; the data file's status is retained.
- All 12 requested modules are selectable. Basic Statistics and overrepresented
  sequences use tables, tile quality uses a heatmap, and K-mer enrichment uses a
  bar chart with the complete reported table available. Other modules use the
  existing quality boxplot or distribution/content charts. Unknown future
  modules fall back to raw tables. Missing cells remain gaps and absent modules
  remain unavailable. Grouped base bins are never expanded or interpolated.
- Tool detection runs bounded asynchronous `--version` probes, supports PATH and
  explicit executable paths, and exposes versions and compatibility errors.
  Detection refreshes when the resolved executable or its modification time
  changes, with a 60-second cache expiry. No tool installation or environment modification occurs at runtime.
- FastQC-only, combined, and MultiQC-only reuse the same queue and process-group
  cancellation. MultiQC receives an explicit list of successfully parsed reports.
  Failed FastQC inputs or failed MultiQC produce partial results when native
  FastQC metrics are available. Duplicate sample names are surfaced instead of
  being silently overwritten in MultiQC.
- MultiQC-only accepts existing FastQC result directories or selected ZIP/data
  files. Discovery checks every traversed path and snapshots only QC reports and
  bounded companion files. ZIP/extracted copies with matching output paths are
  imported once, preferring the ZIP. Imports reject symlinks and are capped at
  20,000 visited entries, 64 directory levels, 500 reports, and 512 MiB of snapshots. Individual data
  and companion files are capped at 32 MiB; ZIP imports at 128 MiB. Original
  FASTQs are not included. Other upstream QC formats are outside this phase.
- Finished FastQC analyses offer **Generate MultiQC**. It creates a separate
  analysis from that run's saved reports without requiring the result store to
  be added to the input roots or rerunning FastQC.
- Reports retain original HTML attachments, normalized metrics, official
  outputs, imported report snapshots, logs, and manifests. MultiQC's structured
  general statistics are shown as stored, without unit conversions or display
  scaling. No report HTML or JavaScript enters the application DOM. The later
  [isolated report viewer](REPORT-VIEWER.md) adds sandboxed HTML previews through
  a dedicated endpoint while preserving these attachments.

## Persistence and API compatibility

New manifests and metrics use schema version 2 with additive fields. Completed
version-1 manifests and metrics are readable without a migration or rewrite.
Unfinished runs retain the existing interrupted-on-restart behavior and the
result-directory lock and atomic writes remain in place.

Manifests now retain required tool names, detected versions and executable paths,
resource parameters, input references and metadata, commands, per-command start
and finish timestamps, exit codes, and source-run references. Report snapshots
and normalized data allow imported results to reopen even after their originals
are removed. The output directory must remain on persistent storage.

Existing endpoints and the `tools` boolean configuration fields remain available.
`GET /api/config` adds `tool_details`; the booleans indicate usable versions.
`POST /api/runs` accepts QC directories as paths for MultiQC-only.
`POST /api/runs/{id}/multiqc` aggregates that finished run's saved FastQC directory
under the same session authentication and filesystem checks.

## Dependencies and configuration

No new Python or frontend package dependencies. FastQC 0.13.0 is the primary
version; 0.12.1 remains compatible. MultiQC must be >=1.25 and <2. Java is required
by FastQC. Load tools through the site's environment or configure
`QUALIDOCK_FASTQC` and `QUALIDOCK_MULTIQC` with executable paths before launch.
The application does not install them. K-mer availability follows FastQC's own
configuration; QualiDock does not calculate or enable it automatically.

## Validation — 2026-10-15

The following is the original Phase 2 verification record. Subsequent issue fixes and passing actual Linux/MultiQC CI are recorded in [ISSUES.md](ISSUES.md); those results supersede the original unvalidated tool/platform limitations below.

Final checks: **82 backend tests passed, 1 real-MultiQC test skipped; 36 frontend tests passed; TypeScript/Vite production build passed.** React module/report render checks and OOD template rendering/shell syntax checks also passed. The existing full ECharts bundle still produces Vite’s bundle-size warning.

- Real FastQC v0.13.0 / Java 17 generated the committed small paired fixtures and
  unmodified golden output containing all 12 modules, including tile and K-mer
  data and actual PASS/WARN/FAIL statuses.
- Parser tests compare all raw rows and statuses with that output. Frontend tests
  compare all chart series, bins, quantiles, and raw tooltip values, and exercise
  ECharts SVG rendering with actual data.
- The actual FastQC application integration test passes, including official
  downloads, unchanged inputs, exact saved metrics, and restart recovery.
- Backend coverage includes runtime detection, missing/incompatible tools,
  version-probe bounds, successful and failed execution, partial results,
  cancellation, directory snapshots, duplicate samples, legacy history, source
  removal, path traversal, escaped symlinks, downloads, and literal shell
  characters in input paths.
- The existing managed-macOS test fixture substitutes the RSS sampler because
  this sandbox denies subprocess `ps`. It does not substitute real FastQC.
  Running the standalone smoke script with the native sampler stops at that
  permission boundary. Native Linux resource enforcement still requires Linux
  execution; the production monitor has not been weakened for testing.
- MultiQC was not installed in the managed workspace. Its real combined-tool
  integration test is explicitly skipped, while subprocess-based orchestration
  tests pass. The real CI job now uses FastQC 0.13.0 and runs both the smoke script
  and the actual-tool tests. A passing CI run has not been claimed here.
- Browser automation providers were unavailable. React render checks and ECharts
  rendering pass; live browser interaction, mobile layout, and HPC deployment
  acceptance remain to be checked in their respective environments.

Run the checks:

```sh
.venv/bin/python -m pytest -q
npm test --prefix frontend
npm run build --prefix frontend

# Actual tools required; respects configured executable paths.
.venv/bin/python scripts/smoke-real-qc.py \
  --input-root backend/tests/fixtures/fastqc-0.13.0
```

For FastQC alone, add `--mode fastqc`. The real combined test must pass with an
installed compatible MultiQC before Phase 2's complete end-to-end acceptance is
claimed. No additional cosmetic work is required to proceed with that validation.

## File inventory

Modified:

- `backend/qualidock/metrics.py`, `manager.py`, `app.py`: parsing, existing execution
  workflow, persistence metadata, runtime detection API, saved-run aggregation.
- `frontend/src/AnalysisDetail.tsx`, `App.tsx`, `NewAnalysisForm.tsx`,
  `QualityChart.tsx`, `types.ts`, `styles.css`: module views, collapsible details,
  directory setup, versions, existing-result aggregation, structured summary.
- `backend/tests/conftest.py`, `test_workspace.py`: explicit version-aware
  orchestration fixtures and compatible failure tests; actual-tool tests are
  separate from these fixtures.
- `scripts/smoke-real-qc.py`, `.github/workflows/ci.yml`: actual-tool checks,
  executable configuration, FastQC-only option, FastQC 0.13.0 CI.
- `README.md`, `docs/OOD.md`, `docs/SECURITY.md`, `docs/VALIDATION.md`,
  `deploy/ood/template/before.sh.erb`: usage, validation record, and tool versions.

Added:

- `backend/qualidock/tools.py`, `reports.py`: bounded runtime detection and report
  discovery using the existing filesystem policy.
- `frontend/src/qc.ts`, `chartOptions.ts`, `QcModule.tsx`: reported-data adapters,
  ECharts options, and module tables using existing components and styles.
- `backend/tests/test_metrics.py`, `test_engines.py`, `test_real_tools.py`,
  `frontend/tests/qc.test.ts`: parser, execution, persistence, real tools, and chart
  checks.
- `backend/tests/fixtures/fastqc-0.13.0/`: two small compressed FASTQ inputs, their
  actual data/summary outputs, limits configuration, and provenance README.
- `docs/PHASE2.md`: this implementation and validation record.
