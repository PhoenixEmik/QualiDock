# QualiDock

A single-user sequencing QC workspace for Linux workstations and HPC compute nodes. Browse existing FASTQ files, run FastQC and MultiQC, process reads with fastp or focused SeqKit utilities, inspect native charts and before/after QC, and download persistent reports and derived datasets.

**Status: v0.1 development, not an accepted release.** Standalone Linux and an HPC deployment through Open OnDemand must pass end-to-end acceptance before tagging v0.1.0. See [validation](docs/VALIDATION.md).

## Run locally

Requirements: Linux, Python 3.11+, Node.js 22+, Java, FastQC **0.13.0** (also compatible with 0.12.1), and MultiQC 1.25+ (below 2). Install QC tools through your site's modules or a dedicated Bioconda environment. Keep that environment on `PATH` when starting QualiDock. Optional read processing uses fastp 0.23–1.x and SeqKit 2.6–2.x; see [native processing, defaults and provenance](docs/PROCESSING.md). Missing optional tools do not prevent existing QC workflows.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
cd frontend
npm ci
npm run build
cd ..

# Optional: generate small, explicitly synthetic paired-end input files.
python3 scripts/create-example-data.py

# Configure directories already on this host; input roots must exist.
export QUALIDOCK_ROOTS='["/absolute/path/to/fastq", "/absolute/path/to/fastqc-reports"]'
export QUALIDOCK_OUTPUT="/absolute/path/to/persistent/qualidock-results"
./scripts/start.sh
```

Open the connection URL printed at startup. Its fragment carries a random session token; the browser exchanges it for an HttpOnly cookie and removes the fragment. Alternatively, paste the token into the login screen. Keep the URL private. The token is regenerated on restart unless `QUALIDOCK_TOKEN` is supplied. Existing results remain available after authenticating the new session.

Without `QUALIDOCK_ROOTS`, the app uses the generated `example-data` directory. The default output directory is `runs` in this checkout. FASTQ inputs are never uploaded, modified, or relocated. Run under a regular Unix account. One server process/worker may own an output directory at a time.

For more test inputs, run `python3 scripts/prepare-test-data.py --download-public`.
This adds small, checksum-verified public yeast RNA-seq subsets and clearly labeled
synthetic multi-lane, manual-pairing, QC-profile and 24-read cohort scenarios under
`example-data/testing`. See [test datasets and provenance](docs/TEST-DATA.md).

## Workspace

- **Workspace:** browse connected storage, navigate directories, and select inputs. Switch between **Samples** (grouped detected read pairs) and **Files** (individual files). Incomplete pairs and unrecognized names remain available. Search covers currently loaded sample names and filenames; load more to include additional entries.
- **Quality Control:** configure FastQC-only, combined FastQC/MultiQC, or existing-report MultiQC runs.
- **Read Processing:** execute fastp, SeqKit statistics, seeded fraction sampling, length filtering or exact read-ID extraction. Select FASTQs using the existing browser; advanced settings remain optional.
- **Results:** find running, queued, completed, failed, partial, interrupted, or cancelled runs. Open an analysis for **Overview & logs**, **QC metrics**, and **Reports**. The UI displays the actual job state and stage, without estimated progress percentages.

Use **New analysis** in the Workspace, or configure the current selection, to choose FastQC + MultiQC, FastQC only, or MultiQC only and set a bounded thread count. Selecting a confirmed pair in Samples includes both mates, even if directory pagination splits them. Files mode supports individual-read selection; partial selections remain visible when switching views.

Large folders use bounded name snapshots and page-only metadata reads; see [browsing behavior and the 100,000-entry benchmark](docs/BROWSING.md). A changed or expired listing requires Refresh; source selections remain intact.

Each analysis retains native per-base quality boxplots, mean quality, GC distributions, base content, length, N content, adapter content, and module checks when actual parsed data is available. Its Reports section previews registered HTML outputs in an opaque-origin sandbox, with MultiQC selected first when present. Original HTML/ZIP outputs, normalized metrics, logs, and manifests remain downloadable. Strict isolation keeps application cookies and real browser storage inaccessible. MultiQC uses temporary frame-private settings that reset on reload. External assets/services, form-based controls such as MultiQC text filters, and in-report exports remain blocked; use the original download for those features. See [report viewer behavior and validation](docs/REPORT-VIEWER.md).

QC Metrics includes clickable module statuses, optional explanatory notes, paged Raw Data tables and exact CSV/TSV exports. New analyses with confirmed, persisted R1/R2 relationships can compare reported quality and compatible QC profiles. Incompatible bins stay on separate original axes, and old/unpaired results remain individually accessible. See [native FastQC behavior and comparison rules](docs/NATIVE-FASTQC.md).

New analysis supports manual pair review/correction, single-end assignments and sample/lane grouping. Choose a persistent output location from configured roots, then rename or reopen a saved configuration from Results. Grouping never merges FASTQ files or QC distributions. See [sample and analysis management](docs/SAMPLE-MANAGEMENT.md) for output-root configuration, locking, API additions and compatibility.

QC Metrics includes a native **Overview** with sortable/exportable MultiQC General Statistics and a clickable QC status heatmap, existing **Sample Details**, and **Compare Samples** with shared read-file selection, six supported comparison modules, and source/chart exports. See [native analytics, scientific constraints and compatibility](docs/NATIVE-ANALYTICS.md).

The workspace uses neutral slate surfaces and blue controls, independently of the FastQC scientific palette. Native quality plots retain yellow quartile boxes, red medians, blue means and quality-region backgrounds. See [palettes, visual fidelity and validation](docs/CHART-FIDELITY.md).

Mate detection recognizes `_R1`/`_R2`, `.R1`/`.R2`, `-R1`/`-R2`, and corresponding `1`/`2` suffixes, optionally followed by `_001` (or equivalent separator). A pair is confirmed only when exactly one of each mate exists in the same directory. Both mates must be selected; unpaired files can also run. Each FASTQ is assessed independently.

For **MultiQC only**, enter an existing QC results directory within a configured root, or select `*_fastqc.zip` / `fastqc_data.txt` files. Directory imports discover FastQC reports recursively, validate every path, and snapshot only bounded QC reports and their summary/HTML companions. FASTQ data is never copied or rerun. ZIP/extracted copies of the same result are imported once. Other QC tool formats remain outside this phase. Directory imports are limited to 20,000 entries, 500 reports, and 512 MiB of report snapshots.

Use **Generate MultiQC** in a finished analysis to aggregate its saved FastQC results into a new run, even when the result store is outside the configured input roots. Successful FastQC results remain available if MultiQC fails. Identical FASTQ basenames in different directories use isolated official-output namespaces and exact source mapping. MultiQC adds directory prefixes when report names collide; missing expected summary rows are reported instead of silently merging inputs. Analysis details show recorded per-file outcomes and completed counts without estimated percentages.

The QC module selector covers Basic Statistics, per-base and per-sequence quality, sequence content, GC, N content, length, duplication, overrepresented sequences, adapters, per-tile quality, and K-mer content. Basic Statistics and overrepresented sequences use native tables; tiles use a heatmap; K-mers include an enrichment chart and their complete reported table. Optional or missing modules show an unavailable state. K-mer analysis follows the installed FastQC configuration and is not enabled or calculated by QualiDock. Exact table values and grouped bins are retained. Sample Details can be collapsed.

History uses paginated summaries and revision-only SSE notifications; full manifests
are fetched for the selected analysis. Legacy endpoints remain compatible. See
[history behavior and payload benchmarks](docs/HISTORY.md). CSV/TSV exports offer
explicit [spreadsheet-safe and verbatim formats](docs/EXPORTS.md).

Analysis Overview also provides optional [read-only FASTQ integrity validation](docs/INTEGRITY.md):
full gzip/record checks, source SHA-256 and configured mate identifier/order checks.
Quick or interrupted scans retain explicit incomplete coverage.

Every processing operation writes to a new analysis directory, never to the
original FASTQ file. Advanced parameters are optional. See [processing](docs/PROCESSING.md).

Project catalogs, batch planning, cross-run cohorts, delivery policies, release
review and optional Kraken2 screening have been removed from the application.
Existing analysis manifests, reports and source/derived FASTQs are preserved.
See [the simplification and safe legacy export guide](docs/CORE-FIRST.md).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `QUALIDOCK_ROOTS` | `["<checkout>/example-data"]` | JSON array of readable, existing directory roots |
| `QUALIDOCK_OUTPUT` | `<checkout>/runs` | Persistent per-user output storage |
| `QUALIDOCK_FRONTEND` | `<checkout>/frontend/dist` | Built frontend directory |
| `QUALIDOCK_TOKEN` | Random per session | Shared session secret; supply through a protected environment |
| `QUALIDOCK_CPUS` | Detected capacity | CPU upper bound, also bounded by affinity, cgroup and scheduler variables |
| `QUALIDOCK_MEMORY_MB` | 4096, bounded by host/cgroup memory | Total session memory budget; set explicitly to the PBS allocation |
| `QUALIDOCK_PREFIX` | Empty | External URL prefix, e.g. `/node/compute.example/8765` |
| `QUALIDOCK_SECURE_COOKIE` | `0` | Set to `1` when the external connection uses HTTPS |
| `QUALIDOCK_FASTQC` | `fastqc` | Executable name or absolute path |
| `QUALIDOCK_MULTIQC` | `multiqc` | Executable name or absolute path |
| `QUALIDOCK_FASTP` | `fastp` | Optional native processing executable |
| `QUALIDOCK_SEQKIT` | `seqkit` | Optional FASTQ utility executable |

The session footer shows detected tool versions; setup explains missing or incompatible tools. Detection uses bounded asynchronous version probes (`seqkit version`, otherwise `--version`) and never installs software. Explicit executable paths are supported through the variables above.

The application runs one analysis at a time; other runs queue. FastQC threads are bounded by CPU capacity and a conservative 768 MB per thread with a 512 MB session reserve. Tool process groups inherit a Linux CPU affinity limit. A process-group RSS monitor samples every 500 ms and terminates a run that exceeds the tool memory budget; this is not a replacement for a scheduler/cgroup hard memory limit. MultiQC executes in the same allocation with numerical library thread limits. The runtime does not submit scheduler jobs.

## Development and checks

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run build
```

