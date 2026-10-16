# Core-first architecture and intentional removals

QualiDock focuses on browsing FASTQs, FastQC/MultiQC, fastp/SeqKit, scientific QC
comparison and persistent results. Projects are removed entirely: no replacement
catalog, runtime SQLite dependency, project hierarchy or project-specific API.
The four navigation entries are Workspace, Quality Control, Read Processing and
Results. Existing within-analysis QC comparisons remain; cross-project cohort
analytics have been removed.

Removed: project/sample/sequencing-run CRUD and associations, project audit and
revision machinery, batch plans/attempts, cross-run cohort selection and review
rules, delivery inventories/targets/reconciliation, demultiplex evidence import,
release policies/reviewer decisions/bundles and optional Kraken2 execution.
Their routes, services, UI, configuration, tests and dedicated fixtures are gone.
Former administrative endpoints return 404. No compatibility wrappers remain.
No runtime package was needed solely for these features: SQLite was stdlib.
The Kraken2 CI installer and reference fixture were removed.

## Existing data

The application does not open or delete `projects.sqlite3`. Analysis manifests,
metrics, integrity evidence, report identities, registered historical artifacts,
original FASTQs and derived FASTQs are retained. Completed manifests are not
rewritten merely to strip obsolete administrative fields. Unknown historical
fields remain in the original downloadable JSON. An incomplete administrative
archive is never newly registered as a download.

For meaningful historical associations, stop every server using the store, then:

```bash
python3 scripts/export-legacy-projects.py /absolute/results/projects.sqlite3 /absolute/archive/projects.json
```

The one-shot exporter locks the existing store, opens the catalog read-only,
exports schema 1–3 entities, links, associations, evidence and administrative
rows with the original catalog SHA-256, and refuses to overwrite the destination.
The original catalog remains untouched. JSON fields inside archived rows remain
original strings for lossless recovery. Keep the database and export as private
archives; neither is needed to open scientific analyses. Unknown schemas,
symlinks, shared-writable catalogs and transaction sidecars are rejected.
The inspected development store had one project and no analysis associations;
no runtime data files were changed by the refactor.

## Responsibilities

- `files.py` / `sample_metadata.py`: restricted input access and file relationships.
- `store.py`: owned result roots, exclusive locks and atomic JSON persistence.
- `manager.py`: analysis lifecycle, shared execution slot, report registration.
- `executor.py` / `worker.py` / `resources.py`: safe commands, process groups,
  cancellation, CPU and memory budgets.
- `processing.py`: small fastp/SeqKit argument and output adapters using that same
  lifecycle; no independent execution engine.
- `metrics.py` / `reports.py` / `preview.py`: parsing, imports and isolated reports.
- `integrity.py` / `validation_jobs.py`: streaming full/quick validation with
  explicit coverage; no delivery or release-policy dependencies.

Atomic JSON helpers now live with persistence rather than forcing scanner
subprocesses to import the complete analysis manager. Scientific calculations,
FastQC/MultiQC execution and original HTML reports are unchanged.

## Audit and measured reduction

Compared with main `2f6a4be` (before this refactor), using tracked production Python
under `backend/qualidock` and TypeScript/TSX/CSS under `frontend/src`:

| Measure | Before | After |
| --- | ---: | ---: |
| Production files | 104 | 72 |
| Production lines | 24,402 | 14,526 |
| `App.tsx` lines | 1,492 | 988 |
| `app.py` lines | 444 | 311 |
| `manager.py` lines | 648 | 624 |

Production diff: **807 added, 10,683 removed**, net **9,876 fewer lines (40.5%)**.
The calculation includes both `ResultsList.tsx` and its former App implementation;
relocation is not counted as a net saving. Across the repository: five files added,
31 modified and 98 deleted, including intentionally obsolete tests and fixtures.
No runtime dependency was added. SQLite is absent from the runtime package.

