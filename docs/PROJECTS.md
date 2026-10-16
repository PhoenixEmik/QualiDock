# Persistent project registry

## Scope and identity

The project registry is separate from the existing QC execution/result store.
`Project → Sample` and `Project → SequencingRun` records have UUID-based stable
identities. Labels and declared identifiers are editable, non-unique metadata;
the same `S1` label in different projects never establishes identity. A sample
can participate in several sequencing runs, and a run can contain several samples.

An explicitly linked analysis can contain file-level associations to both a
sample ID and a sequencing-run ID. Lane, chunk, library identifier and read role
are user-confirmed declarations. The saved source snapshot, report ID, checksum
availability and original QC association are recorded separately as observed
evidence. No filename inference is promoted to biological proof, and no reads,
lanes or QC distributions are merged. Original FASTQs remain read-only.

An analysis belongs to at most one project. Linking never rewrites the analysis
manifest or its official reports. Omitted file assignments mean **unresolved**,
not a guessed sample. Unassigned legacy analyses remain accessible through the
existing Analyses workspace and `/api/unassigned-analyses`.

## Storage decision and compatibility

`<QUALIDOCK_OUTPUT>/projects.sqlite3` contains only domain metadata, associations,
append-only audit events and immutable evidence snapshots. Python's standard
library supplies SQLite; no server, ORM or additional dependency is required.
The existing per-user exclusive default result-store lock owns the registry.
The database and journal files must be regular, singly linked, user-owned and
private; parent storage must not be writable by other users. Symlinked/replaced
files, future schema versions and unversioned databases fail closed.

