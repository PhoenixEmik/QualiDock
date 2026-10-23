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
PSC `0.0` average depth is not evidence of measured zero depth. Missing/unknown
AF and singletons share a default bin; AF is not a native biological estimate.
Original values remain available for inspection with their upstream meanings.

## Acceptance status

Tool/input and independent upstream qualification complete locally:18 formats/
cases,36 native invocations;78 input/security/alignment unit regressions passed.
Application execution, native parser/interface, MultiQC, full CI, both browsers
and benchmark integration remain in development. Do not close #43 on these
small fixtures or missing-tool skips. Large/shared-storage acceptance stays #5.
