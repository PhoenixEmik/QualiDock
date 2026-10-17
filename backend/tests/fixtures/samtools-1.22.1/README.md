# SAMtools 1.22.1 fixture

`input.sam` and `reference.fa` are deliberately synthetic, independently readable
small alignment inputs. They contain eight records: one proper read pair (2),
secondary (1), supplementary (1), duplicate primary (1), QC-failed primary (1),
single mapped primary (1), and unmapped primary (1). chr1 is 100 A bases, chr2 is
50 C bases. No actual sequencing data or biological inference is implied.

`flagstat.txt` and `stats.txt` are untouched genuine SAMtools 1.22.1 / HTSlib
1.22.1 outputs generated locally using the test-only BAM at
`/private/tmp/qualidock-alignment.bam`. Full stdout including the original command
line is retained. Expected primary segments: 6; mapped primary segments: 5;
flagstat QC-passed/failed total segments: 7/1. SAMtools stats reports total length
40, excluding secondary/supplementary. Categories overlap; counts are not pairs.

Reproduce BAM/CRAM and the existing reference .fai explicitly with
`scripts/prepare-alignment-test.py --output /tmp/alignment-fixture --samtools …`.
This test utility creates files only in its requested destination. QualiDock
never performs conversions, builds indexes, or modifies reference/input files.
