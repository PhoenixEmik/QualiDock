# Optional QC tools

Optional tools use the same RunManager, LocalExecutor, queue, Unix user, CPU/memory
limits, cancellation, owned output directories, authenticated downloads and
restart recovery as the default FastQC workflow. QualiDock never installs tools.
FastQC remains the default. These integrations do not create processed FASTQs.

## nanoq 0.10.0

Set `QUALIDOCK_NANOQ` to an executable path, or provide `nanoq` on PATH. Version
detection deliberately accepts the verified **0.10.0** contract only. Select
FASTQ/FASTQ.gz files in Workspace, configure **nanoq long-read QC** in Quality
Control, then inspect the saved **QC metrics** and **Reports** tabs. Each file is
evaluated independently; mate counts are not combined into biological samples.
Registered derived inputs use the existing exact dataset authorities.

The command is `nanoq --stats --json --report <owned.json> --input <input>`.
`--stats` suppresses read output; no filters, trimming, `--fast`, stdout FASTQ or
length/quality per-read dumps are requested. Input FASTQs first pass the existing
full streaming validator in a resource-governed, cancellable subprocess. Count,
base and min/max-length totals must match the actual JSON before registration.
Original JSON is retained byte-for-byte; malformed, empty, missing or inconsistent
reports fail. Completed files survive failures of other inputs as partial results.
Unfinished QC namespaces and private validation files are not artifacts.

The native table preserves reported numbers, including nanoq's integer mean
length. N50 is taken directly from nanoq, never recalculated. Threshold counts use
**strict `>`** in upstream 0.10.0, despite an inconsistent source comment saying
`>=`. Mean read quality is based on each read's mean error probability, converted
to Phred, then summarized across reads. nanoq uses Phred+33; this is a tool
convention, not independent encoding detection. These are not FastQC's per-base
mean values or Q20/Q30 **base** percentages. ONT protocol and basecalling affect
quality; no short-read PASS/WARN/FAIL rules or biological interpretations are added.

MultiQC 1.35's nanoq module reads verbose **text** reports, not this JSON schema.
This adapter therefore does not offer aggregation or manufacture a text report.
Original JSON remains downloadable. Existing FastQC/fastp MultiQC is unchanged.

nanoq 0.10.0 retains read length/quality vectors, so memory scales with read count;
it is not a constant-memory algorithm. Existing process-tree limits apply. One
additional full input-validation scan supplies structure, gzip CRC and SHA-256
evidence. Snapshot rechecks detect ordinary changes; they are not a claim that
file size/mtime alone proves immutable content. No large/shared-storage throughput
or peak-memory acceptance is inferred from the small fixtures.

Validation includes genuine upstream ONT records and untouched nanoq output,
plain/gzip, original numerical fidelity, missing dependencies, malformed/oversized
JSON, invalid inputs, collision isolation, partial outcomes, validation cancellation,
downloads, derived authorization and restart. CI provisions only test tools and
exercises actual setup/results/restart interactions in Chromium and Firefox.

## FastQ Screen 0.16.x (tested 0.16.0)

Optional operator configuration:

```sh
export QUALIDOCK_FASTQ_SCREEN=/absolute/path/to/fastq_screen
export QUALIDOCK_BOWTIE2=/absolute/path/to/bowtie2
export QUALIDOCK_SCREEN_PANELS='{"standard":"/absolute/path/to/panel.conf"}'
```

Select **FastQ Screen** in the existing QC form and choose an approved panel.
The form exposes no arbitrary config path or aligner flags. Each panel is a small
operator-supplied UTF-8 configuration, for example:

```text
DATABASE human /references/human/index
DATABASE mouse /references/mouse/index
```

The application accepts only `DATABASE <name> <absolute-prefix>`, an optional
`BOWTIE2 <executable>` matching the configured executable, and `THREADS` (overridden
by allocation). Comment-only lines are allowed. Do not include arbitrary tool
directives or trailing inline annotations. Names must be ASCII letters followed
by letters/digits/`_.-`; 1–16 unique references are supported. The config must be
owned by the current user/root, not group/world writable, at most 64 KiB, with no
symlink components. All six `.bt2` or `.bt2l` files must be regular/readable at the
declared prefix. Missing or invalid optional panels appear unavailable without
preventing FastQC/nanoq/processing. QualiDock never downloads or builds references.
`scripts/prepare-screen-test.py` explicitly builds **test-only** synthetic indexes;
it is never called by the application.

Initial aligner support is Bowtie2 2.4–2.x (genuine tests: **2.5.4**); no arbitrary
aligner options, bisulfite mode or alternative aligners are exposed. FastQ Screen
0.16.0 removed actual paired alignment: **R1/R2 files are separate SE observations**.
Metadata can retain pair/lane identities, but this operation neither asserts nor
validates mate synchronization. Reordered/mismatched mates are not treated as a
paired dataset, and `paired` options are rejected. Processing's strict paired-end
checks remain unchanged. Only four-line FASTQ records are supported by this
upstream tool; the existing scanner explicitly rejects wrapped records for this
operation alone. Phred+33 is the upstream alignment convention, not detected
quality encoding.

Default `--subset 100000` is upstream's approximate **systematic** subsampling,
not exact or uniformly random selection. Upstream can process up to **twice** the
requested target when the input is small/near the target. Actual screened counts
are preserved and checked against full input counts and this bound; these are not
whole-library abundance estimates. The source validation and upstream counting
still scan the input, so bounded mapping does not imply bounded source I/O.

FastQ Screen internally builds shell commands and can ignore aligner failures.
QualiDock therefore uses authorized input symlinks with generated safe names,
rebuilds the approved minimal config, validates execution/index/output paths, and
uses a tiny run-owned launcher to record each genuine Bowtie2 exit code. The
launcher is a child in the same process group/resource limits, not another job
manager. No exit-zero summary is accepted if any reference alignment failed.
For this integration only, output/index/executable paths must contain letters,
digits, `/`, `_`, `.`, `-` only. Input filenames can contain spaces, quotes or
shell characters because only safe aliases reach upstream commands. This is a
deliberate compatibility restriction instead of weakening command safety.

Results preserve original `_screen.txt`, `_screen.html`, and `_screen.png` when
the optional upstream GD::Graph package is installed. HTML contains an embedded
interactive Plotly graph and uses the unchanged opaque-origin report sandbox.
Original files stay downloadable; no filtered/tagged/no-hit FASTQs are published.
Temporary upstream subsets can remain unregistered after cancellation.

Native tables display original reference categories and exact reported percentages.
Multiple/no-hit observations depend on the chosen panel, sampling and mapping
preset (`--very-fast-local -k 2` in upstream 0.16.0); they are **not definitive
contamination diagnoses**. Provenance records config SHA-256, selected references,
index filesystem snapshots, actual tool versions, command arguments, subprocess
exit codes and validated source SHA-256. Index snapshots are **not independent
reference-content checksums**; operators remain responsible for reference identity.
Panel/index snapshots are rechecked before and after each file.

Optional MultiQC uses the existing shared aggregation helper and unique file
namespaces. The FastQ Screen module supplies its own plot/raw data and source map,
**not General Statistics**. QualiDock verifies its actual module sample identities
without manufacturing General Statistics columns. Unsupported schemas or missing
source mappings remain explicit partial-report failures; successful original QC
results are retained. No alternative native MultiQC plot renderer is introduced.
The workflow explicitly enables `preserve_module_raw_data`, required to retain
these original module values in the MultiQC 1.25.1 structured JSON (its default
is false). This changes data export retention, not mapping or QC calculations.
