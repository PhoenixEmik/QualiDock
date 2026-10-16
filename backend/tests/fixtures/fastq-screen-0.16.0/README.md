# Actual FastQ Screen 0.16.0 / Bowtie2 reference fixture

`alpha.fasta`, `beta.fasta` and `reads.fastq.gz` are explicitly **synthetic DNA**.
Two independent 2,000-nt reference strings were generated with Python
`random.Random(8421).choices('ACGT', k=2000)`. Reads 0–11 are 100-nt alpha segments
at `i*30`; reads 12–17 are beta segments at `i*30`; reads 18–19 contain 100 Ns.
All qualities are `I`. There are 20 independent reads, not a paired library.
No human, clinical or experimental-organism sample interpretation is intended.

`reads_screen.txt` is untouched output from **real FastQ Screen 0.16.0** and
**real Bowtie2 2.5.4**, using `--aligner bowtie2 --subset 10 --threads 1`.
There are 12 alpha-only, six beta-only and two no-hit reads. All 20 reads are
processed: upstream does not subset files containing at most twice the target.

Indexes are intentionally not committed. Test code explicitly runs
`scripts/prepare-screen-test.py` with the actual bowtie2-build to create temporary
indexes. The application itself never builds or downloads references. Tests
verify original output bytes, actual mappings, failures and provenance, rather
than mocking a successful screening command. Tests that corrupt an index must
fail even though upstream FastQ Screen can otherwise exit zero.
