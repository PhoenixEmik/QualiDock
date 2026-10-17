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
Runtime detection reads Python distribution metadata in the console entrypoint's
own interpreter, without importing NanoPlot: some older versions install Chrome
during CLI import, even for `--version`. A standard pip/conda Python console script
in an isolated virtualenv/Conda environment is required (user-site/PYTHONPATH-only
installs are not exposed by the isolated metadata probe); shell/binary wrappers and nonstandard launchers are unavailable with
an explicit diagnostic. Load the environment first and configure its direct
`NanoPlot` entrypoint. Scientific input paths with spaces remain supported. The
recorded tool information includes this version-source distinction; genuine CLI
version/execution is separately verified by the provisioned regression tests.

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
#5 stays open. Existing FASTQ validation bounds (1 MiB per line, 4 MiB per
record) also apply; this is not a claim of unrestricted ultra-long read support.
PNG is the only intentionally deferred output format for #31.

Linux hosted-runner observations on the same input: 2.718 s baseline / 3.117 s
advanced analysis wall time; actual NanoPlot stage 1.225 / 1.427 s, source
validation 0.226 / 0.225 s. Highest sampled process-tree RSS was 231,268,352 /
268,709,888 bytes (three samples, 0.5 s interval), **not exact peak memory**.
Waited-child CPU was 4.037 / 3.990 s including probes/guardians, not pure tool
CPU. The source SHA-256 was unchanged. Evidence and dependency versions are in
`nanoplot-real-evidence` on [CI 38997343347](https://github.com/PhoenixEmik/QualiDock/actions/runs/38997343347).

Implementation inventory relative to `fe0e57d`: 6 files added, 20 modified,
none deleted. Application code adds 357 lines/removes 47 (net +310, including
formatting). Added `nanoplot.py` is an 81-line explicit adapter; modified existing
QC lifecycle/config/API/history and setup/results/types/report-selection files
reuse the same manager, validator and viewer. Genuine NanoStats and its provenance
README, 23 unit cases, 13 real-tool cases, one frontend report-order regression
and browser cases are added. Benchmark, test provisioning, CI and the existing
guides are extended. No runtime dependency, executor, database or chart framework
is introduced. Manifests add optional `qc.results[].nanoplot` raw rows/HTML paths;
old analysis fields/formats remain unchanged. Final full local backend: **435 passed**
without skips; 36 focused NanoPlot checks also passed after version/completeness
hardening. Frontend: **143 passed** and TypeScript/Vite build passed.
[Final acceptance CI 38998848956](https://github.com/PhoenixEmik/QualiDock/actions/runs/38998848956)
on implementation commit `313dad6` passed all eight jobs, including genuine tools,
MultiQC 1.25.1/1.35/latest-1.x and Linux resources. Browser artifacts contain
**60 Chromium / 36 Firefox** cases, zero failures/errors/skips. Screenshots of
native NanoStats and original interactive reports were visually reviewed;
this is not a pixel-equivalence claim. Reproducible evidence is in the run's
`nanoplot-real-evidence` and `report-browser-*` artifacts; downloaded copies are
under ignored `validation/nanoplot-final-{linux,browser}`. #31 is accepted with
its explicitly confirmed HTML-only output scope; no release is prepared.

## SAMtools 1.22.1 — read-only alignment QC

Set `QUALIDOCK_SAMTOOLS` or provide `samtools` on PATH. The initial explicit
contract requires **SAMtools 1.22.1 with HTSlib 1.22.1**; older, prerelease and
unqualified builds are unavailable without affecting FASTQ tools. No application
runtime dependency is added. Test provisioning builds the original pinned source.

BAM/CRAM appear as independently selectable alignment inputs in Workspace. Select
an alignment and choose **SAMtools alignment QC** in the existing Quality Control
form. FASTQ pairing, structural validation, integrity scans, derived FASTQ
registration and sample grouping are deliberately separate. Mixed FASTQ inputs
are excluded by the form and rejected by the alignment API. No BAM conversion,
sorting, indexing, editing or derived alignment output is implemented.

Each file executes original `samtools head -n 0` (metadata only), `quickcheck -v`,
`flagstat` and `stats`. Thread arguments request **threads minus one** additional
decoder threads. All commands share the existing executor/resource slot and
cancellation. stdout goes directly to original owned report files; stderr remains
in the analysis log. Report-writing subprocesses have a **128 MiB per-file OS
limit**, not a run-wide storage quota. Parsed headers/FAI are at most 16 MiB /
100,000 references; flagstat is at most 64 KiB; stats is streamed, with at most
200 native summary rows and 1 MiB per line. Full original stats remains available.
Incomplete or failed per-file namespaces are not registered as QC artifacts.
Successful files remain accessible if another file fails.

**quickcheck means header/EOF sanity only.** A deliberately internally corrupted
BAM passes quickcheck but fails the subsequent scan regression. Neither this label
nor filesystem snapshots claim exhaustive alignment integrity or content hashes.
Source paths, size/mtime/device/inode, format, dictionary, flags, versions,
command/exit/timestamps and reference evidence remain in the manifest. Independent
tests hash inputs, existing indexes and references before/after to verify unchanged
bytes. Opening results or rerunning configuration never executes a conversion.

Native flagstat rows preserve original QC-passed/QC-failed segment counts and
printed percentage labels, including `N/A`. Categories overlap. Total segments
include primary/secondary/supplementary alignments and are **not independent read
pairs**. Mapped percentages use each QC column's total segments; primary-mapped
uses primary segments; properly-paired/singleton uses paired-in-sequencing
segments. Original stats SN values/precision/notes are preserved separately;
`raw total sequences` excludes secondary/supplementary. No Q20/Q30 base metric
or overall biological quality classification is inferred. See the official
[flagstat](https://www.htslib.org/doc/samtools-flagstat.html),
[stats](https://www.htslib.org/doc/samtools-stats.html) and
[quickcheck](https://www.htslib.org/doc/samtools-quickcheck.html) definitions.

For CRAM, configure only approved existing **uncompressed** local references:

```sh
export QUALIDOCK_ALIGNMENT_REFERENCES='{"assembly":"/references/assembly.fa"}'
```

The FASTA and its existing `.fai` must be readable regular files without symlink
components, owned by this user/root and not group/world writable. No FASTA/index
is generated, downloaded or copied. Every alignment dictionary sequence must
exist with matching length in the selected FAI before record decoding. Explicit
`--input-fmt-option reference=<local FASTA>` is passed to both record scanners;
reference MD5 checks remain enabled. Environment overrides `REF_PATH=/dev/null`,
`REF_CACHE=/dev/null` and `HTS_PATH=` disable inherited reference search/cache and
external plugins. Complete local dictionary coverage prevents missing-contig UR
fallback; pinned HTSlib additionally rejects remote UR references. Reference
snapshots and FAI SHA-256 are recorded/rechecked before/after execution; they are
not a full FASTA checksum. Mismatched reference bases fail genuine decoding.
Missing reference/index/contigs fail clearly. CRAM with embedded references still
requires the same explicit approved contract in this initial integration.

Optional **Generate MultiQC** uses the existing aggregation helper. Genuine stats
and flagstat reports use stable input-ID filenames, avoiding basename collisions;
source mappings are accepted only from the verified Samtools stats/flagstat
sections. Original reports remain available if aggregation/mapping fails. This
is separate from importing arbitrary external SAMtools directories; that new
import workflow is not offered. MultiQC original HTML uses the unchanged isolated
viewer. Genuine MultiQC **1.25.1** crashes in its flagstat module when reported
percentages are `N/A` (`None / total`). That version therefore aggregates the
original **stats only**, with an explicit run warning and no false flagstat source
mapping. Original flagstat remains natively viewable/downloadable, unchanged;
no missing value is converted to zero. MultiQC **1.35** supports both sections.
Version-matrix acceptance is recorded after required CI finishes.

Small synthetic SAM/reference fixtures explicitly define 8 alignment records
(primary 6, secondary 1, supplementary 1) and original SAMtools outputs. Tests
verify actual report values, plain BAM and CRAM, corruption/truncation, wrong
reference, source immutability, collision mapping, secure artifacts, cancellation
and restart. A live HTTP canary test runs unchanged in Linux genuine-tool CI;
the local managed macOS sandbox cannot bind a listening port. No representative
large-alignment or NFS/Lustre performance acceptance is claimed. No release work
is included. #33 may build on this validated input contract.

SAMtools implementation inventory relative to `adb0888`: 12 added files,
25 modified, none deleted. Application production code adds **675** lines and
removes **97** (net **+578**, including formatting). New production files are
`backend/qualidock/alignment.py` (253 lines) and
`frontend/src/AlignmentResults.tsx`; existing config/file kinds/QC lifecycle,
executor stdout handling, validation guard, analysis setup/history/types and
artifact links are extended. Tests add the genuine synthetic SAM/FASTA and
original reports, explicit test-only conversion/provisioning scripts, 31 backend
cases and browser setup/results/restart coverage. No new runtime dependency,
database, executor, plugin interface or manifest migration is introduced. API
additions are optional `samtools` mode, approved-reference/QC options and config
listing; manifest `qc` rows add optional `alignment` reports/tables and reference
evidence. Existing saved analyses remain readable.

Final local backend on `7024dc2`: **465 passed**, one HTTP-canary case deliberately
not selected because this managed macOS sandbox cannot bind listening ports.
That unchanged case passes in Linux genuine-tool CI, with curl-enabled upstream
HTSlib. All **31 SAMtools tests pass** in the dedicated MultiQC 1.25.1/1.35/latest
matrix; 1.25.1's explicit stats-only contract is covered, not skipped. Frontend
**144 passed**, TypeScript/Vite build passed (existing ECharts chunk warning).
[Acceptance CI 39001443076](https://github.com/PhoenixEmik/QualiDock/actions/runs/39001443076)
on implementation commit `7024dc2` passed **all eight jobs**. Browser artifacts
contain **63 Chromium / 39 Firefox** cases, zero failures/errors/skips, including
actual BAM/CRAM setup, missing-reference blocking, downloads with live terminal
updates, prefixed paths, narrow layouts and restored results. Both browsers'
screenshots were visually reviewed. Narrow tables retain keyboard-accessible
horizontal scrolling; no pixel-equivalence claim is made. Source immutability,
reference identity and numerical equivalence are tested independently of visuals.
Artifacts are `report-browser-*`, with downloaded copies under ignored
`validation/alignment-final-browser`. #32 is accepted; no release was prepared.

One hosted-Linux observation on the explicit 8-record fixture: BAM+MultiQC wall
**2.363 s**, CRAM+MultiQC **2.353 s**; each SAMtools command took 0.224–0.229 s
including the existing worker/guardian. Single process-group RSS observations
were approximately 10.4–10.6 MB (one sample per command), **not exact peak memory
or pure SAMtools RSS**. No tool CPU or physical filesystem-throughput claim is
inferred from these timings. Original evidence/tool compilation features are in
`alignment-1.35-evidence` on CI run `39001443076`; local downloaded evidence is
under ignored `validation/alignment-final-linux`. Large alignment/shared-storage
acceptance remains unmeasured.

## mosdepth 0.3.14 — coverage QC

Set `QUALIDOCK_MOSDEPTH` or provide `mosdepth` on PATH. The initial verified CLI
contract is **0.3.14**, with the existing **SAMtools/HTSlib 1.22.1** preflight.
Select BAM/CRAM and choose **mosdepth coverage QC** in the existing QC form.
It uses the same alignment authorization, resource slot, executor, stdout limits,
cancellation, per-file/partial results, JSON persistence and artifact protection.
FASTQ pairing, processing and derived datasets remain separate. No new runtime
package, tool installation, executor or database is introduced.

Inputs must be coordinate sorted, with an existing matching BAI/CSI or CRAI.
SAMtools metadata/EOF checks and a full stats scan verify actual sort order
(`is sorted`) and CRAM decoding, not just the `SO:coordinate` header. This adds
one full input scan before mosdepth's indexed queries. CRAM uses the same approved
local FASTA/FAI policy above; no implicit remote reference search/cache, source
conversion, sorting or index building is performed. Reference checks remain
independent of coverage: mosdepth can avoid sequence decoding, so coverage alone
would not validate the reference bases.

Indexes are selected deterministically (CSI before BAI; full source suffix before
basename alternatives), authorized under input roots, and explicitly supplied
using upstream `source##idx##index` syntax. User paths containing the reserved
delimiter are rejected. Index format prefixes and upstream decoding are checked;
index/source snapshots are rechecked after execution. These snapshots **do not
cryptographically bind an arbitrary valid/stale index to a BAM**. Operators must
provide a matching index; no size/mtime-only immutability proof is claimed.
Sources and existing indexes are independently hashed before/after genuine tests.

The command always requests `--no-per-base`, explicit `--flag` and `--mapq`, and
`--threads <allocated threads minus one>` decoder threads. Default mask **1796**
excludes unmapped, secondary, QC-failed and duplicate records. An optional control
also excludes supplementary alignments (mask **3844**). Default CIGAR and mate
**overlap correction** remain enabled; fast/fragment modes are not offered.
MAPQ is an aligner-specific alignment score, not base quality; 255 can mean
unavailable. Source files remain unchanged; no FASTQs or alignment outputs are
published. `MOSDEPTH_PRECISION=5` is explicit and recorded; reported decimal
strings remain unchanged in tables/tooltips. No Phred quality bands are used.

### Coverage scope and denominators

**Genuine 0.3.14 behavior:** contigs with no alignment records can be omitted from
summary and global CDF totals. In the explicit eight-record fixture, the header
has 150 reference positions, but the tool reports 100 positions / depth sum 25 /
mean 0.25000. Its CDF fraction at ≥1× is 0.25000. QualiDock shows that reported
100-position denominator and lists the unreported 50-position chr2; it does not
replace the denominator with 150 or invent a whole-assembly fraction. Unreported
references are unavailable, not filled with zero. This limitation is prominent
in the native results and tested independently of chart rendering.

`summary.bases` is the **sum of aligned depths**, with the chosen filters and mate
correction; it is not total sequenced FASTQ bases. Means/min/max and original
precision come from mosdepth. Zero-length aggregate mean/min/max are unavailable
for scientific interpretation even when the original report uses zero sentinels.
The native global chart plots only actual reported `total` CDF points: fraction
of reported reference positions covered at **at least** each depth. It neither
fills missing tail depths nor normalizes to a different reference population.
Original per-reference distributions remain downloadable. Changing views does
not run tools again.

### Approved BED targets

```sh
export QUALIDOCK_COVERAGE_PANELS='{"targets":"/references/targets.bed"}'
```

Initial panels are administrator-owned local **uncompressed** BED files, no
symlink components or group/world writes, at most 2 MiB and 10,000 intervals.
Only consistently three/four-column, nonempty, ordered, **nonoverlapping within
each reference** intervals are accepted; no merging or clipping is performed.
Optional names are preserved literally. Each contig/end must match the selected
alignment dictionary; out-of-bounds/unknown targets fail before mosdepth.
Panel SHA-256/snapshots and exact rows are persisted/revalidated. No upload,
reference download, automatic interval generation or reference manager is added.

BED execution always requests original threshold counts at **1×, 10×, 20×, 30×**.
A threshold row counts positions in its original `[start,end)` interval, with
**end minus start** as denominator; counts are not global percentages. Global
and regional CDFs are distinct original files. Empty contigs can still produce
zero-valued individual intervals while being absent from the regional aggregate:
the fixture requests 40 BED positions, but mosdepth's regional denominator is 30.
Both are displayed. QualiDock does not recompute a combined region statistic.
If only unreported contigs are targeted, the regional aggregate can have length
zero and an empty regional CDF, while actual per-region zero counts remain valid.

### Native view and original reports

The existing ECharts `NativePlot` supplies a compact global CDF, exact raw-value
tooltips, zoom/reset, series visibility and PNG/SVG export. Existing application
navigation is unchanged. A single alignment selector avoids rendering hundreds of
charts by default. Summary/regions/thresholds/raw CDF are original-data tables,
with source paths, filter mask, MAPQ and index provenance. Missing values are not
changed into zeros. Summary and regional tables display at most 200 rows; original
files retain every row. CDFs above 20,000 `total` points are downloadable without a
native chart rather than silently resampled. Parsing is bounded to 4 KiB per line
and 64 MiB decoded per report; normal report subprocesses retain the shared
128 MiB per-file writing limit. Reserved `total`/`_region` naming collisions fail
explicitly. Oversized/ambiguous/malformed reports are not successful native QC.

Original summary, global/regional distributions, region/threshold BED.gz files,
owned regional **report** CSI indexes and preflight/execution logs are registered
only after successful validation. Source alignment indexes are never created or
modified. Gzip/CSI download permission is limited to explicitly known completed
coverage artifacts; arbitrary gzip files do not become artifacts. Downloads stay
authenticated attachments. mosdepth does not create HTML reports, and no synthetic
HTML is generated. Native MultiQC aggregation for mosdepth is not exposed in this
initial contract; existing integrations and official viewer remain unchanged.

Validation uses genuine mosdepth output and independently specified SAM intervals,
including mate overlap, filtering, zero coverage and omitted contigs. Local
source build: upstream 0.3.14, Nim 2.2.12 with `--mm:refc`, hts-nim 0.3.31 and
HTSlib 1.22.1, no tool source patch. Linux CI separately tests the official static
release with its published SHA-256. No representative large-BAM, peak-memory or
NFS/Lustre acceptance is inferred from the eight-record fixture. Upstream's
chromosome-sized depth arrays remain governed by existing process-tree/cgroup
limits; regional selection is not a promise of bounded input I/O or small RAM.
The existing `benchmark-analysis.py --mode mosdepth` records the actual app
workflow rather than introducing another benchmark system. One local observation
on a 531-byte / eight-record BAM + approved BED reported 2.330 s app analysis wall,
0.283 s full-stats preflight and 0.275 s mosdepth stage (including guardian
startup), 32,895 registered report bytes, and unchanged source SHA-256. Waited-child
CPU was 1.110 s, including probes/guardians, not pure mosdepth CPU. These small,
warmed/uncontrolled-cache observations are not performance acceptance. Portable
process-tree RSS and kernel filesystem I/O are unavailable; original scope labels
are retained. Linux CI records its separate evidence.

Linux hosted-runner observation on the same eight-record fixture (507-byte BAM):
2.335 s application analysis wall, 0.230 s full-stats scan and 0.231 s mosdepth
stage, 31,993 registered report bytes, source SHA-256 unchanged. These timings
include process guardians. Waited-child CPU was 2.202 s including probes/guardians.
The mosdepth execution had one process-tree RSS sample of 10,579,968 bytes at a
0.5 s interval: **not tool-only or exact peak memory**. Kernel per-process I/O
observations are retained without summing overlapping counters into a throughput
claim. Evidence is in `mosdepth-real-evidence` on CI 39005371025; local downloaded
copies are under ignored `validation/coverage-final-linux`.

Implementation inventory relative to accepted SAMtools commit `71f5287`:
16 files added, 22 modified, none deleted. Application code (`backend/qualidock`,
`frontend/src`) adds **844** lines/removes **120** (net **+724**, including
formatting). Added application files are `coverage.py` (248 lines),
`CoverageResults.tsx` (215 lines) and `coverageChart.ts` (63 lines). Existing
alignment lifecycle, input authorization, configuration, manager/artifact handling,
history, QC setup/results, API helpers and optional frontend types are extended;
there is no separate execution loop. Added tests are `test_coverage.py`,
`test_coverage_real.py`, genuine mosdepth report fixtures, `coverage.test.ts` and
`test_coverage_browser.py`. Existing benchmark, test-tool provisioning, CI,
README and optional-QC/benchmark documentation are updated.

API additions: optional `mosdepth` mode, bounded `qc_options`, and approved-panel
availability in `/api/config`. Manifests add optional `qc.bed_panel` and
`qc.results[].mosdepth` raw tables/provenance; existing analysis fields, source
identities and artifact/download contracts are preserved. No migration or source
copying is required. Original reports can be reopened without tool execution.

[Final acceptance CI 39005371025](https://github.com/PhoenixEmik/QualiDock/actions/runs/39005371025)
on `d917322` passed **all eight jobs**, including MultiQC 1.25.1/1.35/latest-1.x
and Linux resource controls. Dedicated mosdepth checks: **46 passed** (24 unit,
22 actual-tool cases), including remote-reference HTTP canaries unchanged.
The complete local backend suite with real tools passed **510 tests**, with two
HTTP-listener canaries deselected because this sandbox cannot bind sockets;
both run in Linux CI. The dependency-light backend job intentionally reports
397 passed/115 optional-tool skips; required-tool jobs exercise genuine tools.
Frontend: **146 passed**, no skips, TypeScript/Vite build passed (existing large
ECharts bundle warning). Browser JUnit artifacts contain **66 Chromium / 42
Firefox** cases with zero failures/errors/skips, including coverage at `/`,
`/node/compute/8765` and `/rnode/compute/8765`, source/index/reference/BED hashes,
CRAM, restart/rerun, downloads, SVG export, keyboard controls and narrow layout.
Mobile coverage screenshots from both browsers were visually reviewed, without
claiming pixel equivalence. Reproducible originals are `report-browser-*`
artifacts; downloaded screenshots/XML are under ignored
`validation/coverage-final-browser/{chromium,firefox}`. #33 is accepted; #5 remains
open for representative large-file/shared-storage acceptance. No release is
prepared or published.

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