Run `npm test` in `frontend` for sample grouping, selection, directory pagination, missing inputs, and exact chart-data checks against real FastQC 0.13.0 output. These use Node's built-in test runner and TypeScript stripping (Node 22.6+).

For frontend development, start the backend on port 8765, then `npm run dev` in `frontend`. Vite proxies `/api` to the backend. Open the Vite URL and paste the backend's token on the login screen. Production serves the built frontend and API from the same FastAPI process.

For the real-tool smoke test:

```bash
python3 scripts/create-example-data.py --reads 1000
.venv/bin/python scripts/smoke-real-qc.py
```

The smoke test requires real executables and checks paired-end inputs, FastQC/MultiQC execution, generation from existing results, exact report metrics, downloads, unchanged inputs, and restart persistence. Use `--mode fastqc` when validating FastQC alone, and `--input-root backend/tests/fixtures/fastqc-0.13.0` to use the small bundled paired inputs. Both modes respect configured executable paths. It uses a temporary results directory and deletes only its own outputs. CI defines Linux backend tests, frontend compilation, and this real-tool smoke test.

## Open OnDemand

The [Batch Connect adapter](deploy/ood) launches this same standalone server on a PBS-allocated compute node. See [the OOD deployment guide](docs/OOD.md) for site configuration and acceptance checks. Configure your site's cluster ID, queue/account, module names, and shared installation paths.

