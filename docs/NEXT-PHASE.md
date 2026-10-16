# Project, batch analytics and controlled delivery phase

Work proceeds in dependency order, one issue and logical implementation at a time.
FASTQ inputs remain read-only; only a separately requested, authorized delivery
operation in #24 may create destination copies. Existing QC and release manifests
remain authoritative and compatible. No deployment/scheduler work is included.

| Issue | Status | Acceptance / evidence |
|---|---|---|
| [#20](https://github.com/PhoenixEmik/QualiDock/issues/20) | Complete; issue closed | [Project model, API, storage decision, backup and rollback](PROJECTS.md). Fully green [CI 38855524020](https://github.com/PhoenixEmik/QualiDock/actions/runs/38855524020), commit `2117168`: backend/frontend/build, genuine QC/tools, Linux resources and 42 browser cases per browser. |
| [#21](https://github.com/PhoenixEmik/QualiDock/issues/21) | Complete; issue closed | Project Workspace, metadata CRUD/imports, audited file-association corrections and source QC/report drill-down. Fully green [CI 38861150941](https://github.com/PhoenixEmik/QualiDock/actions/runs/38861150941), `291d6ef`; 48 browser cases per target. |
| [#22](https://github.com/PhoenixEmik/QualiDock/issues/22) | Complete; issue closed | [Batch planning, provenance, limits and API](BATCH-QC.md). Browse-first registration and checkbox cohorts. Fully green [CI 38869158008](https://github.com/PhoenixEmik/QualiDock/actions/runs/38869158008), `328c604`: actual tools/resources, 316 backend + provisioned missing-tool cases, 143 frontend/build, 54 browser cases per target. |
| [#23](https://github.com/PhoenixEmik/QualiDock/issues/23) | Implemented; CI acceptance pending | [Compatible cohort projections, exact fractions and declared review rules](COHORT-COMPARISON.md). Actual FastQC low-Q30/restart test passed; 353 full local backend tests passed; 26 focused cohort and 147 frontend tests/build passed. Browser/CI acceptance pending. |
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

Accepted #21 CI at `291d6ef`: **283 backend tests passed**, with 11
missing-tool cases covered by provisioned actual-tool jobs; **141 frontend tests**
and production build passed. Actual FastQC/MultiQC compatibility, optional Kraken2
and Linux resource checks passed. **48 browser cases passed per matrix target**,
including project relationship persistence and original manifest/source preservation.
The initial failed select-label regression was fixed without skipping tests.
The association audit race regression passed in the 36-test focused project suite.

Accepted #22 CI at `328c604`: **316 backend passed**, 12 absent-tool cases
covered by provisioned real-QC/screening jobs; **143 frontend passed**, production
build, genuine FastQC 0.13.0 and MultiQC 1.25.1/1.35/latest 1.x, Linux resource
limits and optional Kraken2 all passed. Per browser target: **12 project cases +
42 existing regressions**, all successful. Source synthetic fixture bytes and
pre-existing scientific artifacts remained unchanged. Native screenshots live
in CI artifacts and were visually inspected. The browse-first test polling
client defect was fixed, not skipped. Detailed [batch API and limits](BATCH-QC.md)
and [name-only / browse-first workflow](PROJECTS.md) document the accepted changes.

#23 local implementation verification: **353 backend tests passed** with actual FastQC,
MultiQC and Kraken2 available, plus the final **26 focused cohort cases** (including
new pagination/security regressions). **147 frontend tests** and production build
passed. The actual low-Q30 FastQC/full-validation/restart regression passed. Browser
acceptance remains pending and #23 stays open until the CI matrix is green.
