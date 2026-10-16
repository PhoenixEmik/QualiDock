# Validation and standalone release acceptance

QualiDock remains `0.1.0.dev0`; no release is tagged or published. This is the
current acceptance record. Development-phase documents describe historical
implementation environments and do not override this record.

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
