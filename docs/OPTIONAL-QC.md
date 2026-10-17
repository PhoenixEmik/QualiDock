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

## NanoPlot 1.48.0

Set `QUALIDOCK_NANOPLOT` to an existing `NanoPlot` executable, or put it on PATH.
Only the genuinely tested **1.48.0** contract is enabled. The application installs
no packages or browsers. Tool dependencies stay outside QualiDock's runtime
dependencies; CI uses an isolated environment and records installed versions.

Choose **NanoPlot long-read QC** with authorized FASTQ/FASTQ.gz or exact registered
derived datasets. Each file stays an independent observation. Pair/lane metadata
is retained without merging files or applying short-read classifications. The
existing full structure/gzip/SHA validator precedes execution; reported read/base
totals must match before publication. Missing or malformed reports are failures,
and incomplete namespaces are never registered as successful artifacts.

Approved arguments: `--fastq`, `--threads`, `--outdir`, `--tsv_stats`, `--plots dot`,
`--no_static`, `--include-js embedded`, normally `--only-report`. Defaults save
NanoStats, one combined standalone HTML and the upstream log. Advanced controls
add logarithmic length plots or preserve individual interactive HTML files.
Opening reports never reruns QC. The original embedded Plotly report uses the
existing opaque-origin viewer, without CDN allowances or CSP changes. All original
files retain authenticated attachment downloads.

Native tables preserve original NanoStats strings/rounding and compound fields.
`Reads >Q…` percentages count **reads**, not Q20/Q30 bases; Mb fields are rounded
upstream values. Mean read quality comes from NanoPlot/nanomath and is independent
of nanoq's mean and FastQC's per-base values. No statistic is reconstructed.
Ordinary FASTQ has no channel/start-time metadata: activity maps and yield **over
time** are unavailable. Yield **by length** is a different supported upstream
plot. Rich FASTQ, sequencing summaries, alignment/POD5 sources, filters, pickle/raw
dumps and arbitrary CLI options are out of scope.

Input is extracted before plotting. The upstream scatter can select up to 10,000
random read points; plot-point selection has no reproducibility promise. NanoStats
still describes the full input. This does not bound source I/O or initial memory.
The approved profile does not request `--downsample`.

**PNG is explicitly deferred by the confirmed #31 scope decision.** Genuine
1.48.0 static export calls `get_chrome()`; legacy scatter also failed with modern
seaborn (`stat_func`). Both paths stay disabled rather than installing a browser,
patching the scientific tool or offering a broken control. Supported original
visual artifacts are combined/individual interactive HTML. Investigated older
NanoPlot versions are not offered or claimed compatible.

Small actual ONT benchmark input: 20 reads / 26,248 bases / 23,565 gzip bytes.
One local observation measured 4.821 s baseline vs 4.846 s advanced analysis wall
time and 4,727,207 vs 37,377,624 registered report bytes. These include setup/full
validation and are not repeated performance acceptance. SHA-256 matched before
and after. Evidence under `validation/nanoplot/{baseline,advanced}/benchmark.json`
retains scan bytes, stage timings, waited-child CPU and labeled memory/I/O.
Local macOS cannot validate process-tree RSS enforcement; Linux CI supplies its
own observation. No giant-input, NFS/Lustre or 11 GB summary acceptance is claimed;
#5 stays open. PNG is the only intentionally deferred output format for #31.

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

Initial aligner support is Bowtie2 2.4–2.x (genuine tests: **2.5.4** locally,
**2.5.2** in Linux CI); no arbitrary
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
Reports use unique, stable input-ID filenames. Genuine MultiQC 1.25.1 file-list
testing showed that `--dirs` did not preserve namespaces for identical basenames;
unique filenames prevent silent replacement independently of that older behavior.
Both original report values and verified source mappings must survive aggregation.

## Implementation and acceptance record

- #29 nanoq: completed. [Acceptance CI](https://github.com/PhoenixEmik/QualiDock/actions/runs/38981897664)
  passed all eight jobs on implementation commit `76c749b`.
