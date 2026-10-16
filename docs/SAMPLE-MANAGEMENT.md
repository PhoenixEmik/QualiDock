# Sample and analysis management (Phase 3C)

Samples, pairs and lane/chunk labels are organizational metadata. FastQC continues
to run on individual FASTQ files, and MultiQC aggregates their official reports.
No FASTQ concatenation, lane merging, trimming or derived sample-level QC statistics
are performed. A manual assignment is a user's statement, not biological proof.

## Pair and sample review

Select inputs in Workspace, then open New analysis. Samples & read pairing lets
you confirm automatic pairs, remove a pairing, assign two different unpaired files
as R1/R2, and mark individual files single-end or unpaired. To correct a pair,
remove it and assign its files again. Optional lane/chunk labels belong to the
pair. Missing or ambiguous mates remain analyzable individually.

The same editor lets you confirm detected sample groups, edit display names,
create a group from a chosen file, and move reads between groups. Moving a paired
file moves both mates; unpair first to separate them. Group IDs remain stable when
display names change. Exact file references, provenance (`auto`, `confirmed`,
`manual`) and optional lane/chunk identities are stored in the run manifest.

Detection recognizes common `_S1_L001_R1_001`, `_L001_R1`, `_R1_001`, and `_1`
patterns (and R2 equivalents). Sample-number tokens remain in the internal identity,
so C15_S1 and C15_S2 are distinct suggestions even if their display name is C15.
S1 by itself never defines a biological sample. Grouping keys include the directory;
ambiguous duplicate read names and unmatched naming remain independent. Suggestions
can be confirmed or corrected before running.

Workspace Samples shows expandable lane/chunk groups with independent lane and
read checkboxes; Files remains unchanged. Selecting a whole sample includes its
other directory pages using the existing directory snapshot validation. A run is
still limited to 500 inputs. Identical FASTQ stems in separate directories now use
independent output namespaces; exact report-to-input mappings preserve identity.
Duplicate display names never merge results.

QC Overview displays the saved groups. Select a group to reuse its individual reads
in native comparisons, or inspect a member's FastQC chart. Saved lane/read identities
also appear in shared selection and pair selection. Native comparisons remain
read-level, with no aggregate distributions. Generated MultiQC runs retain their
source run's sample metadata; imports without that provenance do not guess it.

## Configured output locations

`QUALIDOCK_OUTPUT` remains the default persistent store and is created as before.
Administrators may additionally configure existing directories:

```sh
export QUALIDOCK_OUTPUT_ROOTS='["/scratch/user/project-a-qc", "/home/user/project-b-qc"]'
```

These must be absolute, non-nested directories owned by the current Unix user,
writable/searchable and free of symlink components. The default is always included.
New analysis provides an output-location picker, free-space display, Check location,
permission/unavailability feedback and a `<root>/<new analysis ID>` destination
summary. This phase deliberately permits only the configured roots themselves;
it does not create or browse arbitrary project subdirectories. Configure additional
project roots once, then choose between them per run without editing environment
variables for every analysis. Free space is observational; the 1 MiB minimum is not
an estimate or reservation of all space a tool might need.

Every configured store is held under an exclusive Unix lock for the session. All
accessible run manifests are scanned at startup; there is no database or secondary
index to become stale. Duplicate run IDs across stores fail startup. A session
owns its entire configured set, so independent simultaneous sessions need disjoint
store sets. Keep configured roots in subsequent launches to discover their histories.
Unavailable/unwritable roots at startup produce a startup error; runtime changes
are reported by Check location and revalidated when creating/starting a run.

Per-run directories are created exclusively, preventing accidental overwrite.
Root identity and filesystem containment are checked, including symlink escapes;
registered artifact authorization and HTML preview isolation are unchanged.
Existing completed results can still be downloaded if a held store becomes
read-only, while metadata changes and new runs are rejected. If storage disappears
while queued, the live job fails without starting a tool. When persistence is
impossible, the failure is shown in memory and restart marks its saved active state
interrupted. There is no implicit cleanup, deletion or retention policy.

## History

