# Validation and standalone release acceptance

QualiDock remains `0.1.0.dev0`; no release is tagged or published. This is the
current acceptance record. Development-phase documents describe historical
implementation environments and do not override this record.

## Patched HTSlib security qualification — 2026-10-23

[CI 39930283266](https://github.com/PhoenixEmik/QualiDock/actions/runs/39930283266)
on application code `616494f` passed **all eight jobs** for security PR #42 /
Issue #41. Current admission requires **SAMtools 1.24 /HTSlib 1.24**,
**mosdepth 0.3.14 rebuilt with HTSlib 1.24** and explicit native version reporting,
and **RSeQC 5.0.5 /CLI 5.05 /pysam 0.24.1 /native HTSlib 1.24**.
Picard remains **3.5.0 /Java 17 /HTSJDK**. Historical 1.22.1 reports remain
readable, but those executables are no longer accepted for new analyses.

| Check | Accepted evidence |
| --- | --- |
| Default backend | 613 passed /231 missing-optional-tool skips; provisioned jobs execute the genuine tools |
| SAMtools/security | 66 passed without skips per matrix target; original BAM/CRAM flagstat and all 39 SN values/notes unchanged |
| Scientific regressions | All existing coverage, three RSeQC modes, Picard insert/RNA metrics, FastQC/MultiQC, fastp/SeqKit, nanoq/NanoPlot and FastQ Screen jobs passed |
| Gene-body | 49 parser/genuine-tool cases passed without skips; original values, index handling, source identity, cancellation and restart retained |
| Frontend | 154 passed; TypeScript/Vite build passed |
| Chromium /Firefox | 78 /54 cases, zero errors/failures/skips across retained XML; three prefix contexts, original artifacts and report isolation |
| Linux resources | 1 CPU /1 GiB cgroup; actual patched flagstat scan cancelled, source unchanged, partial QC unpublished; existing RSS/guardian/recovery checks passed |
| MultiQC | 1.25.1 /1.35 /latest 1.x (resolved 1.35), with original modules and existing source mapping |

See [HTSLIB-SECURITY.md](HTSLIB-SECURITY.md) for all seven July advisories,
official source-asset SHA-256 evidence, exact reader/loader contracts, scientific
comparison, explicit mosdepth version-only instrumentation and complete change
footprint. Downloaded proof is under ignored `validation/htslib-security`.
No original scientific output or numerical assertion was rewritten. Tiny fixture
evidence does not close large/shared-storage acceptance #5 or HPC hosting #4.
BCFtools remains gated on merging the accepted security PR. No release or tag.

## RSeQC gene-body coverage — 2026-10-19

[CI 39192950625](https://github.com/PhoenixEmik/QualiDock/actions/runs/39192950625)
on code `27ac706` passed **all eight jobs**. This completes #34 on top of the
merged #36 genuine-tool qualification. No release/tag is prepared or published;
#35 has not started. Scientific contracts, provenance and the complete change
footprint are in [RNA-QC.md](RNA-QC.md#rseqc-gene-body-coverage-505-34).

| Check | Accepted evidence |
| --- | --- |
| Complete backend CI | 517 passed /195 missing-optional-tool skips; provisioned jobs run the genuine tools |
| Gene-body parser + actual tools | 49 passed, no skips; sorted BAM, BAI/CSI, exact 1–100 values, public hg19 subset, original R PNG, zero/constant/short profiles, malformed output, cancellation, restart and source/index immutability |
| Existing #36 qualification | 9 pure report-contract tests retained, genuine version/help/original table/PNG/hash study rerun |
| MultiQC | 1.25.1 /1.35 /latest 1.x compatibility jobs passed; original 100 values and source mappings, duplicate BAM basenames and failed aggregation preserved independently |
| Frontend | 150 passed; TypeScript/Vite build passed; actual ECharts visibility actions, original-value tooltips and responsive SVG rendering |
| Chromium /Firefox | 75 /51 cases, zero failures/errors/skips; six RNA cases per browser across the three existing prefix contexts; original downloads, native chart/export, mobile and restart |
| Existing scientific/resource/security regressions | FastQC/MultiQC, fastp/SeqKit, SAMtools/CRAM, mosdepth, nanoq/NanoPlot/Screen, authenticated artifact/report isolation, derived reuse, lineage and Linux 1 CPU /1 GiB cgroup jobs passed |
| Local complete backend | 579 passed /131 missing-optional-tool skips /2 sandbox-blocked remote-search canaries deselected; both canaries remain enabled in accepted Linux CI |

Actual source values and manifests were independently checked from downloaded
`genebody-qc-evidence` (49-case JUnit, no skips); all 100 strings agree with the
original table for BAI, CSI, alternate BAI naming and the public hg19 fixture.
Browser JUnit and desktop Chromium/mobile Firefox screenshots were inspected
under ignored `validation/genebody-browser`. Original R min-max normalization is
explicitly distinguished from the native unnormalized table; no pixel-perfect
claim, bias threshold, invented ratio or absolute-depth claim is made.

Tested: RSeQC 5.0.5 (CLI 5.05), SAMtools 1.22.1, MultiQC 1.25.1/1.35, Rscript
4.4.1 on macOS and 4.3.3 in Linux CI. Existing process/resource/cancellation and
artifact security controls are reused. Special output-root HTSlib markers cannot
alter controlled relative index arguments. Failed PNG/aggregation bundles are
not registered, including after restart. No original BAM/index/annotation is
modified; all test-generated indexes stay in test-owned directories.

Limits remain explicit: BAM only; annotation name/coordinate compatibility is
not independent assembly verification; indexed-count agreement is operational
evidence rather than cryptographic proof of every index interval. Exact short-
transcript reports with inconsistent percentile counts are rejected, not filled.
Tiny fixtures are not large-BAM/NFS/Lustre performance acceptance; #5 stays open.

## RNA-seq and library alignment QC — 2026-10-17

[CI 39023607426](https://github.com/PhoenixEmik/QualiDock/actions/runs/39023607426)
on code `343a027` passed **all eight jobs**, with all supported scientific,
resource, browser and security checks enabled. Feature contracts and file
inventory are in [RNA-QC.md](RNA-QC.md); actual private measurement records and
limits are in [BENCHMARKING.md](BENCHMARKING.md#rna-seq-and-library-qc-evidence-5).
The final follow-up changes documentation only; no release/tag is created.

| Check | Final evidence |
| --- | --- |
| Backend default CI | 487 passed /166 missing-tool skips; provisioned jobs below execute the optional scientific cases |
| Genuine SAMtools/ref safety | 31 passed; BAM/CRAM, local reference policy and authenticated artifacts |
| RSeQC | 64 passed without skips, including independent CLI comparisons, public hg19 BAM, synthetic orientations and BED12 security |
| Picard | 49 passed without skips, including original PDF/Rscript, exact orientations/precision, single-end unavailable, tail cutoff, resources/cancellation/restart |
| New RNA/Picard MultiQC | Eight passed without skips on 1.35; genuine mixed original fixtures additionally pass on 1.25.1 and latest supported 1.x |
| Existing mosdepth | 46 passed |
| Existing FastQ Screen | 13 passed on each MultiQC target |
| nanoq / NanoPlot | Eight /13 genuine-tool cases passed |
| Retained processing/new benchmark | 91 passed without skips, including all 11 new alignment/RNA benchmark cases, genuine fastp/SeqKit and derived reuse |
| Existing QC/imports | Seven actual-tool cases per MultiQC target |
| Frontend | 146 passed; TypeScript and Vite build pass |
| Linux resources | Non-root one-CPU /one-GiB cgroup, affinity, memory, cancellation, guardians and restart remain passing |
| Chromium / Firefox | 72 /48 passed; JUnit has zero failures/errors/skips, including root and both existing URL prefixes |

Qualified new runtimes: **RSeQC 5.0.5** (scripts report 5.05), **Picard 3.5.0**
(original JAR), **Java 17.0.20.1**, **Rscript 4.3.3** for optional original PDF,
SAMtools/HTSlib1.22.1 and MultiQC1.25.1/1.35 (latest `<2` resolved to1.35).
FastQC0.13.0, fastp0.23.4 (Linux;1.4.0 locally), SeqKit2.14.0, nanoq0.10.0,
NanoPlot1.48.0, FastQ Screen and mosdepth retain their genuine regression suites.
The existing Falco qualification-only tests also pass; no extra engine is enabled.
No runtime package dependency or second executor/persistence layer was added.

Committed upstream reports include original RSeQC stdout/stderr over explicit
synthetic geometry plus Galaxy tools-iuc's pinned hg19 public test BAM/BED12.
Picard fixtures preserve the original metrics, histogram PDF, single-end zero
observation diagnostics, exact Java/R metadata and JAR SHA-256. Independent CLI
outputs match native original strings/tables; unknown SD remains `?`/unavailable,
not zero. The original PDF was rendered and visually inspected without editing.
Native screenshot/JUnit evidence is retained in `report-browser-*` artifacts
and locally under ignored `validation/rna-343-browser/{chromium,firefox}`.
Screenshots were visually reviewed; no pixel-perfect equivalence is claimed.

The MultiQC partial-bundle regression deliberately writes incomplete HTML/JSON
then fails. Verified RSeQC/Picard results remain downloadable; the failed bundle
stays on disk but is unpublished, including after restart. Registry tests cover
nonzero/active/cancelled exits and legacy manifests without execution metadata,
using existing execution records rather than another state model. Application
CSP, opaque-origin report sandboxing, authentication, source immutability and
historical result compatibility remain intact. No CI assertions or supported scientific regressions
were weakened or disabled.

Local full retained-tool run after the artifact fix: **621 passed /30 missing
optional-tool skips**, with two local socket-listener canaries deselected because
this managed macOS sandbox cannot bind sockets. The required Linux alignment
job executes those canaries. The portable local test fixture substitutes only
the denied RSS sampler; actual `/proc`/cgroup resource proof comes from Linux.
Missing local RSeQC/R/PDF/Falco cases are not treated as scientific evidence;
the provisioned jobs require actual tools and execute them. Focused local
preview/artifact/MultiQC checks:47 passed /four missing-local-RSeQC skips.

Seven completed new benchmark observations retain source hashes, exact
versions/argv, validation/preflight timing, sampled CPU/RSS, available individual
I/O counters and API observations. Their BAM inputs are505–1305 bytes and the
nanoq gzip input52,290 bytes. These test instrumentation, not scale. CPU includes
concurrent cold tool probes; sampled RSS can miss short tools; individual I/O
counters are not NFS/Lustre bandwidth. JVM startup overhead was not isolated.
**Issue #5 remains open** for authorized large files, real shared storage,
cache/concurrent-load, live network/SSE, insufficient-space and site tuning.

Deliberate limits: new RSeQC/Picard modes accept BAM only; no RNA/Picard CRAM
qualification is asserted. BED12 SHA-256 and BAM contig/bounds checks do not
prove complete genome assembly identity. Picard per-library MultiQC is disabled
because upstream combines overlapping populations. Native library rows and
original reports remain available. Aggregation is scoped to the current
operation; external MultiQC-only imports retain their FastQC/fastp allowlist.
No gene-body coverage, expression/variant pipeline, reference download, OOD/PBS
expansion or release work was performed.

## Core usability and performance implementation — 2026-10-17

Issues #5, #26 and #27 extend the existing benchmark and add two read-only views.
No execution engine, database, dependency, workflow scheduler, persistence format
or top-level navigation was added. RunManager, tool adapters, FASTQ validation,
dataset authorization and secure report serving remain the existing implementations.

[CI 38958391847](https://github.com/PhoenixEmik/QualiDock/actions/runs/38958391847)
at `8f43384` passed all eight jobs. All tests and the workflow remained enabled;
the final follow-up changes documentation only.

| Check | Evidence |
| --- | --- |
| Backend default CI | 285 passed / 46 missing-tool skips; the provisioned jobs execute these scientific cases |
| Genuine processing and new capabilities | 80 passed without skips; includes the 17-case benchmark suite, Inspector and a raw → fastp → SeqKit → FastQC chain |
| Genuine QC/imports | Seven cases per MultiQC target: 1.25.1, 1.35 and latest supported 1.x |
| Frontend | 142 tests and TypeScript/Vite build pass; existing bundle-size warning remains |
| Linux resources | Existing non-root 1 CPU / 1 GiB affinity, memory, cancellation, guardian and restart checks pass |
| Chromium 156.0.8078.4 | 51 passed: Inspector 3, Lineage 3, processing 9, retained reports/security/history/analytics 36 |
| Firefox 157.0 | 27 passed: Inspector 3, Lineage 3, processing 9, critical report isolation/interaction/restart 12 |

JUnit artifacts for both browsers report zero failures, errors or skips. Actual
Inspector and Lineage mobile screenshots were reviewed; their PNGs are retained
in the corresponding report-browser artifacts and locally under
validation/core-usability/{chromium,firefox}/. These are HTTP browser/prefix tests,
not acceptance of a deployed OOD/HTTPS site.

Local full backend run before the final benchmark-only edge additions: 329 passed,
zero skipped. The final focused benchmark run passes all 17 tests, including
partial publication, cancellation, bounded monitoring and timeout terminal evidence.
Inspector has 11 focused cases; Lineage has five, including genuine processing and
restart. Local tools: FastQC 0.13.0, MultiQC 1.35, fastp 1.4.0, SeqKit 2.14.0.
Linux CI processing uses fastp 0.23.4 and SeqKit 2.14.0 with FastQC 0.13.0.

### Measured fixture observations (Linux CI)

The private CI JSON retained all eleven completed mode/configuration runs. One
2-file fixture observation (400 reads/mate, 109,308 source bytes) recorded:

| Operation | Wall seconds | Waited-child CPU seconds | Derived bytes |
| --- | ---: | ---: | ---: |
| FastQC | 6.970 | 5.190 | 0 |
| FastQC + MultiQC | 9.083 | 7.193 | 0 |
| fastp baseline | 2.376 | 2.047 | 99,971 |
| fastp + raw/post QC + MultiQC | 15.790 | 11.514 | 99,971 |
| Exact-count sampling | 2.233 | 1.985 | 2,220 |

These are single small-file observations, not throughput comparisons or tuning
recommendations. Wall includes API/polling/audit costs; source before-hash timing
is separate. Child CPU includes probes/guardians and excludes API-parent CPU.
Process-tree RSS is sampled at 0.5 s and can miss an entire short tool execution;
the JSON labels it sampled, never exact peak. Validation uses actual byte counters;
fastp's 109,308 source + 99,971 derived validation bytes are separate from the
99,971-byte independent output hash audit and two optional source hash passes.
No physical disk/network I/O total is asserted. Cache/concurrent-load conditions
and representative large-file/shared-storage behavior were not measured.

### What was verified

The benchmark uses actual tools and the existing public 400-read-per-mate fixture
(109,308 compressed source bytes). FastQC-only, combined QC, fastp with/without
optional QC, SeqKit statistics, fraction/exact sampling and independent/paired
length and ID selection execute through the normal lifecycle. Sources retain
before/after hashes; registered derived outputs match saved validation hashes.
Failed/partial/cancelled/timeout results remain distinct. Per-process I/O is not
summed because waited-child counters can overlap; source/output validation bytes,
extra audit/hash passes, sampled RSS and waited-child CPU have separate scopes.
Private fixture evidence JSON is uploaded with core-processing-io; see
[BENCHMARKING.md](BENCHMARKING.md). This is not large-data performance acceptance.

Inspector tests actual plain/gzip records, wrapped lines, exact quality characters,
count/record/decompression/response bounds, empty/malformed/oversized data,
confirmed first-N IDs and mismatches, derived outputs after restart, source
immutability, no analysis creation, auth/CSRF, traversal/symlinks, forged refs and
input/output-root overlap. Browser tests also check escaped header text, raw and
derived selections, keyboard scrolling, responsive containment and close focus.

Lineage reads recorded manifests on demand: at most 20 nodes / depth 8 / 50 items
per analysis, with explicit omissions and no reverse graph scan. Tests cover
cycles, missing parents, old metadata, independent inputs, lane/chunk identity,
changed sources and inconsistent copied hashes. The real multi-generation chain
retains R1/R2 identities, output hashes, parent navigation and report access after
restart. Metadata matches are never described as fresh content verification.

The initial lineage browser failure targeted the state row rather than the page
heading; the assertion now checks the heading and labeled Analysis ID, retaining
all scientific assertions. An existing synthetic report-security fixture omitted
its analysis.log and caused background 500s in Firefox; it now has the same empty
log layout as an owned run, checked before browser interaction. No security,
scientific or supported-feature assertions were removed or relaxed.

### Files and compatibility

Added production files: backend/qualidock/inspector.py and lineage.py;
frontend/src/FastqInspector.tsx, ProcessingLineage.tsx and inspector.ts.
Modified: app.py, App.tsx, AnalysisDetail.tsx, ProcessingResults.tsx, styles.css
and the existing scripts/benchmark-analysis.py. Added tests: test_benchmark.py,
test_inspector.py, test_lineage.py, inspector.test.ts, test_inspector_browser.py,
test_lineage_browser.py. Updated the report-browser fixture, CI, README,
BENCHMARKING.md, PROCESSING.md and this acceptance record. No files were deleted (11 added, 12 modified across the repository including
this final evidence update).
The flat source-provenance panel was replaced by the bounded lineage view; its
scientific metadata remains in original manifests.

Against 62f6395, application production Python/TS/TSX/CSS adds 764 lines and removes
19 (net +745); the benchmark adds 135 and removes 32 (net +103). No runtime
package dependency changed. Both APIs are additive: POST /api/inspector and
GET /api/runs/{id}/lineage. Existing manifests and all execution/report APIs remain
compatible. The full file/line inventory is git diff --numstat 62f6395..8f43384;
private local evidence is under validation/core-usability/. The final
documentation-only follow-up uses [skip ci] because the complete accepted
production/test/workflow tree above is unchanged.

### Remaining acceptance and limits

Issue #5 remains open: no authorized representative large FASTQs or NFS/Lustre
allocation was supplied. Tiny-fixture wall/CPU/RSS/scan observations are not
physical/network throughput, cache/concurrent-load acceptance or site defaults.
Inspector supports ASCII headers and bounded records only; it does not infer
encoding, index/hash a file, verify later records or prove whole-file pairing.
Lineage cannot recover absent provenance and does not discover all children.
The installed Starlette TestClient emits an httpx deprecation warning; tests pass,
and no dependency was added merely to silence it. The existing ECharts bundle
warning remains. No release/tag, OOD/PBS work or additional operation was introduced.

## Earlier accepted automated evidence — 2026-10-16

[CI 38918679043](https://github.com/PhoenixEmik/QualiDock/actions/runs/38918679043)
at `6361f43` passed all eight jobs after the focused cleanup:

| Check | Accepted evidence |
| --- | --- |
| Backend | 269 passed; 29 missing-tool cases run in separately provisioned jobs |
| Frontend | 141 tests; TypeScript/Vite production build |
| Actual processing | 47 tests, no skips; FastQC 0.13.0, MultiQC 1.35, fastp 0.23.4, SeqKit 2.14.0 |
| Actual QC/imports | Seven tests per MultiQC 1.25.1, 1.35 and latest-supported 1.x target (resolved to 1.35) |
| Chromium | Nine native processing/reuse tests and 36 retained interaction/security/history/chart tests |
| Firefox 157.0 | Nine native processing/reuse tests and 12 critical genuine-report interaction/isolation/restart tests |
| Linux resource/process | Non-root, 1 CPU / 1 GiB cgroup; affinity, RSS termination, cancellation, queue recovery, guardian and restart |

Local full genuine-tool verification: **298 backend tests passed, no skips**,
with FastQC 0.13.0, MultiQC 1.35, fastp 1.4.0 and SeqKit 2.14.0 (macOS arm64).
Chromium was 156.0.8078.4. The Firefox job covers the listed critical subset;
the complete 45-case browser suite remains Chromium acceptance.

One obsolete unit test for the unused client-side history filter was removed
with that module; equivalent sorting/filter assertions now exercise the backend
contract. No supported scientific/security regression was disabled. New genuine
MultiQC CLI failures preserve FastQC/fastp results, and both browsers verify
confirmed fraction-sampling setup plus derived reuse → logout/login → raw-input
processing. The initial logout regression exposed stale reviewed metadata;
the application reset was fixed rather than weakening the test.

The processing tests compare actual FASTQ records, source checksums, normalized
mate identifiers/order, counts, seed reproducibility and independent reservoir
indices. They cover malformed inputs, partial failures, cancellation, output path
security, restart and derived reuse. No Q20/Q30 percentages are inferred from
FastQC aggregate quality statistics. See [PROCESSING.md](PROCESSING.md).

Chromium runs the production build with genuine QC reports under standalone and
the two retained URL-prefix layouts. It checks opaque-origin report isolation,
authentication, source mappings, native plots, downloads, exports, polling/SSE
recovery, history, reruns, derived reuse and narrow layouts. These are local HTTP
integration tests, not evidence of an actual OOD/HTTPS installation. See
[REPORT-VIEWER.md](REPORT-VIEWER.md), [HISTORY.md](HISTORY.md) and the CI artifacts.

Earlier accepted baselines remain meaningful: [paired-processing CI 38914238400](https://github.com/PhoenixEmik/QualiDock/actions/runs/38914238400)
at `9d7aa49` passed 288 backend cases across its provisioned jobs, 142 frontend
tests and 45 Chromium cases; the [core-first simplification
CI 38899079194](https://github.com/PhoenixEmik/QualiDock/actions/runs/38899079194)
at `1914146` passed 42 Chromium cases and the then-current core suites;
[LINUX-VALIDATION.md](LINUX-VALIDATION.md) preserves the original cgroup/process
observations; [BROWSING.md](BROWSING.md) and [HISTORY.md](HISTORY.md) preserve
explicitly scoped directory/history benchmarks. None establish large-FASTQ or
NFS/Lustre throughput.

## Standalone release candidate gates — issue #7

- [x] Genuine FastQC/MultiQC/fastp/SeqKit workflows and exact native data checks.
- [x] Authentication, path containment, downloads and HTML sandbox regressions.
- [x] Linux cancellation, resource enforcement, guardian and restart evidence.
- [x] Chromium interaction/responsiveness and Firefox critical workflows, including derived reuse and session reset.
- [x] All relevant cleanup CI jobs pass at `6361f43`; a future versioned release candidate must rerun its own gates.
- [ ] Review licenses, installation, upgrade/rollback and scoped limitations.
- [ ] Align release versions and publish only under a separate release instruction.

Release notes must list the browsers and tool versions actually tested. Current
CI covers Chromium fully and the explicitly listed Firefox critical subset.
A compatible version range is not a claim that every version was tested.

## Separate, unaccepted deployment/performance claims

- **Issue #4:** the retained optional OOD adapter still requires site-specific
  HTTPS proxy, session, installed-module and shared-storage acceptance. It is not
  a prerequisite for a standalone-only release. No OOD/PBS changes belong to this
  cleanup.
- **Issue #5:** representative large FASTQs and NFS/Lustre measurements are still
  pending. Small fixtures validate scientific behavior, not throughput or
  large-file resource recommendations. Use [BENCHMARKING.md](BENCHMARKING.md).

Project/release administration, controlled delivery and retention workflows were
removed intentionally. Issues #24/#25 are abandoned scope, not missing standalone
features. Historical analyses, QC artifacts and source/derived FASTQs remain
preserved; the offline catalog export is documented in [CORE-FIRST.md](CORE-FIRST.md).

## Historical environment records

The original [Phase 2 record](PHASE2.md) retains its 2026-10-15 result of 82 backend
tests, one missing-MultiQC skip, 36 frontend tests and actual FastQC 0.13.0 fixture
provenance. Its missing-tool/browser/site limitations describe that environment,
not the current accepted standalone behavior.

On 2026-10-14, the initial bootstrap ran 29 backend orchestration tests on Python
3.13 with fixture executables, compiled Python and rendered the existing OOD
ERB/YAML/shell templates. Frontend dependencies were verified against lockfile
integrity hashes and the real ECharts TypeScript/Vite build passed. TestClient
served its HTML/JS/CSS. There was no connected browser or usable local server bind,
no real FastQC/MultiQC installation, and no Linux/site execution. The macOS test
fixture substituted only the denied RSS sampler; orchestration fixtures did not
validate the scientific engines. The smoke test reported missing FastQC clearly.
That bootstrap record was never a claim of release acceptance. Subsequent genuine
tool, Linux and browser evidence above supersedes those environment limitations.

The final follow-up commit updates documentation only and uses `[skip ci]` because
the complete production/test/workflow tree above already passed. No code, test or
CI configuration change is excluded from acceptance. No release/tag was created.
