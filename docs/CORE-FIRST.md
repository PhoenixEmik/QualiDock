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
