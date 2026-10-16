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

Schema version 1 initializes installations with no project registry. Existing
v1/v2 analysis manifests and release manifests are not migrated or rewritten.
`PRAGMA user_version` gates future migrations. Unknown/newer versions are refused
without rewriting the database or QC results; do not manually lower the version.
An old QualiDock version can still open unchanged QC manifests, but will not show
project metadata. Preserve the database for a later compatible upgrade.

Metadata edits require the currently displayed `revision`; stale updates return
409. Archive/restore is the supported removal lifecycle (`status`); destructive
DELETE endpoints are intentionally absent. Relationships are append-only in this
initial registry: an attached analysis cannot silently move projects or change
sample assignments. Check the explicit assignment preview before attaching;
correcting a historical association requires a separately audited revision
workflow rather than rewriting the original evidence.

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
Project QC/release readiness initially remains `unknown`; review must drill into
the actual analysis. A saved approval is historical evidence and does not itself
prove present source freshness, successful transfer or biological identity.
Evidence and audit tables reject UPDATE/DELETE. This prevents application-level
rewrites, not a malicious Unix owner editing their own database or source files.

## Authenticated API

All endpoints retain existing session/bearer authentication, CSRF header and
same-origin protections. New endpoints accept stable IDs, never arbitrary file
paths. File assignments reuse the existing authorized analysis inventory and
revalidate source access. Project responses omit filesystem paths; original
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
The Project Workspace UI follows in #21; existing Workspace/Analyses navigation
and standalone analysis creation remain available.

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
