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

## Audit and measured reduction (simplification release `1914146`)

Compared with main `2f6a4be` (before this refactor), using tracked production Python
under `backend/qualidock` and TypeScript/TSX/CSS under `frontend/src`:

| Measure | Before | After |
| --- | ---: | ---: |
| Production files | 104 | 72 |
| Production lines | 24,402 | 14,525 |
| `App.tsx` lines | 1,492 | 988 |
| `app.py` lines | 444 | 311 |
| `manager.py` lines | 648 | 624 |

Production diff: **806 added, 10,683 removed**, net **9,877 fewer lines (40.5%)**.
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
Confirmed sampling validates mate order before and after actual SeqKit execution.
The subsequent core-processing enhancement adds opt-in pair-preserving length/ID
selection and exact-count sampling; see the current processing contracts below.
The existing before/after FastQC implementation is reused, including exact grouped
bins and original tables. See [processing contracts](PROCESSING.md).

Results owns its history requests, search/sort and rename UI. The duplicate state
filter tabs were deleted; one state selector remains. Read-relationship editing,
output destination and resource settings are collapsed options in QC setup.
Removed administrative tasks are never resumed; old fields are archival data.

## Validation evidence for the simplification release

Local retained backend suite: **252 passed, 8 skipped** (the local installation
has no SeqKit). The missing-file error path and measured scan regression also pass
in a focused genuine-tool run. Frontend: **140 passed**, TypeScript/Vite build
passes; the existing ECharts bundle-size warning remains.

