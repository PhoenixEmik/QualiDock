# Public Galaxy/RSeQC RNA-seq subset

Source: Galaxy tools-iuc, pinned commit
`9952aaab7511f7c8475aa9a6e068e3b8d973cfef`, `tools/rseqc/test-data/`:
https://github.com/galaxyproject/tools-iuc/tree/9952aaab7511f7c8475aa9a6e068e3b8d973cfef/tools/rseqc/test-data

This is the existing small hg19 RNA-seq subset used by the Galaxy RSeQC wrapper,
not generated biological evidence. No BAM, annotation or report bytes were
modified. Local names only:

| Local | Upstream | SHA-256 |
| --- | --- | --- |
| input.bam | pairend_strandspecific_51mer_hg19_chr1_1-100000.bam | d8e67748861c72119faa7cb02f583cd8c9f315026be0e0aa201908ea2cbf725c |
| genes.bed12 | hg19_RefSeq_chr1_1-100000.bed | 973aa97ac8813b7f94996c97aa1edb5c4f1b1b7b21f1c05e591a4d0c4fefaa27 |
| upstream.infer_experiment.txt | output.infer_experiment.txt | 2a999e2c08e2bf3ccc99fabfeeb2f76dddf7a910dec0e4c970fd3d608f9c9463 |
| upstream.read_distribution.txt | output.read_distribution.txt | 2f7b39459e25f19ab665b14f0aeb7a80b65bb1ac869f337223512b75039f162d |

3449-byte BAM, 40 primary alignment records, seven BED12 transcripts. Original
Galaxy strandedness fractions are 1.0000/0.0000/0.0000 (pattern1/pattern2/failed).
Distribution reports 40 reads, 44 tags, 38 assigned tags. New real-tool tests
independently execute RSeQC 5.0.5 and compare the app's exact stdout and native
values, with before/after source SHA-256. The older committed upstream report is
an independent regression reference; no old tool version is claimed supported.
This tiny selected region does not establish sample-wide protocol accuracy,
representative library characteristics, or large-input performance.
