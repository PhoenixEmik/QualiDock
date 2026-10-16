# Test datasets

Prepare a compact development suite without changing existing pilot inputs:

```sh
python3 scripts/prepare-test-data.py
# Optional, ~13 MB download; no QC/preprocessing software is installed:
python3 scripts/prepare-test-data.py --download-public
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

## Reproducibility and validation

Existing files with different bytes are rejected. Repeating the same command is
safe; to change `--reads`, choose a new `--output` directory. Larger synthetic
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
