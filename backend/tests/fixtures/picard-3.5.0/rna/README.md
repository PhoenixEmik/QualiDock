# Original Picard 3.5.0 CollectRnaSeqMetrics qualification output

Synthetic data only. Files were generated with the original SHA-256-pinned JAR,
Java 17.0.20.1 and SAMtools/HTSlib 1.22.1 on macOS, using
`scripts/qualify-picard-rna.py`. No scientific output was rewritten. The
`sha256.json` manifest protects the committed bytes. Paths/timestamps in original
headers identify only isolated synthetic test storage.

`input.sam`, `genes.refFlat` and `rrna.interval_list` are the category fixture:
seven PF reads of 50 bases including one unmapped; six mapped PF alignments;
one additional QC-failed alignment is excluded. Independent aligned-base counts:
100 coding, 50 UTR, 50 intronic, 100 intergenic. With the explicit rRNA annotation,
50 formerly intergenic bases become ribosomal. No interval file gives blank
rRNA metrics, not a biological zero.

Uniform and biased plus/minus profiles are generated independently by the study;
these use explicit exon-boundary overhangs and known transcript coverage.
`boundary-spliced` instead exercises the 3.5.0 end-exclusive coverage-counter
limitation, not a claim of no biological bias. ALL_READS and LIBRARY are distinct,
overlapping populations in `by-library`, never independent samples.

Reproduce with the documented qualification command in
[the study report](../../../../../docs/PICARD-RNA-QUALIFICATION.md).
Full BAMs, original PDF, stdout/stderr, argv/exit/resource evidence and original
MultiQC JSON/HTML belong to CI artifacts, not production fixtures. These small
fixtures establish no large-input or shared-filesystem performance acceptance.
