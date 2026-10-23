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
| RSeQC | Same **RSeQC 5.0.5**, CLI **5.05**; explicitly pin **pysam 0.24.1 / HTSlib 1.24**. The [pysam release](https://github.com/pysam-developers/pysam/releases/tag/v0.24.1) wraps HTSlib 1.24. Runtime checks the configured script's own Python interpreter with `-I`, distribution metadata and `pysam.__htslib_version__`. Shell launchers and unverifiable/mismatched environments are unavailable. CI records the native extension's actual path and linked libraries. |
| Picard | **Picard 3.5.0 / Java 17 / HTSJDK**, not HTSlib. Its insert-size and RNA-metrics algorithms are unchanged; SAMtools preflight and fixture conversion move to 1.24. CRAM remains unqualified for Picard. |
| NanoPlot / nanoget | Existing FASTQ-only operation, with no BAM/CRAM exposure through this application. Its isolated dependency environment is separate from the RSeQC environment. A newer external samtools does not patch Python extensions. |
| Other supported tools | FastQC/Picard use Java implementations; SeqKit and nanoq are not HTSlib readers; Bowtie2/FastQ Screen consume the existing FASTQ contract. They are not silently upgraded or claimed fixed by this change. |

SAMtools/HTSlib 1.22.1 is rejected, even when historical manifests and original
reports remain readable. Exact version reporting is an operator-trusted tool
contract, not an attestation that an arbitrary executable cannot lie. CI source
hashes, static/dynamic loader evidence and independent scientific execution
provide the qualification evidence. No tools are installed by the application.

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

The compiler is the test runner's distribution-provided Nim; its exact version
is retained. No speculative compiler upgrade or new runtime dependency is added.

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

Security branch: implementation/acceptance in progress. Full CI, Linux resource
evidence and both browser jobs must pass before merger or Variant QC work.
The new version-policy tests are not scientific evidence by themselves. Local
missing-tool skips and tiny synthetic fixtures do not qualify large files,
NFS/Lustre throughput or production hosting. Those remain tracked by #5/#4.
