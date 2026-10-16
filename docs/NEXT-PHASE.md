# Project, batch analytics and controlled delivery phase

Work proceeds in dependency order, one issue and logical implementation at a time.
FASTQ inputs remain read-only; only a separately requested, authorized delivery
operation in #24 may create destination copies. Existing QC and release manifests
remain authoritative and compatible. No deployment/scheduler work is included.

| Issue | Status | Acceptance / evidence |
|---|---|---|
| [#20](https://github.com/PhoenixEmik/QualiDock/issues/20) | Implemented; validation in progress | [Project model, API, storage decision, backup and rollback](PROJECTS.md). Local dedicated tests pass, including actual FastQC; full regressions and CI must pass before closure. |
| [#21](https://github.com/PhoenixEmik/QualiDock/issues/21) | Pending #20 | Project Workspace and sample/run UI; existing Workspace/Analyses navigation retained. |
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
CI evidence will be linked from #20 before proceeding to dependent implementation.

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
