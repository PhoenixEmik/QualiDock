# RNA-seq and library alignment QC

These optional operations use the existing alignment input authorization,
RunManager slot, LocalExecutor, CPU/process-tree memory limits, cancellation,
atomic manifests and authenticated artifacts. No pipeline, executor, database,
runtime dependency or navigation page is added. Tools are installed by the
operator, never by the application. Ordinary FASTQ and existing alignment QC do
not require these optional tools or annotation files.

## RSeQC 5.0.5 (individual CLI version 5.05)

Configure `QUALIDOCK_RSEQC_INFER` / `QUALIDOCK_RSEQC_DISTRIBUTION` with existing
`infer_experiment.py` / `read_distribution.py` executables, or load them on PATH.
The exact verified CLI contract is 5.05 from the upstream 5.0.5 package. The CLI
label and suite version are both retained; other versions are unavailable until
qualified. No tools are installed to service a version probe.

```sh
export QUALIDOCK_RNA_ANNOTATIONS='{"genes":"/references/genes.bed12"}'
```

Operator-approved BED12 annotations must be absolute local readable regular files,
owned by this user/root, without symlinks or group/world writes. Validation is
bounded to 128 MiB, 16 KiB per line, one million transcripts, two million exon
blocks and 100,000 contigs. Twelve tab-separated fields, `+`/`-` strands,
transcript/coding bounds, RGB/score, exon counts/nonoverlap/bounds are checked.
Names cannot contain whitespace because the actual upstream parser uses generic
whitespace splitting. Annotation overlaps are allowed: genuine transcripts and
opposite-strand genes can overlap. Models are not merged, clipped or rewritten.
Only comment lines beginning `#` are ignored; UCSC track/browser preambles are
not silently treated as gene models.

Each selected annotation has a full SHA-256, file snapshot, transcript/block
counts and contig maximum-end dictionary. This evidence is persisted and checked
again before/after execution. Names must match the BAM header exactly and all
annotation coordinates must fit. Case-colliding names are rejected because
upstream read_distribution uppercases contigs. This establishes local annotation
identity and name/coordinate compatibility, **not an independent proof of the
reference sequence or genome assembly**. Choose the correct assembly yourself.
Unannotated BAM contigs may exist and are not assigned imaginary gene categories.

### Input and execution

Initially **BAM only**; SAM/CRAM are not qualified. No automatic reference download,
index creation, format conversion or source writes. SAMtools/HTSlib 1.22.1 head,
quickcheck and a full stats scan precede either operation, using the existing
restricted reference environment. quickcheck is header/EOF sanity only. The full
stats scan adds one source pass and is distinct from RSeQC's scientific scan.
Read-pair FASTQ metadata never applies to these alignment operations.

Choose RSeQC in the existing QC setup, choose one operation and an approved gene
model. Each input produces an independent result. Infer settings are collapsed:
default maximum usable alignments200,000, minimum MAPQ30 (bounded user controls).
No arbitrary CLI flags, filtering outputs or derived FASTQs are offered.

`infer_experiment.py -i source.bam -r genes.bed12 -s N -q Q` reports original
PairEnd/SingleEnd orientation fractions and the failed-to-determine fraction.
The original sampled usable-alignment count comes from its separately preserved
stderr, not rounded-fraction multiplication. **First eligible, gene-overlapping
alignment records**, not random sampling or independent fragments. The sample
cap does not guarantee bounded input I/O: finding eligible alignments can scan
the entire source. Filtered/unmapped/unannotated records are outside that
denominator. Failed-to-determine is not the proportion of all BAM reads that
failed sequencing or mapping. Mixed/insufficient data can produce upstream
`Unknown data type: Mixture` without fractions; these remain explicitly
unavailable, not zeros. No arbitrary threshold classifies a biological protocol.
Gene models, mapping assumptions, gene overlaps and sampled population affect
inference. Small fixtures establish parser fidelity, not biological accuracy.