Final production-code [CI 38899079194](https://github.com/PhoenixEmik/QualiDock/actions/runs/38899079194)
at `1914146` is fully green: Linux backend (236 passed / 24 missing-tool skips),
frontend 140 tests and build, 1 CPU / 1 GiB resource validation, actual MultiQC
1.25.1 / 1.35 / latest 1.x, **17 genuine processing tests without skips**, seven
genuine QC/import/integrity tests, and **42 Chromium browser tests** (six native
processing/reuse plus 36 retained regressions). The provisioned jobs execute the
missing local-tool cases; skips are not counted as scientific validation.

An initial browser reuse test omitted descriptive text from a button's accessible
name. Its locator was corrected, and optional controls are explicitly expanded
before inspection. The full subsequent browser run passed; no supported-feature
assertions were disabled. Browser validation uses standalone and both existing
URL-prefix layouts, without a Firefox job or new deployment work. Screenshots and
measured I/O JSON are in that run's artifacts. A reviewed result screenshot is also
available locally under `validation/core-first/processing-comparison.png` (ignored,
not added to the source distribution).

The final follow-up commit changes this validation document only. It uses a
`[skip ci]` message because the complete production/test tree above has already
passed; no code, test or CI configuration changes are excluded from validation.

One measured local genuine fixture run (400 reads per mate; fastp without optional
FastQC): 109,308 source-validation bytes, 99,971 output-validation bytes, four full
file scans, approximately 1.6 s wall / 1.1 s waited-child CPU. Source SHA-256 is
computed during structural validation, not a separate pass. The JSON artifact
records exact measurements and memory scope. macOS's denied process-group RSS
sampler is not claimed as a measurement; Linux uses the actual observer.
`RUSAGE_CHILDREN` high-water memory is explicitly cumulative and not an aggregate
per-workflow peak. External tool I/O, large-input scaling and NFS/Lustre throughput
are unavailable measurements, not extrapolations from this fixture.

At that release, exact-number sampling and pair-preserving length/ID filtering
were not implemented; the subsequent enhancement is documented in PROCESSING.md.
Immutable-evidence scan caching and cross-analysis trend dashboards remain outside
the implemented scope. Report sandbox limitations and safe download fallbacks
remain. No OOD/PBS changes or deployment work were performed.

## Focused cleanup audit — 2026-10-16

Baseline: `9d7aa49`, after the paired-processing enhancement. This is a bounded
cleanup, separate from the earlier 40.5% reduction above.

| Decision | Evidence and action |
| --- | --- |
| Remove | Release notes still advertised delivery/release review and Kraken2; corrected. The unused client-side `analysisManagement.ts` had only test callers; deleted with that dedicated test. Its filter/sort assertions now exercise the actual backend history contract. One unused Python import was removed. |
| Consolidate | General QC and fastp duplicated MultiQC file lists, argv, configuration, JSON reads and unique source-name matching. `multiqc.py` shares only those operations; input collection, naming depth/fullnames, expected samples, mapping severity and partial-result policy remain explicit in each caller. |
| Consolidate | QC/processing share optional relationship review in the existing SampleEditor module. App stores a single metrics response and uses one session reset, including derived authorities; reconciliation is calculated once. Results stores one history response/query, without a filter-reset effect or client-side duplicate filtering. |
| Retain | LocalExecutor, manifest versions, output locks, validators, report sandbox, scientific fixtures and all supported core workflows. No replacement job manager, database, form framework or dependency. |
| Retain | Documented full-list API and default legacy SSE, still used by repository benchmarks/tests and potentially external clients; the frontend exclusively uses paginated/revision paths. See HISTORY.md. |
| Defer | Artifact registry caching or direct-output rewrites: no measured evidence justifies their additional security/lifecycle complexity. Large-input/shared-filesystem work remains issue #5. |

The local artifact observation used isolated synthetic directory layouts containing
copies of genuine FastQC report text, never FASTQ copies or invented metrics. Three
instrumented scans per layout measured a median **2.72 ms for 10 report files** and
**155.33 ms for 1,000 report files**, including manifest registration/write. Path.stat
calls were 58–61 and 4,018–4,021 respectively. Twenty repeated history/list/directory
reads triggered **zero** artifact scans. Scans occur at FastQC batch completion,
analysis finalization and explicit integrity-validation completion/cancellation.
These are local macOS metadata observations, with instrumentation overhead, not
NFS/Lustre or large-FASTQ acceptance. The existing publication/containment rules
remain unchanged. The observation and one-shot reproduction script are retained
locally under ignored `validation/cleanup/`; this is not a new benchmark framework.

Issues #24/#25 were closed as intentionally not planned, with their original
proposals retained. Issue #7 now separates standalone release acceptance from
optional site integration and measured-performance claims. No tag or release was
created. Historical scientific analyses, archived catalogs and validation evidence
were not deleted. RELEASING.md and VALIDATION.md now describe the current scope;
PHASE2.md is clearly a historical record with its meaningful original evidence.

Cleanup production inventory (`9d7aa49` → `6361f43`): **233 lines added, 231 removed,
net +2**, 73 production files before/after (14,866 → 14,868 lines). This is reduced
duplication and clearer ownership, not a claimed line-count reduction. App state
calls fell 34 → 33; ResultsList fell 14 → 8. AnalysisDetail's independent module,
sample and comparison choices remain intact; it was reviewed without a speculative
rewrite. No runtime dependency was added or removed.

Added: `backend/qualidock/multiqc.py`, `backend/tests/test_multiqc_shared.py`.
Deleted: `frontend/src/analysisManagement.ts`. Modified: backend manager, processing
and outcomes; App, ResultsList, SampleEditor and the two setup forms; backend history
and processing regressions; frontend management tests; the processing/history
browser tests; CI; README and this guide, HISTORY.md, PHASE2.md, RELEASING.md and
VALIDATION.md. The machine-readable diff is `git diff --name-status 9d7aa49..6361f43`
(2 files added, 20 modified, 1 deleted). Local details are also retained under
`validation/cleanup/change-inventory.json`.

[Accepted cleanup CI 38918679043](https://github.com/PhoenixEmik/QualiDock/actions/runs/38918679043)
passed at `6361f43`: backend 269 passed/29 tool cases covered by provisioned jobs;
frontend 141 tests/build; 47 processing cases with MultiQC 1.35 and seven
QC/import cases per supported MultiQC target; Chromium 45 and Firefox 21 critical cases; Linux 1 CPU / 1 GiB
resource/process checks. Local full genuine-tool suite: 298 passed, zero skips.
Both browsers caught the stale-session pairing regression; resetting reviewed
metadata and derived/rerun context fixed it. Official reports, source checksums,
registered datasets and historical manifests remain unchanged. New runs share
`multiqc-config.json`; old per-workflow config artifacts remain downloadable.

Remaining debt is explicit: full-list compatibility payloads are still large when
requested, startup loads existing manifests, artifact discovery still walks result
directories, the ECharts bundle-size warning remains, and large/shared-storage/site
acceptance is unverified. These do not justify a new cache, database or framework
in this cleanup. See VALIDATION.md for evidence boundaries.
