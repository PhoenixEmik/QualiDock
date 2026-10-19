# Genuine RSeQC gene-body output

Unmodified files from PR #36, commit `2993b619bcfec087b2a2a5c0626fefa48e60c2df`,
accepted CI run 39185806278, artifact `rna-gene-body-tool-study` (ID 12157269418).
The existing `scripts/qualify-rseqc-genebody.py` creates a test-owned indexed copy
of `scripts/prepare-rna-test.py`'s explicitly synthetic RNA geometry.
`qualification.json` records command, input/annotation SHA-256 and original table
SHA-256. No reports were fabricated for production. The original table has 100
values and maximum 2; the original R script min-max-normalizes it to maximum 1.
Original PNG is preserved in the CI artifact; numerical fixtures stay textual.
