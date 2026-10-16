# Test datasets

Prepare a compact development suite without changing existing pilot inputs:

```sh
python3 scripts/prepare-test-data.py
# Optional, ~13 MB download; no QC/preprocessing software is installed:
python3 scripts/prepare-test-data.py --download-public
# Additional pinned upstream fixtures, ~42 MB (independent of --download-public):
python3 scripts/prepare-test-data.py --download-extra
```

The default destination is `example-data/testing`, inside the application's default
input root. In Workspace, Refresh and open `testing`, then choose a scenario folder.
Run **FastQC + MultiQC** and inspect QC Overview, Sample Details, Compare Samples,
and Reports. Do not select every scenario as one biological cohort.

| Folder | Files | Purpose |
|---|---:|---|
| `synthetic-multilane` | 14 | Two artificial samples, three lanes each, an extra C15 chunk |
| `synthetic-qc-profiles` | 8 | Four artificial pairs: high quality, declining tail quality, adapters, GC/N/duplication stress |
| `synthetic-manual-pairing` | 2 | Nonstandard names with spaces; assign forward as R1, reverse as R2 |
| `synthetic-pairing-edges` | 5 | Single-end, missing R2, duplicate R1 naming candidates |
| `synthetic-cohort` | 24 | Twelve artificial pairs for shared selection, sorting, heatmap and overlays |
| `public-yeast-rnaseq` | 6 | Three experimental yeast RNA-seq paired-end subsets, 50,000 reads per file |
| `public-miseq-amplicon` | 2 | MiSeq v2 amplicon subset; noncanonical mate IDs, see below |
| `public-novaseq-amplicon` | 2 | NovaSeq amplicon subset with binned qualities; verified paired identifiers |
| `public-nanopore-16s` | 1 | Previously filtered Nanopore 16S mock-community reads, variable lengths |
| `public-bacteroides` | 2 | **Upstream simulated** bacterial genomic reads; verified paired identifiers |
| `public-smallrna` | 1 | Single-end small-RNA pipeline input; original study is not documented |

Synthetic inputs have 2,000 reads per file by default. All QC classifications are
computed by the real installed FastQC; the generator never writes scientific
results or assigns expected PASS/WARN/FAIL labels. Profile names describe injected
test patterns, not biological interpretation or a promise of particular statuses.
Lane/chunk groups are organizational fixtures; no concatenation is performed.

For the ambiguous naming case, `ambiguous_R1_001` and `ambiguous_1_001` both look
like R1 for `ambiguous_R2_001`; the application should leave them unpaired. The
missing-mate file should remain analyzable independently. In the multi-lane folder,
C15 has eight reads / four lane-chunk pairs; D20 has six / three pairs.

## Public data provenance

