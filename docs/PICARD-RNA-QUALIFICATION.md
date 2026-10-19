# Picard 3.5.0 CollectRnaSeqMetrics qualification (#35)

This is a test-only scientific qualification, not an integrated QC operation.
No production API, settings, UI, metric calculation, manifest or execution
adapter is changed. Issue #35 and the Draft PR remain open for evidence review.
No release is prepared.

## Reproduce and evidence

Use existing `scripts/setup-alignment-ci.sh` and `scripts/setup-picard-ci.sh`
in the Linux CI test environment, which already pins SAMtools/HTSlib 1.22.1,
Picard 3.5.0 (SHA-256 `b7d97861c3a54ba5a421f5a317f38382f955803862d30ef4aca2bcdc54943631`),
Java 17 and R. The application never installs them.

```sh
python scripts/qualify-picard-rna.py \
  --jar "$RUNNER_TEMP/qualidock-picard-tools/picard.jar" \
  --samtools samtools --rscript "$(command -v Rscript)" --multiqc multiqc \
  --output validation/picard-rna-qualification
pytest -q backend/tests/test_picard_rna_qualification.py
```

The destination must be new. Only synthetic test-owned SAM/BAM/refFlat/interval
files are created; no user BAM is copied, sorted, indexed or changed. Test SAM
records are generated in coordinate order and converted with genuine SAMtools.
Each BAM, SAM and annotation is hashed before/after the study. No indexes are
required or generated. Every process uses the existing LocalExecutor, bounded
512 MiB Java heap, 1 CPU, 1536 MiB process-tree RSS limit and per-command timeout.
Paths and argv are arrays, without a shell. Tool credentials/JVM injection vars
are excluded; references and temporary files remain local.

The CI matrix tests MultiQC 1.25.1, 1.35 and the resolved `>=1.25,<2` target.
Artifacts `picard-rna-<target>-qualification` retain all original reports/PDF,
input BAM/SAM/refFlat/intervals, help/version stdout and stderr, exact argv,
exit statuses, `commands.json`, `qualification.json`, source hashes, MultiQC
HTML/structured JSON/config/file lists and diagnostics. Success is determined
by independent numerical assertions, not exit status alone. Committed original
text reports and their hashes are in `backend/tests/fixtures/picard-3.5.0/rna`.
No output is rewritten to satisfy Picard or MultiQC detection.

Local execution additionally qualified Java 17.0.20.1, SAMtools/HTSlib 1.22.1
and Rscript 4.4.1. The macOS sandbox denies `ps`; the explicitly labeled
`--unmeasured-rss` study option disables RSS monitoring/enforcement only for
local evidence, retaining the Java heap bound. This option is **not used in CI**.
Zero/unavailable RSS observations are never peak-memory acceptance.

## Actual CLI contract

The original JAR's `CollectRnaSeqMetrics --version` exits **1** with
`Version:3.5.0`; this is a probe exception, not a scientific success convention.
`--help` is preserved. Scientific successes exit 0. Fully named arguments:

| Argument | Qualified behavior |
| --- | --- |
| `INPUT`, `OUTPUT` | Separate read-only coordinate BAM and owned metrics text file. BAM only qualified; no CRAM claim. |
| `REF_FLAT` | Required native local annotation; strict operator validation must precede future execution. |
| `STRAND_SPECIFICITY` | Required explicit `NONE`, `FIRST_READ_TRANSCRIPTION_STRAND`, or `SECOND_READ_TRANSCRIPTION_STRAND`; no inference from RSeQC. |
| `MINIMUM_LENGTH` | Default 500; coverage transcript eligibility, not alignment/base filtering. A 600-base model becomes ineligible at 700. |
| `END_BIAS_BASES` | Default 100; bases at each transcript end used for bias. |
| `RIBOSOMAL_INTERVALS` | Optional SAM interval_list with matching sequence dictionary, 1-based inclusive intervals. |
| `RRNA_FRAGMENT_PERCENTAGE` | Default 0.8; overlap criterion for upstream rRNA assignment, not an aligned-base fraction setting. |
| `CHART_OUTPUT` | Optional genuine PDF, requiring Rscript. Absence of a chart option does not require R. |
| `METRIC_ACCUMULATION_LEVEL` | Default ALL_READS; LIBRARY adds an overlapping population, not an independent biological sample. |

Use STRICT validation, explicit `ASSUME_SORTED=false`, no index/MD5 creation,
private `TMP_DIR`/`java.io.tmpdir`, `-XX:ActiveProcessorCount=1`, and bounded heap.
Single-valued duplicate legacy arguments are rejected; test overrides replace
rather than append scalar arguments. Accumulation levels intentionally repeat.
Missing R fails before metrics generation. A failure-only Rscript stand-in is
used separately to observe a plotting failure after metrics have been written;
no scientific result or successful plot is simulated. A future adapter must
separate valid numerical output from optional plotting failure. The original
R-rendered PDF is retained and checked by the existing Picard PDF validator.

