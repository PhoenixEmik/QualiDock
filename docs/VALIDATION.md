# Validation and standalone release acceptance

QualiDock remains `0.1.0.dev0`; no release is tagged or published. This is the
current acceptance record. Development-phase documents describe historical
implementation environments and do not override this record.

## Accepted automated evidence — 2026-10-16

[CI 38913214520](https://github.com/PhoenixEmik/QualiDock/actions/runs/38913214520)
at `02e1524` passed every job, including the paired-processing enhancement:

| Check | Accepted evidence |
| --- | --- |
| Backend | 261 passed; 27 missing-tool cases run in separately provisioned jobs |
| Frontend | 142 tests; TypeScript/Vite production build |
| Actual processing | 45 tests, no skips; FastQC 0.13.0, MultiQC 1.35, fastp 0.23.4, SeqKit 2.14.0 |
| Actual QC/imports | Seven tests per MultiQC 1.25.1, 1.35 and latest-supported 1.x target (resolved to 1.35) |
| Chromium | Nine native processing/reuse tests and 36 retained interaction/security/history/chart tests |
| Linux resource/process | Non-root, 1 CPU / 1 GiB cgroup; affinity, RSS termination, cancellation, queue recovery, guardian and restart |

Local full genuine-tool verification at the same processing implementation:
**288 backend tests passed, no skips**, with FastQC 0.13.0, MultiQC 1.35,
fastp 1.4.0 and SeqKit 2.14.0 (macOS arm64). The later `9d7aa49` refinement
records selector identity on failed operations and clarifies UI labels; acceptance
for the cleanup candidate must use its own complete CI rather than assuming that
an older green build certifies new code.

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

Earlier accepted baselines remain meaningful: the [core-first simplification
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
- [x] Chromium interaction, responsive layout and derived reuse evidence.
- [ ] All relevant CI jobs pass at the exact final release candidate.
- [ ] Review licenses, installation, upgrade/rollback and scoped limitations.
- [ ] Align release versions and publish only under a separate release instruction.

Release notes must list the browsers and tool versions actually tested. Current
CI supports Chromium; previous Chromium acceptance is not Firefox acceptance.
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
