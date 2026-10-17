# Falco 2.0.3 evaluation — issue #30

**Decision: do not add a Falco execution engine in this phase.** FastQC remains
the application default and the only FastQC-style native engine. The existing
benchmark can qualify Falco; it is deliberately absent from `/api/config` and
analysis modes. No partial engine integration, alternative chart framework or
report rewriting is retained.

## Measured benefit and correctness gate

Actual Falco 2.0.3 is substantially faster and uses less memory than FastQC
0.13.0 in these local tests. However, it accepts an input whose separator is `?`
instead of `+`, exits zero and writes a QC report. FastQC rejects that same file
and produces no QC ZIP. Both tools leave source bytes unchanged. The existing
QualiDock full structural validator correctly rejects the malformed input.

Supporting this Falco version without silently accepting such inputs would
require additional structural validation. On the tested million-read workload,
that cost eliminates the processing-time advantage with the current shared
validator. We will not bypass validation, introduce a second FASTQ validator or
start another scanner optimization project merely to add a QC engine.

macOS arm64 observations, one CPU thread, three repetitions, alternating native
engine order, unchanged input SHA-256 before/after:

| Input | Reads | Compressed bytes | FastQC median (s) | Falco median (s) | Full validation median (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Genuine existing coverage fixture | 400 | 52,290 | 2.492 | 0.016 | 0.056 |
| Pinned NovaSeq amplicon subset | 3,000 | 156,758 | 2.478 | 0.021 | 0.109 |
| Pinned nf-core million-read test input | 1,000,000 | 36,417,994 | 5.506 | 0.824 | 16.174 |

These values are from the local alternating benchmark under
`validation/falco-evaluation-macos-validation/`. A separate genuine regression run
measured **17.588 s for the consecutive full-validation → Falco command pair**
on the million-read input, compared with a 5.504 s FastQC median in that run. This
is a measured benchmark command sequence, **not an implemented application Falco
workflow**. The faster isolated Falco command is not presented as an application
speedup. Small inputs benefit from avoiding JVM startup; the medium input exposes
the validation cost relevant to the intended larger FASTQ workflow.

In the alternating benchmark, million-read median waited-child high-water RSS
was **366.28 MiB FastQC**, **20.83 MiB Falco**, and **20.77 MiB validation**.
This is kernel `wait4` high-water accounting for each command and its waited
descendants, not simultaneous process-tree peak or a memory-limit acceptance
claim. The managed macOS environment denies `ps`; the test-only portable observer
used for local measurements cannot validate process-tree RSS enforcement. Actual
tool execution and `wait4` CPU/RSS/block counters were retained. Production
LocalExecutor enforcement is unchanged and Linux CI uses its actual observer.

The Linux Actions evaluation independently confirms the gate on the same
1,000,000-read, 36,417,994-byte input (one requested thread, three repetitions):

| Command | Median wall (s) | Median CPU (s) | Median waited high-water RSS (MiB) |
| --- | ---: | ---: | ---: |
| FastQC 0.13.0 | 7.253 | 6.336 | 193.13 |
| Falco 2.0.3 | 0.992 | 0.991 | 21.97 |
| Full structural/gzip/SHA validation | 24.819 | 24.797 | 18.51 |

The consecutive validation → Falco command pair took **26.387 s**. Linux also
reproduced Falco accepting the malformed separator, while independent validation
failed and FastQC produced no ZIP. Source SHA-256 was unchanged. These are hosted
runner observations with uncontrolled cache and shared hardware, not a controlled
large-file benchmark. Raw isolated-tool speed and memory benefits are real, but
the validated path does not justify another engine under the current contract.

Both tools' local kernel block-I/O counts were zero with uncontrolled cache.
That does **not** mean no reads occurred. Linux `/proc` observations are preserved
without summing parent/child counters. No physical-byte throughput, cold-cache,
NFS/Lustre or representative multi-gigabyte performance is claimed. Issue #5
remains separate and open.

## Scientific and integration differences

- Genuine Falco v2 data starts with `##Falco 2.0.3`, rather than `##FastQC`.
  The current native parser intentionally remains unchanged. Supporting a similar
  table layout would still require explicit engine attribution and compatibility
  tests; renaming a header would not establish scientific equivalence.
- Falco produces extracted `fastqc_data.txt`, `summary.txt` and
  `fastqc_report.html`, not FastQC ZIPs. Original files were not modified.
- The benchmark explicitly uses Falco `--groups`; upstream documents that this
  affects grading. Per-tile classifications differed on the NovaSeq fixture;
  overrepresented-sequence classifications differed on all three inputs. Original
  statuses and raw Basic Statistics strings are retained in the evidence.
- GC and base totals use different output precision/formatting (e.g. `47` versus
  `47.8`, `60 kbp` versus `60020`). These are not silently normalized or presented
  as identical reported values.
- Upstream v2 changes duplication sampling and documents tile-sampling variability;
  matching module names do not establish identical statistics. See the
  [upstream v2 documentation](https://github.com/smithlabcode/falco#changes-in-falco-v20).
- Actual MultiQC **1.25.1 and 1.35** consumed three unchanged Falco reports and
  produced three General Statistics rows with exact report-source mappings.
  This verifies standalone format compatibility, not equality with FastQC's
  statistics. No QualiDock Falco execution/native-engine compatibility is claimed:
  the integration did not pass the practical correctness/performance gate.

## Reproduction and regression

```sh
python scripts/benchmark-analysis.py \
  --input /authorized/input.fastq.gz \
  --output /new/private/falco-evaluation \
  --mode fastqc --evaluate-falco /path/to/falco \
  --threads 1 --repeats 3 --hash-inputs
```

The output must be new. One existing LocalExecutor runs the commands sequentially
under the usual guardian and resource limits. Each repetition records the actual
full validator, FastQC and Falco separately, exact argv/version/source metadata,
original reports, wall/CPU/kernel RSS/block counters and available Linux process
I/O. The small measurement wrapper uses `fork`/`wait4` only for private benchmark
accounting; it is not an execution service or application job manager.

Genuine tests cover the small fixture, pinned million-read input, original-source
immutability, actual report/count differences, the malformed-separator behavior,
and intentional absence of an application Falco mode. Test tooling explicitly
downloads the pinned Linux binary and public input; the application installs
nothing. Linux measurements and original reports are retained in the
`falco-engine-evaluation` artifact of
[CI run 38986069142](https://github.com/PhoenixEmik/QualiDock/actions/runs/38986069142).

Revisit only after upstream parsing rejects these malformed inputs, or after
separately justified, measured validator improvements remove the added bottleneck.
No release preparation, scheduler adapters or additional tools are part of this work.
