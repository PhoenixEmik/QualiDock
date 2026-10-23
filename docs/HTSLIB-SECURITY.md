# HTSlib security qualification (Issue #41)

This is the security milestone only. BCFtools integration is gated on all
scientific, security, Linux-resource and browser acceptance checks passing and
the focused security PR being merged. No release or tag is authorized.

## Upstream advisory evidence

On 9 July 2026, HTSlib published seven advisories. The affected maintenance lines
include 1.22.1/1.22.2 and 1.23.1. Upstream lists fixes in 1.21.2, 1.22.3, 1.23.2
and 1.24. A patched version is not automatically a qualified QualiDock version.

| Advisory | CVE | Affected reader |
| --- | --- | --- |
| [GHSA-2wm6-8hgm-7g92](https://github.com/samtools/htslib/security/advisories/GHSA-2wm6-8hgm-7g92) | CVE-2026-63390 | BCF input validation |
| [GHSA-28r7-prwc-hf5c](https://github.com/samtools/htslib/security/advisories/GHSA-28r7-prwc-hf5c) | CVE-2026-62255 | CRAM index handling |
| [GHSA-4hjq-r829-8c8v](https://github.com/samtools/htslib/security/advisories/GHSA-4hjq-r829-8c8v) | CVE-2026-62256 | FASTA index handling |
| [GHSA-6q7c-m967-9v37](https://github.com/samtools/htslib/security/advisories/GHSA-6q7c-m967-9v37) | CVE-2026-62257 | Experimental CRAM 4.0 decoder |
| [GHSA-2jx2-wm7f-rv9m](https://github.com/samtools/htslib/security/advisories/GHSA-2jx2-wm7f-rv9m) | CVE-2026-62258 | CRAM decoder |
| [GHSA-hg3g-v57p-459q](https://github.com/samtools/htslib/security/advisories/GHSA-hg3g-v57p-459q) | CVE-2026-62259 | CRAM 4.0 reader |
| [GHSA-rjqv-xg3q-g423](https://github.com/samtools/htslib/security/advisories/GHSA-rjqv-xg3q-g423) | CVE-2026-62260 | CRAM 3.x/4.0 readers |

[HTSlib 1.24](https://github.com/samtools/htslib/releases/tag/1.24) removes
experimental CRAM 4.0 support. This does not remove QualiDock's qualified CRAM
3.x operation. Index/reference validation, EOF checks and a full stats scan
remain necessary; patching the decoder does not establish source authenticity.
The bounded malformed fixtures are ordinary truncations/header corruption, not
exploit reproductions. No exploit payloads are added.

## Reader inventory and exact runtime contracts

| Component | Actual reader and policy |
| --- | --- |
| SAMtools | Exactly **SAMtools 1.24 / HTSlib 1.24**. Both independent version lines are required; contradictory, missing, prerelease and unqualified maintenance/future versions fail closed. CI builds the release-bundled static HTSlib and records full compilation details, binary/archive/library hashes and `ldd`. macOS local evidence uses `otool -L`. |
| mosdepth | Same **mosdepth 0.3.14 / hts-nim 0.3.31**, rebuilt with **HTSlib 1.24**. The official static 0.3.14 asset contains HTSlib 1.22.1 (audited via its embedded version and symbols) and is no longer admitted. See the explicit instrumentation below. SAMtools's version is never used as evidence of mosdepth's reader. |
| RSeQC | Same **RSeQC 5.0.5**, CLI **5.05**; explicitly pin **pysam 0.24.1 / HTSlib 1.24**. The [pysam release](https://github.com/pysam-developers/pysam/releases/tag/v0.24.1) wraps HTSlib 1.24. Runtime checks the configured script's own Python interpreter with `-I`, distribution metadata and the actual native `hts_version()` exported by its `pysam.libchtslib` extension. Shell launchers and unverifiable/mismatched environments are unavailable. CI compares the native result with `pysam.version.__htslib_version__`, and records the native extension's actual path and linked libraries. |
| Picard | **Picard 3.5.0 / Java 17 / HTSJDK**, not HTSlib. Its insert-size and RNA-metrics algorithms are unchanged; SAMtools preflight and fixture conversion move to 1.24. CRAM remains unqualified for Picard. |
| NanoPlot / nanoget | Existing FASTQ-only operation. Inspection of the pinned [nanoget 1.19.6 source](https://pypi.org/project/nanoget/1.19.6/) confirms that the selected FASTQ paths use Biopython `SeqIO.parse`; its separate pysam BAM readers and automatic BAM-index creation are unreachable through QualiDock's `--fastq`/`--fastq_rich` contract. Full structural FASTQ validation precedes execution. Its isolated dependency environment is separate from RSeQC; neither external samtools nor the RSeQC probe attests other NanoPlot modes. No unrelated dependency is silently replaced. |
| Other supported tools | FastQC/Picard use Java implementations; SeqKit and nanoq are not HTSlib readers; Bowtie2/FastQ Screen consume the existing FASTQ contract. They are not silently upgraded or claimed fixed by this change. |

SAMtools/HTSlib 1.22.1 is rejected, even when historical manifests and original
reports remain readable. Exact version reporting is an operator-trusted tool
contract, not an attestation that an arbitrary executable cannot lie. CI source
hashes, static/dynamic loader evidence and independent scientific execution
provide the qualification evidence. No tools are installed by the application.
RSeQC's probe and execution both clear inherited Python home/path overrides,
disable user-site imports and enable Python's safe-path mode. Otherwise an
isolated probe could qualify a different pysam than the scientific command
actually imports. Genuine RSeQC tests exercise an injected shadow `pysam.py`.

### mosdepth version-only instrumentation

Upstream mosdepth reports its own version but not its HTSlib version. Its
hts-nim binding loads `libhts` with `dlopen`, which `ldd mosdepth` alone misses.
The isolated build makes two explicit, guarded substitutions:

1. hts-nim's shared-library filename becomes the absolute path of the HTSlib
   1.24 built from the authenticated SAMtools release.
2. mosdepth's version string additionally calls the existing `htslibVersion()`
   function. The probe requires the exact additional `Using htslib 1.24` line.

No coverage algorithm, input filtering, overlap correction, report value or
original output is patched. The binding/library and executable must remain at
their configured installation paths. CI records an actual `LD_DEBUG=libs`
version invocation and binary/library hashes; absence of that exact library is
a failure, with no system-loader fallback. A stock static binary that reports
only `mosdepth 0.3.14` is unavailable. This limitation is deliberate.

## Authenticated sources

The SAMtools source is the official release asset, not GitHub's incomplete
generated source archive. On 2026-10-23 the official GitHub API endpoint
`repos/samtools/samtools/releases/tags/1.24` reported the asset digest:

`samtools-1.24.tar.bz2`: `89b2a440123eeaa400392ce1736e7d60ce9041843027d76819753c5a8246bfdd`.

It contains HTSlib 1.24. The separate official HTSlib asset's upstream digest is
`28a8de191381c7a97a35675ceac76fa1ea95e7b678d6a2e9d600a7874e4077de`;
it is recorded for reference, not substituted for the actual bundled archive.
CI verifies the SAMtools archive before extraction/build, explicitly configures
`--with-htslib=htslib-1.24`, and rejects a dynamic system `libhts` dependency.

The same-version mosdepth build uses official GitHub tagged source archives.
Their locally verified archive SHA-256 values are pinned in provisioning;
these are reproducibility pins, not falsely described as upstream-published
release-asset digests:

| Source tag | Upstream Git commit | Archive SHA-256 |
| --- | --- | --- |
| mosdepth v0.3.14 | `821fddb12860d024fef4cf0bfe86918f2413d4e4` | `abac67de4547dc5642efd46846044d6b3536d2ca3443b4ca172446edf82eeb42` |
| hts-nim v0.3.31 | `93ad65442b16d0191aa0c44803d10a6fb7cde9fa` | `e2e8572156cced4557fcb75ecf5a7ee072bcc7abf81066d4b54d5bf674dab3e0` |
| docopt.nim v0.7.1 | `efaa112b6df172a9168c4eb581ab8dda1fbcfe2a` | `a172f7e8be5c10735727ca00f69294e8615c4ad055dd9b58dcdb0f7c6bd7d025` |

docopt's existing transitive build dependencies are also pinned (official
`nitely` tagged source archives): nim-regex 0.11.1 SHA-256
`c9890246cada2eedee9c4a880073727f4f7025367d9c63bf89e4c50a64eaad67`,
nim-unicodedb 0.7.0 `ccf0fe9ec986420e368d2c1fcbe420d0157a49f5d8cb1fe9489518bbffda374a`,
nim-unicodeplus 0.5.0 `1649472ef3bcb5f9e8bab2cae402a9394e1aab089ab9a6a7abe05c6d9e9e74d7`.
No network dependency resolution occurs during compilation.

The accepted Linux compiler is distribution-provided **Nim 1.6.14**, using
`--gc:refc`; its exact version is retained. No speculative compiler upgrade or
new application runtime dependency is added.

## Scientific and failure acceptance

`qualify-samtools-security.py` independently runs head/quickcheck/flagstat/stats
on BAM and locally referenced CRAM. It preserves stdout/stderr and exact argv,
compares against committed genuine 1.22.1 reports, and records source hashes.
Initial macOS comparison found byte-identical flagstat and identical values and
notes for all **39** SN rows: primary sequences **6**, mapped **5**, total length
**40** on the explicit synthetic population. The full original report retains
its actual version/argv comments. This is not a claim of universal numerical
equivalence across releases or biological populations.

The existing numerical coverage/RSeQC/Picard assertions remain intact. No
original report is rewritten, no count assertion is relaxed and no existing
test is disabled. Controlled CRAM reference search/cache remains disabled;
BAI/CSI/CRAI authorization, source/reference identity changes, unauthorized
paths, cancellation/restart and incomplete-artifact rejection are exercised.
The Linux cgroup validation also observes and cancels a real patched SAMtools
decoder while retaining existing process-tree RSS, CPU-affinity, queue,
shutdown, guardian and recovery checks. Chromium/Firefox run existing root and
proxy-prefix workflows. MultiQC 1.25.1, 1.35 and latest qualified 1.x retain
their original official modules and the existing documented 1.25.1 limitation.

### Gate status

[CI 39930283266](https://github.com/PhoenixEmik/QualiDock/actions/runs/39930283266)
on code `616494f` passed **all eight jobs** on 2026-10-23. This is the accepted
security candidate for [PR #42](https://github.com/PhoenixEmik/QualiDock/pull/42)
and Issue #41; Variant QC must still wait for that PR to be merged.

- Default backend: **613 passed /231 missing-optional-tool skips**; provisioned
  scientific jobs execute those tools rather than treating skips as evidence.
- SAMtools/security suites: **66 passed, no errors/failures/skips**, in each
  MultiQC matrix target. Both BAM/CRAM original flagstat and all 39 SN values/
  notes match the genuine 1.22.1 baseline, with original stdout/stderr retained.
- Gene-body suite: **49 passed, no skips**; all existing numerical/index/security
  assertions retained. Local genuine RSeQC plus gene-body regressions also passed
  **49** cases, including shadow-module isolation.
- RSeQC unit/genuine suite **66 passed**, coverage **46**, Picard insert-size
  **49**, Picard RNA production **79** plus **15** qualification cases, and
  RNA/alignment MultiQC **9** passed in the fully provisioned 1.35 job.
- Frontend: **154 passed**, TypeScript/Vite build passed.
- Chromium/Firefox: **78 /54 cases**, zero errors/failures/skips across the
  retained XML suites. Root, `/node/compute/8765`, `/rnode/compute/8765`, native
  results, original downloads, restart/rerun and report sandbox are exercised.
  Downloaded mobile alignment/Picard RNA screenshots were visually inspected.
- MultiQC **1.25.1 /1.35** and latest qualified 1.x (**resolved to 1.35**) passed.
- Linux **1 CPU /1 GiB cgroup** passed. The captured native command was actual
  `samtools flagstat -@ 0`, cancelled during the record scan; the group exited,
  source hashes were unchanged and partial QC reports remained unpublished.
  Existing process-tree memory termination/recovery, affinity, shutdown and
  guardian checks passed. RSS samples are observations, not exact peaks.

Downloaded evidence is retained under ignored `validation/htslib-security`,
including official source/binary/library hashes, `LD_DEBUG` mosdepth library
initialization/finalization paths, native pysam HTSlib 1.24, independent original
reports, JUnit XML, screenshots and the full CI job result. The full genuine
FastQC, fastp/SeqKit, nanoq/NanoPlot, Screen, coverage and Picard insert/RNA jobs
also passed. No scientific count assertion or original report was weakened.

Source footprint relative to `01bb479`: **5 files added /18 modified /0 removed**.
Application source is **+71 /−37 (net +34)** across tools, RSeQC environment
isolation and an alignment docstring; RunManager, execution framework, form and
navigation are unchanged. The final acceptance follow-up changes documents only.

The version-policy unit tests alone are not scientific evidence. Tiny synthetic
fixtures and the bounded malformed cases are not a comprehensive fuzzing proof,
large-file qualification, NFS/Lustre throughput or production-hosting acceptance.
Those operational limits remain tracked by #5/#4. No release/tag is prepared.
