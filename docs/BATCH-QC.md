# Project batch QC and validation

Use **Workspace → Projects → project → Batch QC**. Select all active project
identities, or search/browse checkbox tables for samples and sequencing runs.
Selections combine as an intersection. Select this page adds up to 25 rows;
selection is retained across search/pages (100 IDs per filter). Clear selection
is empty, not an implicit request to process the entire project.

Preview before queueing. The preview shows every eligible FASTQ reference, its
sample/run/lane/chunk/read metadata, actual detected tool versions, threads,
output root, integrity coverage, expected outputs and reuse/rerun reasons.
Incomplete or ambiguous declared pairs stay unpaired, with a visible warning.
Conflicting identities for the same physical source are skipped and require
explicit resolution; labels never disambiguate biology. Archived/unavailable
references are skipped. Missing project file associations require resolution in
Analyses & evidence or the browse-first intake workflow.

A unit is one declared sequencing run, split at 500 inputs. A plan is bounded to
2000 distinct files / 20 units / 5000 original source associations. A pair split
by a unit boundary remains explicitly unpaired rather than being assumed valid.
The split never concatenates files or aggregates quality distributions.

Source bytes are the sum of current compressed/source file sizes, **not** a
runtime or exact I/O estimate. FastQC and full integrity read sources separately;
FastQC internal read behavior is not modeled. Integrity uses the existing bounded
streaming worker. No original FASTQ is copied, modified or loaded into memory.

## Reuse and provenance

Only a complete matching analysis scope is reusable. Its terminal success,
analysis mode, threads, actual tool versions, exact source size/mtime/device/inode
snapshots, pair relationships, native metrics content digest and registered
FastQC HTML/ZIP (plus MultiQC HTML when requested) must all match. Unknown versions,
missing artifacts, partial QC and stale inputs do not qualify. A subset of an
analysis explicitly receives a new QC analysis; it is never cloned into a
parallel scientific result format. The source-stat fingerprint follows existing
input freshness semantics; preview does not rehash entire source datasets.

A full/quick integrity result can be reused only when its mode/validator version,
full current per-file coverage and paired source relationships match. Exact Q20
and Q30 values remain those reported by the existing full validator with a known
FastQC encoding. A quick scan that reaches its limit is not full coverage.

Immutable plans and append-only transition events live in the existing private
project registry (schema v3); JSON QC/release manifests and artifacts remain the
scientific source of truth. New child analyses carry optional `batch_origin`
metadata. Their generated duplicate links do not invalidate the original plan;
manual association corrections remain visible to freshness checks. Completed
children are linked with their actual report identities. Existing analyses and
release records need no migration.

## Execution, cancellation and restart

At most five batch coordinators may be active. Each owns at most one QC/validation
child at a time. Existing RunManager/ValidationJobs and their global resource slot
continue to bound processes, CPU, memory and tool concurrency, including manual
analyses. No scheduler adapter or separate execution engine is introduced.

A stable idempotency key returns the same attempt after a lost network response.
Duplicate active fingerprints (including separately previewed equivalent plans)
are rejected. Re-submission of an already-used plan requires an explicit terminal
attempt ID as `retry_of`, with a new key. Retry revalidates the original cohort and
can resume matching completed owned children; cancelled/interrupted/failed child
results are retained and new QC gets a new ID. A changed cohort/source/tool/resource
allocation requires a fresh preview. No existing result is overwritten.

Per-stage statuses are pending/running/completed/failed/skipped/not evaluated;
per-file QC statuses come directly from existing input outcomes, including unknown
coverage. Integrity progress is the actual worker's current file/records, not a
simulated percentage. QC failures do not erase successful other units or official
artifacts. Missing optional demultiplex evidence is not evaluated, not passed.
Yield inspection uses existing exact counts and **analysis-local explicit targets**;
unscoped project expected-yield declarations are never silently applied across
lanes/runs. Below-target results remain visible. No stage approves a release.

Cancel stops only QC children created by this attempt and the exact integrity task
IDs it started. A concurrent manually requested validation/export is not replaced
or cancelled. Cancellation during child allocation is checked again after the
coordinator stops. Historical completed stages remain inspectable. On restart,
active attempts and unfinished stages become interrupted/not evaluated; no job
is silently restarted. Explicitly review and retry. Ownership uses the existing
exclusive store lock, so another application instance cannot modify the same
registry/results.

## API and validation

All operations use existing session/bearer, CSRF, path containment and configured
output-root protections. No API accepts shell fragments or arbitrary output paths.

- `POST /api/projects/{id}/batches/preview`: optional stable `sample_ids`,
  `sequencing_run_ids`, and `options` (`mode`, `threads`, `integrity`, `reuse`,
  `yield`, `demultiplex`, `output_root`). Omitted/null filters mean the entire
  active project; empty explicit arrays are rejected.
- `POST /api/projects/{id}/batches`: `plan_id`, `idempotency_key`, optional `retry_of`.
- `GET /api/projects/{id}/batches?offset=0&limit=25` (maximum 100).
- `GET /api/projects/{id}/batches/{attempt_id}`.
- `GET /api/projects/{id}/batch-plans/{plan_id}`.
- `POST /api/projects/{id}/batches/{attempt_id}/cancel`.

Automated coverage includes genuine small FastQC/MultiQC outputs and full streaming
validation across two declared runs; source/manifest preservation; exact reuse;
subsets and incompatible pairing; stale metadata/source/tool/options; partial
failures; idempotent requests; cancellation during allocation; five-batch bounds;
100 explicitly synthetic file records; restart; existing analyses/report previews;
and browse/checkbox/mobile browser interactions. Local resource tests and Linux
cgroup validation do not constitute a large-data NFS/Lustre benchmark. Deploy the
registry only on filesystems with reliable locking; actual shared-storage I/O
validation remains the separate benchmark gate documented in issue #5.