Transactions use foreign keys, rollback/DELETE journaling and FULL synchronization.
WAL is not used. Filesystem locking/durability must be reliable; small local tests
are not validation of NFS/Lustre semantics. Use a persistent local default store
for the registry where shared-storage locking is uncertain; existing additional
configured result stores can still contain QC artifacts. An ephemeral session
directory is unsuitable for the default persistent registry. See the official
[SQLite locking description](https://www.sqlite.org/lockingv3.html).

Schema version 1 introduced the registry. Version 2 adds only an optimistic
association revision column and audit lookup indexes in an atomic migration;
existing IDs, snapshots and scientific files remain unchanged. Version 3 adds
immutable batch plans and separately tracked execution attempts; it preserves
all prior project/QC/release identities. Existing
v1/v2 analysis manifests and release manifests are not migrated or rewritten.
`PRAGMA user_version` gates future migrations. Unknown/newer versions are refused
without rewriting the database or QC results; do not manually lower the version.
An old QualiDock version can still open unchanged QC manifests, but will not show
project metadata. Preserve the database for a later compatible upgrade.

Metadata edits require the currently displayed `revision`; stale updates return
409. Archive/restore is the supported removal lifecycle (`status`); destructive
DELETE endpoints are intentionally absent. An attached analysis cannot silently
move projects. Unresolved files can be explicitly assigned later. Corrections
require the association's current revision and a reason; one transaction appends
the complete previous/current record to audit events and updates the current
projection. Historical evidence remains unchanged. A correction cannot change
the association's source file ID.

## Scientific provenance

`POST .../analyses/{link_id}/evidence` captures terminal QC state, tool versions,
execution parameters, exact saved metrics SHA-256 and then-current declared
sample/run metadata. Optional `sample_ids` are the **existing analysis-local
sample-group IDs** for the release evaluator, not project sample IDs. Its exact
release fingerprint, policy and decision are captured without changing them.
Repeated captures of the same snapshot are idempotent. Later declarations or
release decisions produce another snapshot; historical captures remain intact.
Concurrent metadata/QC changes cause a 409 and require recapture.

Project counts are record counts, never a fabricated QC completion percentage.
Project QC/release readiness remains `unknown`; review must drill into
the actual analysis. A saved approval is historical evidence and does not itself
prove present source freshness, successful transfer or biological identity.
Evidence and audit tables reject UPDATE/DELETE. This prevents application-level
rewrites, not a malicious Unix owner editing their own database or source files.

## Authenticated API

All endpoints retain existing session/bearer authentication, CSRF header and
same-origin protections. Relationship endpoints accept stable IDs. Browse-first intake accepts the same
allowlisted FASTQ references and reviewed sample configuration as normal analysis
creation; it reuses all existing path/pairing validations. Batch previews omit
source paths and show the explicitly configured output root. File assignments
reuse the authorized analysis inventory and revalidate source access; original
reports stay behind the existing registered artifact and isolated-preview APIs.

- `GET/POST /api/projects` (create body `{ "fields": { "display_name": "Study" } }`).
- `GET/PATCH /api/projects/{id}` (patch body `{ "revision": 1, "fields": { ... } }`).
- `GET/POST /api/projects/{id}/samples` and `/sequencing-runs`.
- `GET/PATCH /api/projects/{id}/samples/{sample_id}` and `/sequencing-runs/{run_id}`.
- `GET/POST /api/projects/{id}/analyses`; attach body has `analysis_id` and optional
  `assignments` with `file_id`, `sample_id`, `sequencing_run_id`, `lane`, `chunk`,
  `library_identifier`, `read`, `source` (`user_confirmed` / `user_assigned`).
- `GET /api/projects/{id}/associations`.
- `POST /api/projects/{id}/analyses/{link_id}/evidence`; body `{}` for QC or
  `{ "sample_ids": ["analysis-local-group-id"] }` for a release scope.
- `GET /api/projects/{id}/evidence/{evidence_id}`.
- `GET /api/projects/{id}/evidence` returns bounded snapshot summaries; complete
  evidence is fetched only when explicitly opened.
- `GET /api/unassigned-analyses`.

Collections use `offset`/`limit` (default 25, maximum 100); sample/run/project lists
also support literal `search` and `status=active|archived|all`. No multi-tenant/RBAC
claim is made: all authenticated operations execute for the current Unix owner.
Project Workspace is available under Workspace → Projects; existing
Workspace/Analyses navigation and standalone analysis creation remain available.

## Backup, upgrade and recovery

Stop QualiDock cleanly before a coherent application backup. Copy **all configured
result roots**, including `projects.sqlite3`, manifests, review sidecars and report
artifacts, to a private, access-controlled backup. Preserve permissions, canonical
store paths and any SQLite rollback journal; do not selectively discard a journal
after an unclean exit. Original FASTQs are references and need their own retention
and backup plan.

For a registry-only online snapshot, Python's
[`Connection.backup`](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup)
or the SQLite [backup API](https://www.sqlite.org/backup.html) produces a consistent
database image. That alone is **not** a synchronized backup of QC/release artifacts.
Use a new private backup file and do not copy an actively written database with a
plain file-copy command.

Before upgrade, record the application commit and preserve a full offline backup.
After upgrade, verify project/sample/run IDs, linked analyses and original reports.
For rollback, stop all owning sessions, restore the matching backup to the original
canonical result-store locations with original private permissions, then start
the matching application version. Never merge conflicting databases or rewrite
approval snapshots. Missing/offline result stores are unavailable evidence rather
than permission to create replacement reports. Validate filesystem locking on
the intended storage before operational use. This phase adds no scheduler or
deployment integration.

## Acceptance evidence (#20)

Automated tests cover multiple samples/runs, resequencing, duplicate labels,
explicit lane/read associations, legacy unassigned analyses, timestamp/ID stability,
restart, future-version rollback refusal, transactional rollback, concurrent
metadata writes, archive/restore, stale edits, source symlinks/missing files,
cross-project references, authentication/CSRF, private storage and immutable
approval/evidence capture. An actual FastQC 0.13.0 integration verifies saved
metrics hashes, official HTML download bytes, restart and unchanged source hashes.
The existing frontend/build/browser suites remain regression gates. CI evidence
and the next issue's status are recorded in [NEXT-PHASE.md](NEXT-PHASE.md).


## Project Workspace (#21)

Open **Workspace → Projects**. Main navigation remains Workspace/Analyses; Files
retains the explorer and standalone New analysis workflow. Create/search/edit/archive
projects, then manage paginated Samples and Sequencing runs. Repeated labels show
stable IDs. Assay/library/expected yield and platform/date/stage fields are declared,
not independently observed. Blank yield is unknown; zero is retained. Expectations
do not create release rules or combine yield across runs.

Import UTF-8 CSV/JSON sample metadata (1 MiB, 500 rows). Preview precedes atomic
commit; duplicate submissions reuse the initial import, and stale previews conflict.
Existing/ambiguous identifiers require explicit resolution, never auto-upserts or
filename-based matching. SHA-256 covers submitted UTF-8 text, not a differently
encoded original file. Audit records include actual Unix actor and source format.

Under **Analyses & evidence**, attach an existing unassigned analysis, then use
**Assign / inspect files** to confirm explicit file subsets against sample/run IDs.
Search identity pickers for records beyond the initial 100 matches. Leave ambiguity
unresolved. Corrections require a reason and preserve previous/current records.
Samples/runs drill into associated lane/read results; analysis buttons open existing
Overview, native QC or isolated Reports. Metadata operations do not execute QC,
copy FASTQs or change source manifests/reports.

Capture QC-only metadata or an evaluated existing analysis-local release scope.
Snapshots display captured status/time, not derived current project approval.
Analysis approval applies to the original file/group scope; capturing it alongside
project declarations does not certify a new biological identity. Open the source
review to inspect current evidence. Keyboard tabs, responsive scrollable tables and
loading/error/empty states use existing styles and authentication.

Additional authenticated endpoints:

- `POST /api/projects/{id}/samples/import`: `format`, `content`, optional preview
  `fingerprint` (omit to preview; include to commit).
- `GET /api/projects/{id}/analyses/{link_id}/inventory`: bounded original identities
  and associations, omitting absolute source paths.
- `POST /api/projects/{id}/analyses/{link_id}/assignments`.
- `PATCH /api/projects/{id}/associations/{association_id}`: `revision`, full
  `assignment`, mandatory `reason`.
- Association listings accept explicit `sample_id` / `sequencing_run_id` filters.

Schema v1 backups migrate on startup. Before using an older project-aware version
that cannot read v2, restore a matching full backup. Do not lower `user_version`.
QC-only pre-registry versions still read unchanged manifests but cannot show
project relationships. No deployment/scheduler changes are included.

## Browse-first workflow

Create a project using just its name, then choose **Browse & select FASTQs**.
The existing File Explorer supports selecting whole sample groups, lanes or
individual reads across directories. **Configure analysis** opens the existing
sample/pair review and QC settings. **Run analysis** creates a new organizational
sample for each reviewed group, a sequencing-run record and all file/analysis
links in one registry transaction. Assay, platform, sequencing date and expected
yield remain unspecified; they can be edited later under **Optional metadata**.
The action never identifies biology from a label or merges same-named records.
For resequencing an existing biological sample, explicitly correct/confirm its
association; names alone never establish that relationship.

`POST /api/projects/{id}/start-analysis` reuses normal analysis creation and
requires the existing reviewed `input_pairing`/`sample_groups` configuration.
Its stable `request_key` and configuration fingerprint prevent duplicate work
after network retries or restart. Metadata creation is atomic. If registration
fails after QC allocation, the registry transaction rolls back, active QC is
cancelled and the retained analysis ID is reported for inspection; source FASTQs
and pre-existing results are unchanged. A failed registration key cannot silently
create another analysis. No additional required metadata form is introduced.

Batch cohort filters display searchable, paginated **checkbox tables**, with
Select this page / Clear selection, or an explicit All project scope. Empty
explicit selection means no selection and cannot silently select every sample.
Internal UUIDs remain stable but names are the primary display labels.