- #28 FastQ Screen: completed. [Acceptance CI](https://github.com/PhoenixEmik/QualiDock/actions/runs/38984777060)
  passed all eight jobs on collision-fix commit `d73cdcc`.
- #30 Falco: evaluated separately; no application engine was added. See the
  [measured correctness/performance gate](FALCO-EVALUATION.md).

The complete local backend suite with all genuine tools and the million-read
evaluation input passed **399 tests** in 379.99 seconds, with no skips. Frontend
tests passed **142 tests**, and TypeScript/Vite built successfully. The existing
large ECharts bundle warning remains. Actual local versions were FastQC 0.13.0,
MultiQC 1.35 (plus a separate genuine 1.25.1 collision regression), nanoq 0.10.0,
FastQ Screen 0.16.0, Bowtie2 2.5.4, fastp 1.4.0 and SeqKit 2.14.0.

Linux genuine-tool CI independently runs MultiQC 1.25.1, 1.35 and latest 1.x;
processing regressions use fastp 0.23.4 and SeqKit 2.14.0, screening uses
Bowtie2 2.5.2. The dependency-light
backend job intentionally skips unavailable tool cases; dedicated required-tool
jobs run them with actual installations. They do not substitute mocked scientific
success. Linux resource/cgroup, cancellation, secure artifacts, report isolation,
restart, derived reuse and original FastQC/MultiQC regressions remain enabled.

Browser evidence on `d73cdcc` contains **57 Chromium** and **33 Firefox** cases,
zero failures/errors/skips. This includes six new optional-QC cases per browser:
nanoq and FastQ Screen at `/`, `/node/compute/8765`, and `/rnode/compute/8765`.
Real execution, restored results, original JSON/HTML, interactive Screen Plotly,
MultiQC identity, mobile horizontal scrolling and keyboard access are exercised.
Screenshots were visually reviewed; they are not a pixel-equivalence claim.
Downloaded evidence is under ignored `validation/qc-ecosystem/{chromium,firefox}`;
the reproducible upstream artifacts are `report-browser-chromium` and
`report-browser-firefox` on the acceptance CI run.

### Scope of code changes

Relative to pre-integration commit `58d477e`, application production code
(`backend/qualidock` and `frontend/src`) adds **934** lines and removes **140**
(net **+794**), including formatting. There are no new runtime dependencies,
database, execution engine, top-level pages or deleted production files.
Developer benchmark/provisioning scripts add another 179 lines, counted
separately from the application. Tests, fixtures, documentation and CI are not
included in those application production totals.

Added application files: `backend/qualidock/optional_qc.py` (shared optional
report-only QC lifecycle/JSON adapter), `backend/qualidock/fastq_screen.py`
(approved references, real aligner evidence and original summary adapter),
`frontend/src/OptionalQcResults.tsx` (small native tables and provenance).

Modified backend files: `app.py`, `config.py`, `history.py`, `import_formats.py`,
`integrity.py`, `manager.py`, `multiqc.py`, `processing.py`, `tools.py`.
Modified frontend files: `AnalysisDetail.tsx`, `App.tsx`, `NewAnalysisForm.tsx`,
`ResultsList.tsx`, `api.ts`, `types.ts`. The existing scientific charts and report
sandbox are reused unchanged.

Added tests are `test_optional_qc.py`, `test_nanoq_real.py`, `test_screen.py`,
`test_screen_real.py`, `test_falco_evaluation.py`, genuine optional-QC fixtures,
and `tests/browser/test_optional_qc_browser.py`. Test-only provisioning uses
`scripts/setup-optional-qc-ci.sh` and `scripts/prepare-screen-test.py`.
The existing benchmark script and CI are extended, with README, this document,
`BENCHMARKING.md` and `FALCO-EVALUATION.md` recording supported behavior.

API additions are optional `nanoq`/`fastq-screen` modes, `qc_options` for approved
screening settings and corresponding `/api/config` tool/panel availability.
Manifests add optional `qc` metadata with per-file results/provenance. Existing
manifest fields, report IDs, API modes and derived-input authorization remain
compatible; historical analyses need no migration. There is deliberately no
`falco` application mode. No release was tagged or published.