## Native refFlat contract and BED12 decision

refFlat has eleven tab-separated columns:

| Column | Meaning |
| --- | --- |
| 1–4 | Gene name, transcript name, contig, transcript strand (`+`/`-`). |
| 5–8 | Transcript start/end and coding start/end; 0-based, half-open. |
| 9 | Exon count. |
| 10–11 | Comma-separated absolute exon starts/ends, same coordinate convention; trailing commas are supported. |

Gene and transcript identity are distinct. Multiple isoforms may belong to one
gene; chromosome/strand must agree within a gene. Reject duplicate or ambiguous
transcript names and malformed counts/bounds/exon arrays in a future approved
annotation parser. Preserve noncoding (`cdsStart == cdsEnd`) models explicitly.
Models must be ordered, nonoverlapping, within transcript and exact BAM contig
bounds. Name/bounds agreement is not proof of matching reference assembly.
Record the actual identity evidence; do not imply sequence-level verification.

Actual upstream risks: unknown-contig, duplicate-transcript and inconsistent
gene-strand models can be skipped with **exit 0**, yielding intergenic counts.
Out-of-dictionary transcript coordinates may also be accepted. Therefore upstream
STRICT validation alone is insufficient annotation authorization/validation.
A malformed field count and mismatched rRNA sequence dictionary fail nonzero.

**Recommend separately approved native refFlat files**, using the existing
operator-file policy (canonical absolute regular local files, owner/root,
no escaped symlink or group/world write), SHA-256/snapshot verification,
16 KiB lines /128 MiB total and transcript/exon/contig bounds analogous to BED12.
This is a proposed subsequent contract; no new production parser/config exists.

BED12 supplies coordinates, strand and one name, but not necessarily distinct
unambiguous gene/transcript IDs. An explicit offline conversion is feasible only
with an independently curated transcript→gene mapping and verified CDS semantics:
absolute exon starts = chromStart + blockStart; exon ends add blockSize;
transcript and thick bounds retain their half-open convention. Ordinary BED12
alone is insufficient. No runtime conversion, gene-name guessing, download,
reference manager or annotation database is proposed or implemented.

## Independently checked scientific observations

The category fixture contains seven PF 50-base records (one unmapped), six
mapped PF records and one additional QC-failed record, using explicit geometry:

| Original metric | No rRNA file | Approved matching interval_list |
| --- | ---: | ---: |
| PF_BASES | 350 | 350 |
| PF_ALIGNED_BASES | 300 | 300 |
| CODING_BASES | 100 | 100 |
| UTR_BASES | 50 | 50 |
| INTRONIC_BASES | 50 | 50 |
| INTERGENIC_BASES | 100 | 50 |
| RIBOSOMAL_BASES | blank (unavailable) | 50 |

These are **bases**, not reads, fragments or molecules. In the pinned collector,
QC-failed and secondary records are excluded; unmapped PF sequence contributes
to PF_BASES. Supplementary-alignment base semantics remain upstream's and must
not be relabeled as unique molecule bases. Annotation-category priority also
remains upstream's; unlike RSeQC tags, these are base assignments.

`PCT_CODING_BASES`, `PCT_UTR_BASES`, `PCT_INTRONIC_BASES`,
`PCT_INTERGENIC_BASES`, and available `PCT_RIBOSOMAL_BASES` divide by
PF_ALIGNED_BASES. They are fractions (e.g. `0.333333`), not percent-unit values.
`PCT_USABLE_BASES` divides coding+UTR by PF_BASES (`0.428571` here).
No rRNA annotation gives blank fields, never evidence of biological absence.
Empty/insufficient populations may contain upstream default zeros; preserve
raw strings while distinguishing unavailable scientific observations.

For paired fixtures entirely within one plus-strand transcript:

| Population | NONE correct/incorrect | FIRST correct/incorrect | SECOND correct/incorrect |
| --- | --- | --- | --- |
| R1 forward /R2 reverse | 0 /0 | 2 /0 | 0 /2 |
| R1 reverse /R2 forward | 0 /0 | 0 /2 | 2 /0 |
| Equal mixture | 0 /0 | 2 /2 | 2 /2 |

Those strand counts count qualifying aligned records, not independent fragments.
Strand settings affect strand tallies, not a biological protocol determination.
A separate single-end fixture confirms FIRST 2/1 versus SECOND 1/2. NONE's zero
correct/incorrect fields do not mean zero strand agreement.

For eligible 600-base plus/minus models, uniform coverage gives original bias
values 1/1/1; twofold 5′ coverage over the first 200 bases gives 1.5/0.75/2 for
MEDIAN_5PRIME_BIAS /MEDIAN_3PRIME_BIAS /MEDIAN_5PRIME_TO_3PRIME_BIAS.
Both biological directions are checked. The original histogram has **101
positions 0–100**, not RSeQC's 100 positions 1–100. Coverage is normalized by
transcript mean, direction-corrected and averaged across selected models;
only eligible/high-expression transcripts participate. It is not absolute depth.

