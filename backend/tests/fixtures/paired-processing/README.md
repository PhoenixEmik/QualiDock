# Independent exact-count reference (test metadata only)

`exact-sampling.json` contains record indices, not scientific QC measurements.
They were computed with standard Go 1.23.2 by `reference-sampling.go`, independently
of the SeqKit executable and QualiDock's wrapper. The standard fixed-size reservoir
algorithm samples each N-element subset with probability 1 / choose(total, N).
Sorted selected indices preserve input order and contain no repeated positions.
The reference uses Go's seeded `math/rand` because the verified SeqKit 2.14.0
[sample2 source](https://github.com/shenwei356/seqkit/blob/v2.14.0/seqkit/cmd/sample2.go)
uses that PRNG. Tests compare actual FASTQ record bytes at these indices, for both
single/paired inputs, then check reproducibility, full-count and over-count cases.
The existing 400-record FastQC fixture supplies the actual records.

Reproduce with `go run reference-sampling.go > exact-sampling.json`. Go is not an
application dependency and is not required to run automated fixture comparisons.
