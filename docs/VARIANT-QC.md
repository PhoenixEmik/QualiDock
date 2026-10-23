# Read-only BCFtools Variant QC (#43)

Security prerequisite #41 was accepted in CI 39930283266 and merged as #42 /
`2e16718` before this phase began. Variant QC is a separate development PR; no
release or tag is prepared.

## Qualified input and tool contract

The candidate uses exactly **BCFtools 1.24 / HTSlib 1.24**, obtained from the
official release source archive. The upstream GitHub release-asset SHA-256 is
`8caddc22610ee2851666047c859bb91da0c1e32d0c2ec553db6f153ad130e46f`.
Test provisioning verifies the digest, explicitly builds bundled static HTSlib,
and records native version, build/link details and archive/binary/library hashes.
Production never downloads tools. A newer executable with an old, missing,
prerelease or unqualified underlying library is unavailable.

Variant files have a distinct Workspace kind and no FASTQ pairing or alignment
identity. Initial genuine tests cover `.vcf` (VCF 4.2/4.3), `.vcf.gz` (ordinary
gzip/BGZF), and `.bcf` (BCF 2.2 in BGZF, level-zero BGZF or raw BCF). Whole-file
stats requires no index. Existing TBI/CSI files are unnecessary; the application
never creates indexes, copies inputs into result stores, rewrites, filters,
normalizes, annotates or calls variants.

Input-root containment and canonical authorization precede bounded format/header
inspection: 4 MiB decoded header,256 KiB per line,10000 unique sample IDs of at
most200 characters. Index-syntax markers/control characters in paths are
rejected. BGZF requires its complete EOF marker; text VCF requires a final
newline. Initial checks are header/format evidence, not complete validation or
an independent reference-assembly assertion. A sequential genuine native scan
and source identity checks are still required. A file truncated exactly at a
valid record boundary cannot be identified as a former larger file without
external expected hashes/counts.

## Independent original reports

`scripts/qualify-bcftools.py` captures actual version, exact argv, source/report
SHA-256, stdout and stderr for explicit SNP, indel, MNP, mixed/multiallelic,
multisample, symbolic/breakend/star, missing genotype/depth/alleles, empty and
gVCF cases. Equivalent encodings are compared without rewriting reports. The
committed originals are under `backend/tests/fixtures/bcftools-1.24`.

The original SN counters count records containing each type; they overlap and
are not exhaustive. A pie chart or sum interpreted as record composition would
be misleading. Record count is neither unique loci nor alternate allele count.
gVCF blocks are not expanded into per-base variants or genome coverage. TSTV
counts concern substitutions; zero transversions makes a ratio undefined even
when upstream prints `0.00`. QUAL `.` is unavailable, never quality zero. DP
site counts and sample genotype counts have different denominators. Upstream
PSC `0.0` average depth is not evidence of measured zero depth. Genotype-depth
observations use FORMAT/DP, or summed FORMAT/AD when DP is absent; upstream
excludes nonpositive values. They can include record/sample positions without
a called genotype. Site INFO/DP zero is retained, while missing INFO/DP can
appear in the `<0` underflow bin. Native charts exclude underflow rather than
turning missing values into zero. Missing/unknown
AF and singletons share a default bin; AF is not a native biological estimate.
Original values remain available for inspection with their upstream meanings.

## Execution, original parsing and native views

The existing RunManager/LocalExecutor owns scheduling, resource slots, CPU/RSS
controls, process-tree cancellation, restart, rerun, atomic manifests and
authenticated artifacts. The only science argv is `bcftools stats --threads N`
plus explicit `--samples -` when requested and one authorized canonical source.
No plugin, filter, reference or indexing options are accepted. Native warnings,
nonzero exits, changed/missing inputs and invalid original reports fail the
input; incomplete artifacts are not registered. Other inputs may still succeed.

Original stats are unchanged. Parsing streams at most16 MiB,64 KiB per line,
50000 identities per interpreted section; tables preview200 rows and charts
retain at most2000 bins without sampling. Qualified section IDs, column
definitions, numeric types, uniqueness, source IDs, complete summaries,
substitution/TiTv consistency and depth fractions are checked independently.
Unknown sections stay downloadable and uninterpreted. Safe boundary truncation
cannot be detected without external counts. Integer counts above exact JS chart
precision remain in string-valued tables/downloads without a rounded plot.

Quality Control reuses the existing explorer, settings, history, ECharts,
original-data tables and report sandbox. Native results expose record counters,
SNP/indel/MNP/other/no-ALT categories, substitution/TiTv counts, available QUAL
and site/sample-depth distributions, and explicitly requested sample counts.
No category sum, unique-site estimate, biological AF or genome coverage is
invented. Unavailable genotype/depth values stay unavailable; ambiguous average
sample depth is omitted from native metrics.

## Official MultiQC mapping and limitations

Genuine MultiQC1.25.1 and1.35 both preserve the original SN,TSTV and substitution
values with the shared adapter. Each report stays in its owned `i_…` directory;
`prepend_dirs` depth1 and disabled filename cleaning isolate duplicate source
basenames without editing original report `ID` lines. The verified
`Bcftools → stats → dataset → original-report-path` mapping identifies input
files, not biological samples. Within-file sample IDs are separately verified
against official per-sample plot identities; collisions/missing mappings fail
aggregation while original/native results remain available.

Official plots remain unchanged. Their upstream conventions include converting
missing QUAL to zero, undefined Ti/Tv to0.00 and missing average depth to zero.
General Statistics genotype hom/het fields can describe the last sample rather
than the full input. QualiDock records a visible limitation and never uses these
values as native metrics. MultiQC output is quarantined until original values
and unique source mapping pass; failure leaves a partial analysis with completed
input reports downloadable. Latest qualified1.x is also required in CI.

## Existing benchmark

Use `scripts/benchmark-analysis.py --mode bcftools --input FILE --output NEW_DIR
--hash-inputs [--variant-per-sample] [--multiqc]`. It records input bytes,
wall/child CPU time, available sampled process/RSS observations, exact argv,
constraints, original report bytes, MultiQC stage cost and source integrity.
Hashes add two separately recorded full source reads. Small fixtures measure
execution overhead only; they establish no representative performance claim.
Linux process I/O counters do not measure NFS/Lustre network throughput.

## Acceptance status

Tool/input and independent upstream qualification complete locally:18 formats/
cases,36 native invocations;78 input/security/alignment unit regressions passed.
Application execution/parser security tests passed locally (114 before the
additional genuine AD fallback case), with157 frontend tests and production
build. Genuine MultiQC1.25.1/1.35 mapping/failure tests pass. Full CI, both browsers
and Linux resource evidence are pending; #43 must remain open until those gates
pass. Large/shared-storage acceptance stays #5.
