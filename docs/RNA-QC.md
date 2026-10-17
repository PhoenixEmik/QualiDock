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

Full application real-tool/browser acceptance will be recorded after those CI
jobs pass. Representative large RNA-seq and shared-storage acceptance remain
pending issue #5; small-fixture output correctness is not a throughput claim.
