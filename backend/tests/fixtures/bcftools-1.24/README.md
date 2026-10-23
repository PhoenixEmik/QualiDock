# Genuine BCFtools 1.24 / HTSlib 1.24 reports

Generated independently by `scripts/qualify-bcftools.py` after security #41 was
accepted and merged in #42. `prepare-variant-test.py` defines explicit synthetic
VCF records; scientific output is produced only by the authentic native binary.
The official source-asset SHA-256 is
`8caddc22610ee2851666047c859bb91da0c1e32d0c2ec553db6f153ad130e46f`.
The local build uses the release-bundled HTSlib 1.24; CI records binary/static
library hashes and linking independently. No production tools are installed.

`provenance.json` retains every exact argv, report/source hash, version, format
and exit code. Original stdout/stderr are unchanged. Thirty-six independent
executions cover 18 input/encoding cases. `-s -` legitimately exits 255 when
there are no sample columns; those empty stdout/diagnostic fixtures are not
successful QC reports. QualiDock rejects that request before execution.

Whole-file stats needs no index for these VCF 4.2/4.3, ordinary gzip/BGZF VCF,
BCF 2.2 encodings. `-Ou` still produces level-zero BGZF; `raw-bcf.bcf` is actual
unwrapped BCF. All mixed-population report data sections agree across encodings;
multisample VCF/BGZF/BCF agree separately. Sources remain unchanged and no
TBI/CSI index is created. Conversions occur only in this test generator.

Important genuine observations: the six-row mixed population has two SNP rows,
two indel rows, one MNP row and one no-ALT row; a SNP+indel multiallelic record
increments both counters. Three symbolic/breakend/star rows do not become three
`others`: only one does. A two-row gVCF including a 20-position reference block
remains two records, with one no-ALT row; these counters are not genome coverage.
Missing QUAL remains `.`. With no depth, DP has no rows but PSC average depth is
printed as `0.0`. With no transversions, the original Ti/Tv is `0.00`; that is
not a defined ratio. Missing/unknown AF and singletons share the upstream zero
bin. No biological protocol, trustworthy genotype call or AF denominator is
inferred from these tiny fixtures.