Analyses supports name/ID search, exact state and workflow filters, and creation or
completion date sorting. Missing completion dates sort last. Rename atomically
updates the display name without changing IDs, input files or official artifacts.
Rerun opens the existing setup form with saved mode, thread count (bounded by current
resources), pairing, sample groups and output destination. Inputs and permissions
are checked when restoring and again before execution. Starting always creates a
new run ID. Generating MultiQC or rerunning an existing aggregation uses only its
registered source result directory and does not require source FASTQ data to be
copied or reprocessed.

Analysis details include ID, display name, input references, groups, resources,
tool versions, timestamps, output directory and registered reports. Old manifests
without new fields remain readable without rewriting completed records. Historical
records without saved grouping/pairing metadata retain individual read inspection.

## Additive API / manifest fields

- `POST /api/sample-configuration`: validate selected FASTQ references and return
  current pair/group suggestions; it does not launch tools.
- `GET /api/output-locations`: configured destinations, availability, free bytes.
- `PATCH /api/runs/{id}` with `{ "name": "..." }`: atomic display-name edit.
- `GET /api/runs/{id}/configuration`: validated setup draft for review/rerun.
- Existing `POST /api/runs` accepts optional `input_pairing`, `sample_groups`,
  `output_root`, and `rerun_of`; existing callers can omit all of them.
- Runs add optional `sample_groups`, `sample_input_paths`, `output_root`,
  `output_directory`, `rerun_of`; existing pairing records add optional `source`,
  `assignment`, `lane`, `chunk`, `ambiguous`. Input snapshots add filesystem
  device/inode evidence to the existing size/mtime checks.

Manifests remain version 2 with optional fields. Scientific `metrics.json` and
FastQC/MultiQC output formats and report identities are unchanged. `sample_input_paths`
records original FASTQ references for generated MultiQC metadata mapping, separately
from its QC-report execution inputs. It is derived by the server, not accepted as
an arbitrary request field. All endpoints retain session authentication, CSRF/origin
checks and URL-prefix handling.

## Validation and next steps

Backend management tests cover standard/nonstandard and conflicting pairs, incomplete
and ambiguous reads, multiple lanes/chunks, original-file integrity, permission
changes, output traversal/symlink/collision/space checks, root locks, restart,
rename, rerun, and output loss while queued. Scientific integration uses actual
FastQC 0.13.0 / MultiQC and exact copies of the small genuine FASTQ fixtures with
nonstandard filenames; original report values are compared to the existing parser.
Frontend tests cover immutable editing, reassignment, group/lane selection, filename
ambiguity, history filtering/sorting and genuine FastQC result mapping. Browser
acceptance exercises pair confirmation/correction, project output selection, group
analytics, rename and reviewed rerun alongside the existing chart/report/export and
sandbox regression suite. Screenshot artifacts remain under `validation/`.

Future work can add controlled subdirectory creation with an explicit lock/index
ownership design.
Cross-analysis projects, destructive deletion, preprocessing and scheduler execution
remain outside this phase.

## Per-file execution evidence

New runs add `input_outcomes` (stable path-derived ID, exact input path, planned
ZIP/HTML artifact, recorded state, batch exit code and any error), plus
`report_input_map` for exact report-to-input identity. Unique-name report paths stay
unchanged. Colliding stems use `fastqc/i_<path hash>/` without changing/copying source
FASTQs or rewriting official FastQC files. MultiQC uses its supported `--dirs` /
`--dirs-depth 1` when names collide; native statistics map only verified names.
Imported reports retain report-source provenance and do not assert source integrity.

FastQC runs bounded batches of at most eight inputs per output namespace, under
the existing serial LocalExecutor/resource limits. Within a batch individual file
start/progress is unknown; no running percentage is inferred. Completed means a
ZIP parsed successfully with the correct reported filename. A nonzero batch exit
can coexist with valid completed reports; missing/unparseable inputs have explicit
errors. Earlier completed batches survive cancellation; unfinished states become
cancelled/interrupted, or unknown if an unexpected failure prevents reconciliation.
Saved completed records stay completed on restart; active unfinished records become
interrupted. Historical records without these optional fields show unavailable
execution evidence. QC WARN/FAIL classifications remain independent of execution.
