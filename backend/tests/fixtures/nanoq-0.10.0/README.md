# Genuine nanoq 0.10.0 fixture

`ont.fastq.gz` contains the first 20 complete, unchanged records of the pinned
nf-core ampliseq Nanopore Zymo D6305 fixture documented in
[TEST-DATA.md](../../../../docs/TEST-DATA.md). Original compressed source SHA-256:
`cf53d784b470dec4553829ea1baa5796c6f84fa6ddf011b1437d23ef8b917f4c`.
Record sequence/header/quality bytes are preserved; only the subset gzip container
was newly created (mtime 0). Subset SHA-256:
`3ccf3f9b6694529c90e0ce1bc15ec4524d7474ca4cb1c230c0628698689bcb67`.
The upstream MIT notice is retained in LICENSE. Original data were already
Chopper-filtered upstream; this is not an unbiased raw ONT library.

`nanoq.json` is untouched output from the actual 0.10.0 executable:

```sh
nanoq --stats --json --input ont.fastq.gz --report nanoq.json
```

Local executable was built from the published nanoq 0.10.0 crate and its verified
locked dependencies on macOS arm64; Linux CI uses the pinned upstream musl binary.
No synthetic scientific statistics or read identifiers are written into reports.
