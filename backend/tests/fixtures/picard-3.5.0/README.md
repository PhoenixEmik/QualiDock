# Genuine Picard CollectInsertSizeMetrics 3.5.0

Original unmodified reports from CI 39018972918, artifact `picard-tool-study`.
Official 3.5.0 JAR SHA-256:
`b7d97861c3a54ba5a421f5a317f38382f955803862d30ef4aca2bcdc54943631`.
The JAR is a test-tool artifact, **not** a repository/runtime dependency.
Java17.0.20.1, R4.3.3. Probe metadata records real `--version`/`--help` exits1;
these do not run an analysis. Genuine scientific commands exit0.

Explicit synthetic DNA-like alignment geometry in `paired.sam`, reproduced by
`scripts/prepare-insert-test.py`: FR spans150/250/350, RF200/300, TANDEM400.
One duplicate pair is excluded by the original default policy; a single-end
record contributes no insert observation. No biological library is inferred.

Original FR median/mean250, SD100; RF median/mean250, SD70.710678. TANDEM has one
observation and the actual standard deviation is `?`, **not zero**. Blank
sample/library/read-group fields identify ALL_READS metrics. All histogram
values and PDF bytes remain original; no application calculation generated them.

Single-end-only input produces exit0 with an explicit zero-observation warning,
and **no metrics or histogram file**. Preserve that distinction. Command and
temporary paths in the original metric header/diagnostics are hosted-runner paths.
MINIMUM_PCT0.05 / DEVIATIONS10 / INCLUDE_DUPLICATES=false / ALL_READS,
ASSUME_SORTED=false / VALIDATION_STRINGENCY=STRICT, no source/index writing.
Mean/SD/histogram use the upstream tail cutoff; READ_PAIRS can describe a larger
untrimmed population. This tiny fixture does not establish large-BAM performance.