**Pinned upstream limitation:** `Gene.addCoverageCounts` uses an exclusive
alignment-block end although its caller supplies an inclusive end. A 600-base
exactly spliced alignment contributes 598 coverage-counter positions, falls below
the collector's mean≥1 eligibility requirement and yields no histogram/default
zero bias. The `boundary-spliced` original output records this behavior. Uniform
and biased qualification geometries use explicit one-base exon-boundary overhangs
so independently expected exonic profiles remain 1 and 2. Neither the reports
nor upstream calculations are corrected locally. A subsequent UI must mark bias
unavailable without an eligible histogram and explain this version limitation.

## Incremental value relative to retained tools

| Tool | Counting/annotation contract | Distinct value /overlap |
| --- | --- | --- |
| RSeQC infer_experiment | Sampled eligible alignment orientations /BED12 | Protocol-dependent orientation fractions, including undetermined; no automatic mapping to Picard setting. |
| RSeQC read_distribution | Read/aligned-block midpoint tags /BED12 | Annotation categories overlap conceptually, not numerically with base-weighted Picard assignments. |
| RSeQC geneBody_coverage | Eligible BED12 transcripts; 1–100 raw percentile profile | Overlaps coverage shape; different eligibility, aggregation, normalization and position grid. |
| SAMtools stats /flagstat | Alignment/base/flag summaries, no gene model | General alignment QC; lacks gene-region/rRNA base fractions and transcript bias. |
| mosdepth | Depth/breadth with explicit alignment filters /optional BED | Absolute coverage populations differ; not RNA transcript-normalized bias. |
| Picard RNA metrics | Native refFlat, explicit strand and optional interval_list | PF/usable coding+UTR fractions, base-weighted annotation/rRNA assignments, named strand populations and selected-transcript bias. |

No fields are treated as scientifically interchangeable solely by name.
Additional annotation parsing and JVM/R overhead are real costs; tiny fixtures
cannot qualify large RNA-seq, NFS/Lustre, biological accuracy or representative
peak memory. This study proposes no alternative execution/reporting system.

## MultiQC findings

Original unchanged ALL_READS reports with duplicate original `input.bam`
basenames collapse to one `input` sample under default naming. Use existing
1.25.1 `picard_config.s_name_filenames=true` or 1.35
`use_filename_as_sample_name: [picard]` with collision-free report filenames.
The official `Picard/RnaSeqMetrics` source section then maps each report uniquely.
The study asserts exact original counts and bias values in
`multiqc_picard_RnaSeqMetrics`, available General Statistics and coverage plots.

MultiQC deliberately converts original `PCT_*` fractions to percent-unit values
by ×100. Missing rRNA becomes `NA`, not zero. Both transformations are recorded;
do not silently treat MultiQC JSON as unchanged original Picard strings.
The current production source-map allowlist supports InsertSizeMetrics only;
its rejection of RNA entries is retained and tested. A later adapter needs one
explicit section addition and verified names, not a new mapper.

LIBRARY +ALL_READS reports are studied but not approved for combined native
sample identity: the official RNA module reads a population without preserving
all independent accumulation semantics. A future mode should initially permit
**ALL_READS only**. A deliberately header-only incomplete report must not be
accepted as a validated Picard scientific report even if a MultiQC command exits
0; its actual exit/JSON behavior remains in the evidence.

## Decision gate: Outcome A — integration justified, subsequent review required

Base-weighted coding/UTR/intron/intergenic and optional rRNA fractions add
practical value. A minimal **BAM-only, ALL_READS-only, native approved refFlat**
mode is justified, with the pinned coverage limitations stated explicitly.
This is a recommendation, not authorization to implement it in this phase.

Smallest subsequent changes after review:

- `picard.py`: focused RNA options/parser/execution beside the existing JVM adapter;
  exact upstream values, no custom scientific calculations, distinguish PDF failure.
- `alignment.py`: reuse source authorization, coordinate validation, full preflight
  and identity checks; strict refFlat/interval dictionary compatibility.
- `optional_qc.py`, tools/config: one optional operation and separately configured
  refFlat/interval file allowlists using existing approved-file policy.
- Existing QC setup/results: explicit strand choice, approved annotation and optional
  PDF/rRNA selection; concise tables and original report access, no new dashboard.
- `multiqc.py` /source mapping: official RnaSeqMetrics section, proven filename config,
  ALL_READS-only population, fractions versus percent units explicit.

No merge, #35 closure, production mode or release is performed by this study.
CI evidence/results and any remaining qualification limitations are recorded
below once the branch's actual workflows complete.
