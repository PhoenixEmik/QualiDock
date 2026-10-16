# Genuine Illumina BCL Convert evidence

Unmodified public tool reports from the MIT-licensed [MultiQC test-data repository](https://github.com/MultiQC/test-data), pinned at `ae5e10025fa1b0fd6792f8f2b513e160d78474fe`, downloaded 2026-10-16. The upstream fixture directories identify BCL Convert 3.6.3 / 3.9.3; the CSV documents themselves do not report a tool version. No FASTQs are supplied or fabricated by these reports.

| Local file | Upstream file | SHA-256 |
| --- | --- | --- |
| `3.6.3/Demultiplex_Stats.csv` | [`data/modules/bclconvert/3.6.3/single_bclconvert_run/Demultiplex_Stats.csv`](https://github.com/MultiQC/test-data/blob/ae5e10025fa1b0fd6792f8f2b513e160d78474fe/data/modules/bclconvert/3.6.3/single_bclconvert_run/Demultiplex_Stats.csv) | `e784ce8509741e1a5ce61e8ae09695c05a822deb8e5d7aed299922a78bd8250a` |
| `Demultiplex_Stats.csv` | [`data/modules/bclconvert/3.9.3/Demultiplex_Stats.csv`](https://github.com/MultiQC/test-data/blob/ae5e10025fa1b0fd6792f8f2b513e160d78474fe/data/modules/bclconvert/3.9.3/Demultiplex_Stats.csv) | `645daebdd9acc47b0819a1042481170ff408077c3b3dcbbd78e342a7f885d64f` |
| `Index_Hopping_Counts.csv` | [`data/modules/bclconvert/3.9.3/Index_Hopping_Counts.csv`](https://github.com/MultiQC/test-data/blob/ae5e10025fa1b0fd6792f8f2b513e160d78474fe/data/modules/bclconvert/3.9.3/Index_Hopping_Counts.csv) | `11aa7fa1c0e2867b808f574c7265c7b7587b54fce6d2142ad39ceadb1769f417` |
| `Quality_Metrics.csv` | [`data/modules/bclconvert/3.9.3/Quality_Metrics.csv`](https://github.com/MultiQC/test-data/blob/ae5e10025fa1b0fd6792f8f2b513e160d78474fe/data/modules/bclconvert/3.9.3/Quality_Metrics.csv) | `fe9b231e95f93c78f4f3e6c5ce023e14febaaee4f9c3babdaa20fd525e183cdb` |
| `SampleSheet.csv` | [`data/modules/bclconvert/3.9.3/SampleSheet.csv`](https://github.com/MultiQC/test-data/blob/ae5e10025fa1b0fd6792f8f2b513e160d78474fe/data/modules/bclconvert/3.9.3/SampleSheet.csv) | `462b9e60e988fc659d3f79a60dc219199531913eaa9bfbae781bb9a5c893b609` |
| `fastq_list.csv` | [`data/modules/bclconvert/3.9.3/fastq_list.csv`](https://github.com/MultiQC/test-data/blob/ae5e10025fa1b0fd6792f8f2b513e160d78474fe/data/modules/bclconvert/3.9.3/fastq_list.csv) | `f657743260c4ece553627d7c3d3d192b60a9462274c35582e03e6b7b60fd387b` |

The paired-end 3.9.3 fixture has distinct read lengths (reported in Quality_Metrics), so demultiplex PF-read observations must not be added as R1+R2 source-record totals. Index hopping percentage cells are blank: these are unavailable, not zero. The adapter retains the upstream bytes and reported numeric text.
