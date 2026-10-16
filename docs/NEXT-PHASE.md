# Project, batch analytics and controlled delivery phase

Work proceeds in dependency order, one issue and logical implementation at a time.
FASTQ inputs remain read-only; only a separately requested, authorized delivery
operation in #24 may create destination copies. Existing QC and release manifests
remain authoritative and compatible. No deployment/scheduler work is included.

| Issue | Status | Acceptance / evidence |
|---|---|---|
| [#20](https://github.com/PhoenixEmik/QualiDock/issues/20) | Complete; issue closed | [Project model, API, storage decision, backup and rollback](PROJECTS.md). Fully green [CI 38855524020](https://github.com/PhoenixEmik/QualiDock/actions/runs/38855524020), commit `2117168`: backend/frontend/build, genuine QC/tools, Linux resources and 42 browser cases per browser. |
| [#21](https://github.com/PhoenixEmik/QualiDock/issues/21) | Implemented; validation in progress | Project Workspace, metadata CRUD/imports, audited file-association corrections and source QC/report drill-down. Browser acceptance is required before closure. |
| [#22](https://github.com/PhoenixEmik/QualiDock/issues/22) | Pending #20/#21 | Explicit batch planning, fingerprint-based reuse and bounded existing executors. |
| [#23](https://github.com/PhoenixEmik/QualiDock/issues/23) | Pending project/metric provenance | Comparable cohorts only; exact source metrics and declared outlier rules. |
| [#24](https://github.com/PhoenixEmik/QualiDock/issues/24) | Pending project/release foundations | Allowlisted, approved, verified destination copies; no source writes or unsafe overwrites. Actual shared-filesystem benchmarking remains dependent on authorized storage/data. |
| [#25](https://github.com/PhoenixEmik/QualiDock/issues/25) | Pending controlled delivery | Append-only lifecycle reporting and advisory retention; no automatic deletion. |

Local #20 verification: **278 backend tests passed** with actual FastQC, MultiQC
and Kraken2 available; **20 project-specific tests passed**, including actual
FastQC. The final input-validation guards were then rechecked by that dedicated
suite. Existing **138 frontend tests** and TypeScript/production build passed.
The managed macOS harness substitutes the sandbox-denied RSS observer only;
native Linux resource and actual-browser validation remain CI gates. Accepted
CI evidence is linked above; #20 was closed before starting dependent implementation.

Architectural decisions before dependent work:

- The SQLite registry stores domain relationships, not new scientific metric
  calculations or replacement QC/release records. Private database ownership uses
  the existing default store lock. Reliable filesystem locking is required.
- Names, assay/platform metadata and expected yields are explicitly declared;
  observed QC and transfer evidence remain separate and traceable.
- Project sample/run IDs and analysis-local file/group IDs have distinct roles.
  Associations are explicit; no ambiguous filename-based biological merges occur.
- Historical release decisions are immutable snapshots, never rewritten by a
  sample rename or later resequencing. Current readiness must be re-evaluated from
  existing source evidence before any eventual delivery.


Local #21 verification: the complete suite passed **292 tests**, including actual
QC tools; a subsequent atomic-import failure regression and identity-search guard
are covered by **35 focused project tests**. **141 frontend tests** and the final
TypeScript/production build passed. New real-browser cases cover project CRUD,
confirmed/corrected associations, original QC/reports, captured release evidence,
server restart, 120-row import/pagination, same-named project samples, keyboard and
390px layout. Those cases must pass in CI before #21 is marked complete.