`read_distribution.py -i source.bam -r genes.bed12` retains Total Reads, Total
Tags, Total Assigned Tags and all ten original categories/Total_bases/Tag_count/
Tags/Kb. Reads are accepted alignment records after upstream QC-fail, duplicate,
secondary and unmapped exclusions; supplementary handling remains upstream's.
Tags are aligned blocks with midpoint-based category precedence; spliced records
can contribute multiple tags. Nested TSS/TES windows are not additive. Original
Tags/Kb uses upstream's `Total_bases + 1` denominator and rounding; it is not a
percentage. No normalization, molecule count or biological conclusion is added.

### Results and compatibility

Native views show original strings/tables, input paths, annotation identity,
parameters and versions. Full stdout and stderr reports are downloadable along
with preflight reports/logs. Shared execution supports exclusive creation of
stderr artifacts, with a bounded diagnostic excerpt in analysis.log; no shell
wrapper/tee subprocess is introduced. Both outputs retain the shared per-file
writing limit. Malformed/incomplete/nonfinite reports fail instead of becoming
native metrics. Successful independent files survive other input failures.
Cancelled/interrupted namespaces are not registered as successful results.

Manifests gain optional `qc.annotation` / `qc.results[].rseqc` and additive modes;
historical analyses require no migration. Reruns restore annotation/settings but
revalidate current inputs. Opening results never reruns RSeQC. Existing report
viewer/authentication stays unchanged. MultiQC qualification is a separate next
milestone; no RSeQC aggregation is advertised in this initial integration.

### Evidence