Added files: `datasets.py` (exact derived-input authorization), `ResultsList.tsx`
(owned history queries, filters and rename controls), `test_core_scope.py`, this
guide and the offline exporter. The FastQC parser and chart calculations remain
unchanged. Atomic JSON helpers moved into the existing store module, removing the
scanner's manager import cycle. No new execution, persistence or workflow layer.

Deleted backend modules: `catalog`, `project_api`, `project_management`,
`project_intake`, `batch_jobs`, `cohort`, `delivery`, `delivery_service`,
`demultiplex`, `release_exports`, `release_policy`, `release_service`,
`release_worker`, `screening`, `screening_jobs`, `screening_worker`.
Deleted frontend features: all seven `Project*.tsx` components, `DeliveryReview`,
`DemultiplexReview`, `ReleaseReview`, `ScreeningReview` and their seven dedicated
TypeScript models/utilities. Their CSS, dedicated fixtures, tests, documentation,
CI installers and test invocations were removed together.

Core changes touch `app.py`, `manager.py`, `processing.py`, `sample_metadata.py`,
`validation_jobs.py`, `store.py`, `config.py`, `tools.py`, `integrity_worker.py`,
`App.tsx`, `AnalysisDetail.tsx`, the existing setup/results components, types,
processing request helpers, styling, retained regression tests, CI and docs.
The complete machine-readable file diff is `git diff --name-status 2f6a4be..HEAD`.

## Core workflow improvements

Registered derived FASTQs can be selected and reused without copying or broadening
input roots. Source IDs, snapshots, checksums and file/lane metadata persist.
Confirmed fraction sampling now validates mate order before and after actual
SeqKit execution; length filters and ID extraction remain explicitly independent.
The existing before/after FastQC implementation is reused, including exact grouped
bins and original tables. See [processing contracts](PROCESSING.md).

Results owns its history requests, search/sort and rename UI. The duplicate state
filter tabs were deleted; one state selector remains. Read-relationship editing,
output destination and resource settings are collapsed options in QC setup.
Removed administrative tasks are never resumed; old fields are archival data.

## Validation evidence

Local retained backend suite: **252 passed, 8 skipped** (the local installation
has no SeqKit). The missing-file error path and measured scan regression also pass
in a focused genuine-tool run. Frontend: **140 passed**, TypeScript/Vite build
passes; the existing ECharts bundle-size warning remains.

At `db21a90`, Linux CI passed backend (236 passed / 24 missing-tool skips), frontend,
1 CPU / 1 GiB resource validation, MultiQC 1.25.1 / 1.35 / latest 1.x, **17 genuine
processing cases without skips** and seven genuine QC/import/integrity cases.
The initial browser reuse case reached its new draft correctly but its test used
an exact accessible name that omitted the workflow button's description. The test
now targets the actual accessible name, and explicitly expands optional controls
before inspecting them; no assertion was disabled. Final browser evidence is
recorded after the correcting commit's CI completes.

One measured local genuine fixture run (400 reads per mate; fastp without optional
FastQC): 109,308 source-validation bytes, 99,971 output-validation bytes, four full
file scans, approximately 1.6 s wall / 1.1 s waited-child CPU. Source SHA-256 is
computed during structural validation, not a separate pass. The JSON artifact
records exact measurements and memory scope. macOS's denied process-group RSS
sampler is not claimed as a measurement; Linux uses the actual observer.
`RUSAGE_CHILDREN` high-water memory is explicitly cumulative and not an aggregate
per-workflow peak. External tool I/O, large-input scaling and NFS/Lustre throughput
are unavailable measurements, not extrapolations from this fixture.

Remaining deliberate limits: exact-number sampling, pair-preserving length/ID
filtering, immutable-evidence scan caching and cross-analysis trend dashboards
are not implemented. Report sandbox limitations and safe download fallbacks
remain. No OOD/PBS changes or deployment work were performed.
