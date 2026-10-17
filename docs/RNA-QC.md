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

Manifests add optional `qc.results[].picard`; API adds an optional mode and three
validated booleans. Existing records need no migration; rename/rerun/history and
secure downloads reuse existing infrastructure. The existing coverage raw-table
component is shared with Picard; scientific coverage data/charts are unchanged.

Original JAR/CLI/help, Java/R versions, paired metrics/PDF, single-end diagnostic
and explicit synthetic source SAM were captured on
[CI 39018972918](https://github.com/PhoenixEmik/QualiDock/actions/runs/39018972918)
(`picard-tool-study`). Committed genuine fixtures live in
`backend/tests/fixtures/picard-3.5.0`. FR150/250/350 yields original median/mean250
and SD100; RF200/300 yields SD70.710678; TANDEM400 has SD`?`. A separate actual-tool
outlier case verifies untrimmed count4 versus trimmed histogram count3 without
inventing an application recomputation. Full application/PDF/browser acceptance
will be recorded after CI. Large-input/JVM/shared-filesystem acceptance remains
independently scoped to issue #5.

