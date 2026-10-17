# Genuine mosdepth 0.3.14 reports

Untouched original output from mosdepth 0.3.14, compiled from the official tag
with `--mm:refc` / Nim 2.2.12 / hts-nim 0.3.31 / HTSlib 1.22.1 on macOS arm64.
No tool source/scientific calculation was patched. Linux CI independently runs
the official static release (published SHA-256 checked).

Input: the explicit eight-record synthetic SAM and 150-base reference in
`../samtools-1.22.1`, converted/indexed by the test-only fixture utility. Command:

```
MOSDEPTH_PRECISION=5 mosdepth --no-per-base --threads 0 --by panel.bed \
  --thresholds 1,10,20,30 --flag 1796 --mapq 0 coverage input.bam
```

Independent expectation: the overlapping proper pair covers chr1 positions 1–15
once (15 bases), supplementary covers 21–25 (5), single covers 51–55 (5).
Default mask excludes secondary, QC-failed, duplicate and unmapped records.
The original reported chr1 total is length 100, cumulative depth 25, mean 0.25.

**Important genuine upstream behavior:** chr2 has no alignment records; it is
omitted from summary/global CDF totals. Header length is 150, reported global
length is 100. BED contains 40 positions, but regional summary/CDF length is 30;
chr2's individual interval still reports original zero coverage/counts. Do not
substitute 150 or 40 into these reported fractions. Tests explicitly preserve
this distinction. Source/golden reports must not be rewritten to fill zeros.

Original regional CSI files are report indexes, not source alignment indexes.
No per-base file is generated. Statistics are synthetic-fixture observations,
not biological sample metrics or representative large-BAM performance evidence.
