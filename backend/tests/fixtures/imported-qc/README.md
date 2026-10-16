# Genuine imported QC fixtures

Unmodified fastp outputs from the MIT-licensed [MultiQC test-data repository](https://github.com/MultiQC/test-data), pinned at `ae5e10025fa1b0fd6792f8f2b513e160d78474fe`. Downloaded 2026-10-16. These are reported results, not tools or generated scientific substitutes. Commands and source paths inside the original public reports are inert upstream metadata.

| Local file | Upstream path | SHA-256 |
| --- | --- | --- |
| `fastp/SAMPLE.json` | [`data/modules/fastp/SAMPLE.json`](https://github.com/MultiQC/test-data/blob/ae5e10025fa1b0fd6792f8f2b513e160d78474fe/data/modules/fastp/SAMPLE.json) | `29adfbd037e75ec7f9ef823ed1b2c0c6a45ffeb9872e4239f23782a6f4b4dbde` |
| `fastp/fastp.json` | [`data/modules/fastp/repo_example/fastp.json`](https://github.com/MultiQC/test-data/blob/ae5e10025fa1b0fd6792f8f2b513e160d78474fe/data/modules/fastp/repo_example/fastp.json) | `b8dcf72c609833c62dd53a7f024ab651feca03080eac90d64fde1be4c2e32ed2` |
| `fastp/HG001.fastp.json` | [`data/modules/fastp/issue_2138/HG001.fastp.json`](https://github.com/MultiQC/test-data/blob/ae5e10025fa1b0fd6792f8f2b513e160d78474fe/data/modules/fastp/issue_2138/HG001.fastp.json) | `d0aebd21831c6df3a27dfa69f8fc62526a56cae859f974d7fcfc815a94a0b320` |
| `fastp/single.fastp.json` | [`data/modules/fastp/single_end/fastp.json`](https://github.com/MultiQC/test-data/blob/ae5e10025fa1b0fd6792f8f2b513e160d78474fe/data/modules/fastp/single_end/fastp.json) | `a09d093304fa79d84deaed6c0cf1166cdb43ceecd17879f6c85e30966e504e84` |

HG001 reports fastp 0.23.4. Older paired- and single-end outputs do not report a version; QualiDock leaves it unavailable. Preserve original before/after-filtering counts, not an inferred raw-FASTQ mapping.