The genuine upstream CLI and unmodified output were first captured on
[CI 39016787188](https://github.com/PhoenixEmik/QualiDock/actions/runs/39016787188),
artifact `rna-tool-study`. Committed fixtures include original stdout/stderr,
dependencies and explicit synthetic SAM/BED12. Ten alignments yield infer
fractions0.6000/0.2000/0.2000; read distribution has eleven aligned blocks (seven
CDS, four intronic), independently determined from geometry. The spliced record
is intentionally not collapsed to one tag. Source fixture generation occurs
only in tests; no source report is regenerated merely to view it.

A second independent fixture preserves Galaxy tools-iuc's existing hg19 RNA-seq
BAM/BED12 (40 primary alignments), original report references and pinned source
hashes; see `backend/tests/fixtures/rseqc-5.0.5/galaxy/README.md`. New real-tool
checks compare both operations against independent RSeQC execution on those
unaltered bytes, supplementing the explicit synthetic geometry. Neither subset
is used to infer population-wide biological protocol accuracy.

[RSeQC acceptance CI 39017931180](https://github.com/PhoenixEmik/QualiDock/actions/runs/39017931180)
on `10ae4d0` passed all eight jobs. Dedicated RSeQC tests: **64 passed** (45 unit,
19 actual-tool cases), including the public hg19 subset and known synthetic
stranded/unstranded/single-end populations. Frontend146 passed/build. JUnit
artifacts contain **69 Chromium /45 Firefox**, zero failures/errors/skips;
RSeQC setup/results/download/restart runs at root and both URL prefixes. Mobile
screenshots were visually reviewed, not compared pixel-for-pixel. Evidence:
`rna-tool-study`, `rna-qc-evidence`, `report-browser-*`; downloaded screenshots/XML
under ignored `validation/rna-accepted-browser`. Local full retained-tool suite:
555 passed/17 missing-local-RSeQC skips/two socket-listener canaries deselected;
the newly added public-data cases and actual RSeQC run in Linux CI, and the
socket tests remain enabled there. Missing-tool skips are not scientific evidence.

RSeQC scope relative to `ac26f0e`:22 files added/18 modified/0 deleted;
application production +678/−81 (net+597 including formatting). Added production:
`rseqc.py`, `RnaQcSettings.tsx`, `RnaQcResults.tsx`. Existing alignment lifecycle,
settings/tools, API/history, shared stderr capture and QC setup/results/types are
extended. No runtime dependency, DB or parallel execution layer. Tests, original
fixtures, test-only provisioning, existing CI and documentation form the other
changes. Large RNA-seq/shared-storage acceptance remains pending #5.

## Picard CollectInsertSizeMetrics 3.5.0

Configure `QUALIDOCK_PICARD` with the original readable **JAR** (or `picard.jar`
on PATH) and `QUALIDOCK_JAVA` with Java17 (default `java`). The JAR must be a
canonical regular local file, owned by this user/root and not group/world
writable. Shell launchers and JAR symlinks are not supported; point at the actual
JAR. There is no separate Java executor. The qualified upstream JAR SHA-256 is
recorded in test provisioning; runtime version is detected from the genuine CLI.
Picard3.5.0 `--version`/`--help` return1: the exact successful version response is
accepted only by the version probe. **Scientific runs still require exit0.**
Java17.0.20.1 is tested on macOS arm64 and Linux; other Java major versions are
not claimed qualified. Rscript4.3.3 is tested on Linux for optional original PDF.
No Java, R or JAR is installed by the application.

Choose Picard in existing QC setup with **coordinate-sorted BAM**, no index
required. CRAM is explicitly unavailable until independently qualified under the
local-reference policy. SAMtools head/quickcheck/full stats precede execution;
actual sort order is checked. Picard uses `ASSUME_SORTED=false`, strict validation,
`CREATE_INDEX=false` and `CREATE_MD5_FILE=false`. It never sorts, marks duplicates,
rewrites BAM or creates source indexes.

Defaults: `ALL_READS`, `INCLUDE_DUPLICATES=false`, `MINIMUM_PCT=0.05`,
`DEVIATIONS=10`. Advanced controls only add original per-library metrics, include
marked duplicates, or request the original PDF. Per-library mode adds upstream
`LIBRARY` accumulation and requires SM/LB for every read group, globally
unambiguous library labels and no `All_Reads` reserved-name collision. It is not
project/sample CRUD. ALL_READS rows describe the selected BAM, potentially pooling
libraries; library rows are distinct populations and must not be added to those
BAM-wide rows.

Mean, SD and histogram use Picard's median +10×MAD tail cutoff. READ_PAIRS and
other metrics can refer to the larger untrimmed population. Categories below the
0.05 fraction threshold may be omitted: unavailable is not zero. The native
summary retains reported orientation, count, median, mean/SD and population;
original metrics/histogram tables retain all columns/strings with bounded native
row previews. A single TANDEM observation genuinely produces SD`?`; this is
unavailable, never changed to0. These alignment-based observations are not read
lengths or unique molecules. For RNA-seq, genomic template spans can include
introns and are not direct mature-RNA fragment lengths.

Original numeric histogram is always retained when observations exist. PDF is
opt-in and requires Rscript; without R, metrics/numeric histogram remain usable.
No synthetic HTML/PDF or alternative scientific histogram calculation is added.
The original PDF is signature/completeness checked and downloadable through the
existing authenticated attachment endpoint. Only named, validated completed
Picard PDFs gain artifact access; arbitrary PDFs and private temporary files do
not. Existing HTML viewer/CSP remain unchanged.

The JVM uses explicit Xms64MiB, Xmx75% of the existing executor allowance
(session memory minus256MiB), and ActiveProcessorCount equal to the selected CPU
budget. Shared process-tree limits cover Java/native/R children. Inherited JVM
option variables cannot override the allocation. TMP/TEMP/TMPDIR, Java temp and
Picard TMP_DIR point to the owned private run namespace; R startup profiles are
disabled for the original base-R plotting script. Private temp files are never
artifacts. Rscript's actual version is captured when PDF is requested.

Parser bounds:64MiB metrics,16KiB lines,3003 unique population/orientation rows;
metrics/histogram previews retain at most200 rows and originals retain all data.
Duplicate columns/populations, invalid counts/nonfinite numbers, malformed or
incomplete histogram/PDF fail truthfully. A count cannot exceed source alignment
records; this sanity bound is not independent fragment/molecule validation.
Single-end/no-qualifying-pair runs can legitimately exit0 **without output files**:
only the actual explicit zero-pair diagnostic enables an unavailable result, with
original logs retained. Missing files without that diagnostic are failures.
Cancelled/interrupted outputs are not published; other successful files survive
partial input failures.

Manifests add optional `qc.results[].picard`; API adds an optional mode and validated boolean options, including optional
MultiQC aggregation. Existing records need no migration; rename/rerun/history and
secure downloads reuse existing infrastructure. The existing coverage raw-table
component is shared with Picard; scientific coverage data/charts are unchanged.

Original JAR/CLI/help, Java/R versions, paired metrics/PDF, single-end diagnostic
and explicit synthetic source SAM were captured on
[CI 39018972918](https://github.com/PhoenixEmik/QualiDock/actions/runs/39018972918)
(`picard-tool-study`). Committed genuine fixtures live in
`backend/tests/fixtures/picard-3.5.0`. FR150/250/350 yields original median/mean250
and SD100; RF200/300 yields SD70.710678; TANDEM400 has SD`?`. A separate actual-tool
outlier case verifies untrimmed count4 versus trimmed histogram count3 without
inventing an application recomputation. Picard feature acceptance on
[CI 39021134853](https://github.com/PhoenixEmik/QualiDock/actions/runs/39021134853)
passed all eight jobs, including **49 Picard unit/genuine-tool cases**, original
PDF generation, JVM limits, cancellation, restart and both browsers. Large-input/JVM/shared-filesystem acceptance remains
independently scoped to issue #5.


## Verified MultiQC aggregation

RSeQC and Picard setup now offer optional MultiQC aggregation in the same run.
Only completed, supported original reports enter the existing file-list adapter.
Unavailable zero-observation infer/Picard outputs are explicitly omitted with a
warning; their original diagnostics remain downloadable. Independent input
failures and failed aggregation preserve successful QC reports and yield a
truthful partial analysis rather than discarding results.

Verified official modules: RSeQC `infer_experiment` / `read_distribution`, Picard
`InsertSizeMetrics`, and the existing SAMtools stats/flagstat adapter. RSeQC raw
module data, rather than absent General Statistics, establishes reported sample
identities. Picard uses the official filename naming option (`picard_config.
s_name_filenames` on 1.25.1, `use_filename_as_sample_name: [picard]` on newer
qualified 1.x), with collision-isolated internal report IDs. Original command
headers, values and HTML reports are never rewritten. Actual source mappings
are checked against the corresponding saved official raw module keys; missing
or ambiguous mappings surface as partial errors, never guessed associations.

Picard per-library aggregation is explicitly unsupported: genuine MultiQC
modules combine overlapping ALL_READS/library rows and overwrite repeated
orientation keys. Disable MultiQC to retain all original native library
populations, or use BAM-wide Picard reports for aggregation. MultiQC's
orientation-combined statistics also differ from Picard's per-orientation
statistics; the native summary remains authoritative for original Picard rows.
RSeQC's official MultiQC plots transform some nested distribution categories;
use the native original table/download for untouched upstream categories.

The mixed-report regression executes actual MultiQC 1.25.1 and 1.35 against
unchanged genuine fixtures, including duplicate original BAM basenames, precise
fractions, tag counts and Picard's missing `?` SD. CI additionally exercises the
current `<2` compatibility target. Full application tests cover independently
successful reports, intentional MultiQC failure, authenticated preview/download,
source immutability, restart and rerun. Browser tests retain the native tables
and open the corresponding genuine interactive combined plots in the existing
isolated viewer. No new report renderer or scientific chart system is added.

Aggregation is scoped to reports generated by the current operation. Existing
MultiQC-only external imports retain their explicit FastQC/fastp allowlist;
this phase does not silently admit arbitrary alignment logs or invent a
cross-analysis report collection workflow.

## Expansion change inventory

Relative to `ac26f0e` (the accepted pre-RNA baseline), application production and
the existing benchmark CLI changed **+1474 / -200 lines, net +1274**, across 26
files. This includes existing formatting and shared-table extraction; it is not
a claim of architectural reduction. No runtime dependency or new persistence,
executor, scheduler, project feature or chart framework was added. No files
were deleted in this expansion. Complete code/test/fixture changes are available
in the [review diff](https://github.com/PhoenixEmik/QualiDock/compare/ac26f0e...343a027).

**Added production files:**

- `backend/qualidock/picard.py`
- `backend/qualidock/rseqc.py`
- `frontend/src/PicardResults.tsx`
- `frontend/src/PicardSettings.tsx`
- `frontend/src/ReportedTable.tsx`
- `frontend/src/RnaQcResults.tsx`
- `frontend/src/RnaQcSettings.tsx`

**Modified production files:**

- `backend/qualidock/alignment.py`
- `backend/qualidock/app.py`
- `backend/qualidock/config.py`
- `backend/qualidock/executor.py`
- `backend/qualidock/history.py`
- `backend/qualidock/import_formats.py`
- `backend/qualidock/manager.py`
- `backend/qualidock/multiqc.py`
- `backend/qualidock/optional_qc.py`
- `backend/qualidock/tools.py`
- `backend/qualidock/validation_jobs.py`
- `frontend/src/App.tsx`
- `frontend/src/CoverageResults.tsx`
- `frontend/src/NewAnalysisForm.tsx`
- `frontend/src/OptionalQcResults.tsx`
- `frontend/src/ResultsList.tsx`
- `frontend/src/api.ts`
- `frontend/src/types.ts`
- `scripts/benchmark-analysis.py`

Test additions are `test_rseqc.py`, `test_rseqc_real.py`, `test_picard.py`,
`test_picard_real.py`, `test_alignment_multiqc.py`, `test_benchmark_alignment.py`,
and two dedicated browser files. Genuine original outputs/provenance are under
`backend/tests/fixtures/rseqc-5.0.5` and `picard-3.5.0`; test-only fixture/provision
scripts are `prepare-rna-test.py`, `prepare-insert-test.py`, `setup-rna-ci.sh`,
`setup-picard-ci.sh`. The existing shared MultiQC test and CI workflow are extended.
README, OPTIONAL-QC, BENCHMARKING and VALIDATION link the actual contracts/evidence.
These preserve historical scientific records rather than creating migrations.


Incomplete MultiQC bundles are kept on disk for diagnosis but are excluded from
artifact indexing when the latest existing MultiQC execution records a nonzero
or unfinished exit. This uses existing execution metadata, not another state
model. Original successful QC reports remain downloadable. Historical manifests
without such execution evidence preserve their existing report compatibility.
Regressions explicitly create an incomplete HTML/JSON bundle before failure and
verify it is unpublished, including after restart; active/cancelled exits and
legacy metadata are covered separately.


Final code `343a027` passed all eight jobs in
[CI 39023607426](https://github.com/PhoenixEmik/QualiDock/actions/runs/39023607426).
The downloaded browser JUnit contains72 Chromium /48 Firefox cases, zero failures,
errors or skips; latest native screenshots were reviewed under ignored
`validation/rna-343-browser`. Complete scientific/security/version evidence and
local environment limitations are recorded in [VALIDATION.md](VALIDATION.md).
Across source, tests, fixtures, workflow and documentation this expansion adds44
files, modifies25 and deletes0. Application plus the existing benchmark CLI net
+1274 production lines; there are no new runtime dependencies or persistence
migrations. This final follow-up is documentation only (`[skip ci]`); all
production/test/workflow changes are included in the accepted code CI above.

## RSeQC gene-body coverage 5.0.5 (#34)

`geneBody_coverage.py` is an optional third RSeQC operation in the existing QC
setup. Configure `QUALIDOCK_RSEQC_GENEBODY` or provide the original executable on
PATH. CLI version **5.05** is required. It uses the same approved BED12 models,
authorized BAM-only inputs, execution slot, resource limits and secure artifacts.
The application neither installs tools nor sorts, converts or indexes source data.

An existing authorized BAI/CSI is required. SAMtools head/quickcheck/full stats
must establish a usable dictionary, `SO:coordinate` and actual coordinate sorting.
An indexed primary-mapped-record scan across the complete reference dictionary
must match the independent sequential stats count. This detects missing, corrupt,
truncated and inconsistent indexes; **count agreement is operational evidence,
not a mathematical proof of every index interval or a cryptographic BAM/index
binding**. Original BAM and chosen index are SHA-256 hashed before and after;
snapshots, exact paths, hashes, commands and annotation identity are persisted.
No source index is created. Private run-owned symlinks expose exactly the selected
BAM/index with safe names, including CSI under the `.bam.bai` companion spelling
required by this upstream version. They neither copy data nor appear in downloads.
Commas, quotes and shell/HTML characters in original filenames never become
R variable names or shell commands.

Minimum eligible **exonic transcript length** defaults to 100 bp and must be at
least 100 (the upstream constraint). This is a single-threaded scientific tool;
the chosen session allocation still bounds its execution. Original transcript
selection, pileup filtering, percentile calculation and negative-strand reversal
are performed exclusively by RSeQC. The untouched table describes aggregated
coverage at transcript-relative percentiles 1–100, oriented **5′ → 3′**. It is not
absolute genome depth, a transcript expression estimate or a biological fragment
count. Overlapping transcripts/isoforms can contribute overlapping observations.
Annotation, eligibility length, alignment characteristics and protocol all affect
interpretation. QualiDock provides no bias threshold, degradation verdict or
invented 5′/3′ ratio.

Native ECharts displays exact original values without normalization, smoothing,
interpolation or fabricated positions; hover retains the reported strings. PNG
and SVG exports use the existing chart controls. Missing, duplicated or reordered
positions, ambiguous sample rows, nonfinite/negative values and malformed tables
fail clearly. Header-only no-eligible-profile output and verified all-zero signal
are explicitly unavailable. A uniform **positive** profile retains its native
flat curve; it is not incorrectly classified as absent signal. Original reports
remain downloadable. Upstream may emit fewer than 100 distinct values for some
very short models even when its header has 100 labels; such inconsistent tables
are rejected rather than filled or relabeled.

Numerical execution uses genuine `--skip-plot`. Optional original PNG generation
runs the **unchanged generated R script** through the same LocalExecutor and
records R version, exit code and separate diagnostics. Rscript is optional; a
missing runtime or failed/truncated plot does not discard verified numerical
results. Only completed, bounded signature/chunk/CRC-checked PNGs are registered;
failed PNGs remain private even after restart. The R script uses **min-max
normalization** `(value-min)/(max-min)` whereas the native chart preserves the
original table. For a constant profile upstream normalization is undefined:
its verified numerical observations remain visible/downloadable, and the
original plot is explicitly unavailable. Only the qualified upstream empty/
constant-profile diagnostics allow these numerical-only outcomes after its
nonzero exit; arbitrary execution failures are not accepted as scientific success.

Optional MultiQC uses the official `gene_body_coverage` module, saved raw
`rseqc_gene_body_cov` values and existing source mapping. Internal input IDs
remain unique across duplicate original basenames; the original table is never
rewritten. MultiQC's percentage plot is min-max normalized to 0–100 and its
Counts plot retains original values; neither is interchangeable with absolute
depth. Non-informative profiles are omitted with a warning to avoid the upstream
normalization division-by-zero. Aggregation failure preserves successful native
and original reports.

### Qualification and acceptance evidence

PR [#36](https://github.com/PhoenixEmik/QualiDock/pull/36) was already merged as
`d4e5fe2`; this implementation extends its existing qualification script/tests.
Its [successful CI 39185806278](https://github.com/PhoenixEmik/QualiDock/actions/runs/39185806278)
contains the original `rna-gene-body-tool-study` artifact. The genuine table,
original R script, diagnostic and immutable source hashes are preserved under
`backend/tests/fixtures/rseqc-5.0.5/genebody`. The PNG was visually inspected:
its maximum is 1, while the source table maximum is 2. This is normalization,
not a discrepancy to "correct" by editing upstream reports.

Local genuine execution additionally uses RSeQC 5.0.5, SAMtools 1.22.1 and
Rscript 4.4.1. Linux CI uses its existing provisioned R runtime and executes required
index, original-report, cancellation, restart, plot-failure and scientific-value
regressions. Accepted CI/test results are recorded in [VALIDATION.md](VALIDATION.md#rseqc-gene-body-coverage--2026-10-19). Tiny fixtures are fidelity/security evidence only: full hashing adds
two BAM passes and the indexed-count check another mapped-record pass in addition
to existing stats and scientific work. No large-BAM, NFS/Lustre throughput or
representative memory-performance acceptance is claimed; #5 remains independent.
CRAM and Picard CollectRnaSeqMetrics (#35) remain outside this milestone.


### Final acceptance and footprint

Code `27ac706` passed [CI 39192950625](https://github.com/PhoenixEmik/QualiDock/actions/runs/39192950625),
**all eight jobs**. The required Gene Body job passed **49 tests with no skips**;
the **9 original #36 qualification tests** remain enabled in the complete backend
job. Frontend **150 passed** with TypeScript/Vite build. Downloaded browser JUnit
records contain **75 Chromium /51 Firefox**, zero failures/errors/skips. Both
browsers cover root and the two existing reverse-proxy prefixes, real execution,
original PNG/table downloads, SVG export, parameter submission, file browsing,
mobile layout and restart. Desktop Chromium and mobile Firefox screenshots were
visually reviewed against the original R PNG/table; this is not pixel equivalence.
The table's raw maximum 2 versus the original normalized PNG maximum 1 is
intentional and explained in the UI.

Evidence artifacts: `genebody-qc-evidence`, `rna-gene-body-tool-study`,
`rna-multiqc-1.25.1-evidence`, `rna-multiqc-1.35-evidence`,
`rna-multiqc-latest-1x-evidence`, and `report-browser-*`. Local copies are under
ignored `validation/genebody-accepted` and `validation/genebody-browser`.
Independent artifact inspection confirmed all 100 original strings and persisted
source/index hashes for BAI, CSI, alternate BAI spelling and the public hg19
subset. The latter is sorted/indexed only in test-owned storage; its committed
original and annotation remain unchanged. Browser-generated BAM/index files
also stay in isolated test-owned directories.

Tested tools: **RSeQC 5.0.5 /CLI 5.05**, **SAMtools 1.22.1**, **MultiQC 1.25.1 and
1.35**, **Rscript 4.4.1 locally /4.3.3 in Linux CI**. Local complete backend:
**579 passed /131 missing-optional-tool skips /2 sandbox-blocked remote-search
canaries deselected**. The canaries stay enabled in the accepted Linux backend
job (**517 passed /195 missing-tool skips**); required provisioned jobs execute
actual supported tools, including existing FASTQ/processing/alignment workflows.
The existing Vite chunk-size warning remains; no assertions or supported tests
were disabled to achieve acceptance.

Relative to merged qualification baseline `d4e5fe2`, application production code
changes **+268 /-60 lines, net +208**, across 20 files. Overall scope including
this validation record: **10 added /28 modified /0 deleted files**. No runtime
dependency, database, executor or persistence migration is added. The only new
production file is `frontend/src/geneBodyChart.ts`; existing `rseqc.py` owns the
focused adapter/parser and existing `NativePlot` /`ReportedTable` provide chart
lifecycle, exports and raw-data inspection.

Added tests: `backend/tests/test_genebody.py`, `backend/tests/test_genebody_real.py`,
`frontend/tests/genebody.test.ts`; six genuine fixture/provenance files are in
`backend/tests/fixtures/rseqc-5.0.5/genebody`. The existing #36 qualification
script/test/workflow are reused, with a strict version/help/hash study extension.
The full [file inventory and review diff](https://github.com/PhoenixEmik/QualiDock/compare/d4e5fe2...27ac706)
records the small alignment/tool/config/API/history/artifact wiring, RNA setup/
results/types, source-mapping compatibility, browser tests and documentation.
There is no release, OOD/PBS change, #35 implementation or representative
large/shared-storage acceptance (#5 remains open).
