# Genuine NanoPlot 1.48.0 NanoStats

Untouched NanoStats from the existing public ONT fixture
`../nanoq-0.10.0/ont.fastq.gz` (20 reads, 26,248 bases; provenance/license there).
No generated biological values or modified read records.

```sh
NanoPlot --fastq ../nanoq-0.10.0/ont.fastq.gz --outdir output --threads 1 \
  --tsv_stats --plots dot --format png --no_static --include-js embedded --only-report
```

NanoPlot 1.48.0, nanoget 1.19.6, NumPy 2.2.6, pandas 2.2.3, Plotly 6.1.2.
The default report embeds JavaScript. `--no_static` avoids Plotly's Chrome
download/export path. Omitting `--only-report` preserves additional original interactive HTML plots.
PNG export is deliberately unavailable: the modern static path can download
Chrome and the legacy path fails with modern seaborn. Neither is offered. Full HTML is generated and retained by genuine-tool tests/CI,
not checked into Git as a multi-megabyte vendored JavaScript bundle.