See [Phase 2 implementation, changed files, and validation](docs/PHASE2.md) for detailed engine and reporting behavior.

## Architecture and security

`React → FastAPI REST/SSE → RunManager → Executor → FastQC / MultiQC / fastp / SeqKit`

The core package has no OOD or PBS API dependency. `Executor` defines execution and cancellation; `LocalExecutor` uses subprocess argument arrays and independent process groups. Each run has `manifest.json`, `analysis.log`, `fastqc/`, `multiqc/`, and `metrics.json`. Queued/running runs from a prior session are restored as interrupted; completed results are read from disk. See [security assumptions](docs/SECURITY.md).

Metrics are parsed from bounded `fastqc_data.txt` and `summary.txt` files in FastQC ZIPs or extracted result directories, without extracting archives. Raw cells, metadata, summary statuses, and unsupported module tables are preserved. MultiQC general statistics are read from its structured JSON without applying display scaling. New version-2 manifests add tool versions, command arguments, exit codes, resource parameters, and source-run references; version-1 records remain readable without rewriting completed runs. Per-base categories preserve FastQC's grouped positions; quartiles and 10th/90th percentiles are preserved. No Q30 fraction is inferred from these aggregated statistics.

Licensed under [GNU GPLv3](LICENSE). FastQC, MultiQC, Apache ECharts, and other dependencies retain their respective licenses.

MultiQC-only imports also accept existing fastp JSON reports without processing
FASTQs. See [QC imports](docs/QC-IMPORTS.md).
