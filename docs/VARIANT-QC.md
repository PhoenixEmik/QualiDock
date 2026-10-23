# Read-only BCFtools Variant QC (#43)

Security prerequisite #41 was accepted in CI 39930283266 and merged as #42 /
`2e16718` before this phase began. Variant QC is qualified in separate PR #44; no
release or tag is prepared.

## Qualified input and tool contract

The qualified runtime uses exactly **BCFtools 1.24 / HTSlib 1.24**, obtained from the
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
most200 characters. Duplicate INFO/FORMAT IDs, repeated declaration attributes
and unterminated quoted metadata are rejected. Header identities support field
reordering and quoted commas without inventing tags. Genuine BCFtools1.24 can
silently accept conflicting duplicate INFO/DP definitions with exit0; that is
insufficient input evidence and the application rejects it before execution.
Index-syntax markers/control characters in paths are
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

Per-sample `PSC` is preserved as upstream counters, not a new genotype-counting
engine. In [1.24 `sample_gt_stats` / `do_sample_stats`](https://github.com/samtools/bcftools/blob/1.24/vcfstats.c),
the hom/het counters follow the called-allele SNP-or-reference branch (including
ALT=`.`); a mixed SNP/indel call may contribute to both categories. Transition/
transversion counters count distinct called SNP alternate alleles per genotype,
not allele copies. `nIndels` counts nonreference calls carrying an indel;
haploid reference/alternate calls have separate counters and return before the
diploid categories. `nSingletons` follows the upstream one-nonreference-diploid-
sample counter, not alternate allele count1. `nMissing` counts unknown GT when
the record actually has a GT field; records omitting GT do not increment it.
Consequently these columns neither partition all genotypes nor establish a
complete missingness/call rate or biological sample identity.

A FORMAT/GT header declaration alone does not prove that records contain GT.
Genuine1.24 reports all-zero PSC without warnings for declared-but-unused GT.
Native per-sample counters therefore require unambiguous nonzero reported GT
counter evidence in addition to the declaration. Ambiguous zero-only reports
remain original/downloadable; the native genotype view stays unavailable.
This conservative rule can withhold zero-only PSC even for unusual valid
genotyped populations; it never fills missing observations or infers a rate.

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
than the full input. Per-sample plots derive categories from PSC and record
counts; records omitting GT do not establish genotype presence or a complete
call/missingness rate. QualiDock records a visible limitation and never uses these
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

## Acceptance — 2026-10-23

[CI 39952410569](https://github.com/PhoenixEmik/QualiDock/actions/runs/39952410569),
application commit `afa771f`, passed **all eight jobs**. Chromium was retried
alone on the identical commit after slow upstream system-package downloads
consumed the first attempt's60-minute job budget during the last report suite.
The other seven successful gates were retained; no test, numerical assertion or
production resource limit was disabled or relaxed. The accepted retry completed
the whole Chromium suite. Browser CI budget includes dependency downloads/native
builds; it does not change the application's CPU/RSS/process-tree controls.

| Gate | Genuine accepted evidence |
| --- | --- |
| BCFtools/native HTSlib | Exactly1.24 /1.24; official source digest, bundled static library, native version/link/build hashes retained |
| Variant tests | **123 passed, zero failures/errors/skips per MultiQC target**:1.25.1,1.35,latest1.x (resolved1.35) |
| Independent originals |18 cases/encodings,36 direct native invocations, with expected no-sample `-s -` rejections; source hashes unchanged and equivalent scientific sections identical |
| Complete backend |694 passed /273 missing-optional-tool skips; provisioned jobs require and execute the genuine tools |
| Frontend |158 passed; TypeScript/Vite production build passed |
| Chromium /Firefox |**81 /57**, zero failures/errors/skips; root and both proxy prefixes, native statistics, original downloads, missing-data states, history/restart/rerun and mobile layouts |
| Existing scientific workflows |FastQC/MultiQC, fastp/SeqKit, nanoq/NanoPlot, FastQ Screen, SAMtools/CRAM, mosdepth, RSeQC and both Picard operations all passed |
| Patched alignment/security |66 cases per matrix target; BAM/CRAM flagstat byte-identical to original1.22.1 reports, all39 SN values/notes unchanged; version/argv provenance retained |
| Linux resources |Actual1 CPU /1 GiB cgroup, genuine SAMtools and BCFtools scanning/cancellation, source immutability, unpublished partial reports, shared RSS termination, guardian, queue and restart recovery all passed |

Downloaded evidence is under ignored
`validation/variant-qualification/accepted-ci-39952410569/`. Original reports,
exact argv/versions, source/report SHA-256, source mappings, build/link records,
JUnit and genuine benchmark JSON are retained in the CI artifacts. Final mobile
Firefox and Chromium screenshots were inspected; native axes/zoom controls stay
separate and the existing report sandbox is unchanged.

The interface does not estimate AF, unique loci, whole-genome coverage or absent
genotypes/depth. Native zero-only PSC can remain unavailable as described above;
original official MultiQC conventions/limitations remain explicit. The local
one/two-thread comparison also retained identical scientific sections for plain,
BGZF, BCF and raw BCF inputs; it is not a performance claim. Actual large/private
VCF/BCF and NFS/Lustre measurements remain open in #5 (with an explicit variant
follow-up), site OOD/OpenPBS acceptance stays #4, and release #7 stays deferred.
No QualiDock release or tag is prepared.

## Change inventory

Relative to accepted security merge `2e16718`, the feature adds108 files,
modifies26 and removes none, including the final acceptance record.
Of these,93 are compact genuine fixture inputs, original reports, stderr and
provenance under `backend/tests/fixtures/bcftools-1.24/`; see the complete
[PR #44 diff](https://github.com/PhoenixEmik/QualiDock/pull/44/files).
Production code (`backend/qualidock` and `frontend/src`) changes by
**+581 /−29, net+552 lines** on application commit `afa771f`.

Added application files: `backend/qualidock/variant.py`,
`frontend/src/VariantResults.tsx`, `VariantSettings.tsx`, `variantChart.ts`.
Added validation files: `backend/tests/test_variant_inputs.py`,
`test_variant_stats.py`, `test_variant_real.py`, `test_variant_multiqc.py`,
`test_benchmark_variant.py`; `frontend/tests/variant.test.ts`;
`tests/browser/test_variant_browser.py`; `scripts/prepare-variant-test.py`,
`qualify-bcftools.py`, `setup-variant-ci.sh`; this document and the93 fixtures.

Modified backend application files: `app.py`, `config.py`, `files.py`,
`history.py`, `import_formats.py`, `manager.py`, `multiqc.py`, `optional_qc.py`,
`tools.py`. Modified frontend application files: `AnalysisDetail.tsx`,
`App.tsx`, `FileExplorer.tsx`, `NewAnalysisForm.tsx`, `OptionalQcResults.tsx`,
`ResultsList.tsx`, `api.ts`, `explorer.ts`, `types.ts`. Remaining modified files:
`.github/workflows/ci.yml`, `README.md`, `docs/BENCHMARKING.md`,
`docs/OPTIONAL-QC.md`, `scripts/benchmark-analysis.py`,
`scripts/linux-validation.Dockerfile`, `scripts/validate-linux-execution.py`.
The final acceptance entry also updates `docs/VALIDATION.md`.

RunManager gains only input/configuration and artifact routing; it retains the
single lifecycle/resource slot. NewAnalysisForm delegates the focused variant
settings. Existing four primary navigation areas and report sandbox remain.
