# Genuine RSeQC 5.0.5 (CLI 5.05)

Untouched stdout/stderr and dependency evidence from the actual PyPI release,
executed on Linux in CI 39016787188 (`rna-tool-study`). Input SAM/BED12 are
explicit **synthetic alignment geometry**, not a biological RNA-seq sample.
`scripts/prepare-rna-test.py` reproduces the source. No application-generated
scientific values or patched upstream algorithms are used.

Ten paired alignment records contain six orientation-pattern-1 records, two
pattern-2 records, and two overlapping opposite-strand-gene ambiguous records.
Expected infer_experiment fractions: 0.6000, 0.2000, 0.2000 respectively. These
are sampled annotation-overlapping alignment records, not independent fragments
or a proof of the biological library protocol.

One record spans two exons; ten accepted records therefore contribute eleven
aligned blocks. Seven midpoints fall in CDS exons and four in introns. Original
Tags/Kb uses upstream's `bases + 1` denominator and rounding; no values are
recomputed for the UI. Nested TSS/TES rows must not be added.

Commands: `infer_experiment.py -i input.bam -r genes.bed12 -s 200000 -q 30`
and `read_distribution.py -i input.bam -r genes.bed12`. Only the test fixture
generator converts SAM to BAM; the application never rewrites source alignments.
Paths in diagnostic files are original hosted-runner paths. This small fixture
does not establish large-RNA-seq memory/I/O performance or protocol accuracy.