The six public FASTQs are unmodified files from
[nf-core/test-datasets](https://github.com/nf-core/test-datasets/tree/cad884e7fbe5617dcd55bdd07d9ddf65b54febe4/testdata/GSE110004),
pinned to commit `cad884e7fbe5617dcd55bdd07d9ddf65b54febe4`.
The upstream [README](https://github.com/nf-core/test-datasets/blob/cad884e7fbe5617dcd55bdd07d9ddf65b54febe4/README.md)
documents the S. cerevisiae 101 bp strand-specific RNA-seq study and its preparation:
reads were selected against chromosome I and then subsampled upstream. These are
experimental read subsets, **not untouched full-run datasets or unbiased
library-wide QC samples**.

- SRR6357070: wild-type total RNA-seq biological replicate 1.
- SRR6357071: wild-type total RNA-seq biological replicate 2.
- SRR6357076: Rap1-AID, induction 30 minutes, biological replicate 1.

This is a test panel with two conditions, not a balanced study design. Original
upstream filenames, read headers, qualities and gzip bytes are retained. Source
documentation and the upstream MIT license are saved alongside the downloads.
`scripts/test-data-sources.json` pins byte counts, SHA-256 and upstream Git blob
identities; preparation verifies SHA-256 before accepting files. The generated
`manifest.json` records local inputs and explicitly distinguishes synthetic data
from public experimental subsets. No bulk SRA/ENA run downloads are required.

## Additional upstream fixtures

The extra download is **8 unmodified gzip files, 41,916,630 bytes**, pinned to
nf-core/test-datasets commits in `scripts/test-data-sources.json`. All counts and
length ranges below were measured by full-file validation, not inferred from names.

| Folder | Records per file | Length (nt) | Useful tests |
|---|---:|---|---|
| `public-miseq-amplicon` | 2,500 | 35–250 | Variable-length FastQC, amplicon composition, pairing rejection |
| `public-novaseq-amplicon` | 3,000 | R1: 228; R2: 229 | Paired filtering/sampling, binned qualities, R1/R2 charts |
| `public-nanopore-16s` | 1,000 | 229–3,173 | Inspector, SeqKit stats and length filtering, variable-length QC |
| `public-bacteroides` | 24,993 | 151 | Simulated paired processing, exact-count sampling, derived reuse |
| `public-smallrna` | 1,000,000 | 150 | Single-end processing and a modest million-record smoke workload |

Sources and limitations:

- [ampliseq fixtures](https://github.com/nf-core/test-datasets/tree/3cc618ea14e87fd944c30dd37acbef08ad01d590):
  MiSeq `1_S103_L001_R{1,2}_001.fastq.gz`, NovaSeq `novaseq1.r{1,2}.fq.gz`, and
  Nanopore `Std1_ZymoD6305_…chopper.1000.fastq.gz`. The upstream README identifies
  the Nanopore data as Zymo D6305 mock community, SUP v4.3.0 basecalling, already
  filtered with Chopper `-q 16`, then limited to the first 1,000 reads. This is not
  an unfiltered long-read library; short-read fastp defaults are not an ONT protocol.
- **MiSeq is not a confirmed pair under QualiDock's current identifier rules.**
  Its first-token IDs end in `.1` and `.2`; QualiDock deliberately normalizes only
  conventional `/1` and `/2`. Full validation rejects the mate relationship even
  though counts match. Use separate-file QC or independent processing. Manual
  assignment does not bypass validation. Original headers are never rewritten.
- [modules fixtures](https://github.com/nf-core/test-datasets/tree/76179c1c8765b0233ba72d3fb82bc142f1d92b13/data/genomics/prokaryotes/bacteroides_fragilis/illumina/fastq):
  `test2_{1,2}.fastq.gz` are **synthetic genomic reads**, as explicitly documented
  upstream. Do not describe them as experimental bacterial sequencing.
- [smrnaseq fixture](https://github.com/nf-core/test-datasets/tree/d5a0422243620ef4e32c19812ab12edb5dfc882e/testdata):
  `sample_1.fastq.gz` is used as one independent input. The selected upstream
  README does not document its study/accession; no condition, species or biological
  pairing is asserted. The 150-nt sequenced length is not the RNA insert length.

Each folder includes the pinned upstream README and repository MIT license.
Retain these notices; the repository license alone does not establish any
undocumented original-study licensing or provenance. These are development
fixtures, not a coherent biological cohort or unbiased study panel.

Local preparation on 2026-10-17 verified upstream Git blob identity, SHA-256,
gzip CRC, complete FASTQ structure, read counts and length ranges for all eight
files. The NovaSeq and simulated bacterial pairs also passed full ordered,
normalized identifier comparison. MiSeq failed that check as expected. Local
details are in the ignored `example-data/testing/additional-validation.json`.
FastQC 0.13.0 successfully processed all eight inputs; native parsing matched each
validated read count. MultiQC 1.35 aggregated all eight reports, and native General
Statistics parsing returned eight rows. Post-QC SHA-256 checks confirmed unchanged
source files. Local reports are under `validation/sample-data-20261017/`.
This is small/local test evidence, **not large-FASTQ or NFS/Lustre acceptance**.

## Reproducibility and validation

Existing files with different bytes are rejected. Repeating the same command is
safe with the same Python/compression runtime; byte-identical synthetic gzip
regeneration across Python/zlib versions is not promised. Existing mismatches are
rejected rather than overwritten. To change `--reads`, choose a new `--output` directory. Larger synthetic
inputs can be prepared up to 100,000 reads/file. An output outside configured input
roots needs to be added to `QUALIDOCK_ROOTS` before browsing it.

```sh
# Actual tools, exact metric parsing, reports, immutable inputs and restart:
QUALIDOCK_MULTIQC=/absolute/path/to/multiqc .venv/bin/python \
  scripts/smoke-real-qc.py --input-root example-data/testing/public-yeast-rnaseq
```

The existing smoke test chooses the first pair and removes only its own temporary
results. Use the normal UI to retain analyses of all six public files or the
24-read synthetic cohort. Downloads, generated FASTQs, provenance manifests and
local validation reports stay git-ignored under `example-data/` and `validation/`;
only the preparation utility, pinned source inventory and documentation are tracked.
