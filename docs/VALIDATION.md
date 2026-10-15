# Validation and release gate

This repository is an MVP development implementation, not a validated v0.1.0 release.

## Issue follow-up verification — 2026-10-15

[Issue-by-issue status and CI evidence](ISSUES.md) supersede the earlier missing-MultiQC/Linux-validation limitations below. Real MultiQC 1.25.1, 1.35 and latest-supported 1.x now pass combined and existing-result workflows. Native Linux cgroup/process checks pass under 1 CPU / 1 GiB. Directory browsing is covered by regression tests and a local 100,000-name benchmark. Actual site, large-input and browser acceptance remain pending.

## Phase 2 verification — 2026-10-15

See [Phase 2 implementation and validation](PHASE2.md) for the current module coverage, actual FastQC 0.13.0 checks, MultiQC execution tests, backward-compatible persistence fields, and remaining real-MultiQC/Linux/browser/HPC acceptance work. The older record below describes the initial implementation environment.

## Local verification record — 2026-10-14

- **29 backend tests passed** on Python 3.13 in the managed macOS workspace. QC orchestration used real fixture subprocesses. The macOS RSS sampler was replaced in tests because the sandbox denies `ps`; separate tests exercise Linux `/proc` parsing and the over-budget termination response.
- OOD ERB templates rendered, submission YAML parsed, CPU/memory values matched the requested PBS allocation, invalid PBS tokens were rejected, and rendered launch scripts passed `bash -n`.
- Python sources compiled successfully. On the follow-up local-run request, the real frontend dependencies were downloaded through permitted `curl` calls, verified against lockfile integrity hashes, and installed with `npm ci --offline`. The full TypeScript and Vite production build **passed**, including the real ECharts dependency. A reproducible `frontend/package-lock.json` is now present.
- FastAPI served the production HTML and all referenced JS/CSS assets successfully through TestClient. Earlier temporary UI-check stubs were discarded; the production build contains real ECharts.
- Browser QA was unavailable: no browser providers were connected, and the sandbox rejected binding the local server port.
- The real-tool smoke test stopped with a clear missing-FastQC message. Neither FastQC nor MultiQC was available. Generic dependency-manager network access was blocked, although permitted `curl` downloads enabled the frontend installation. Standalone Linux and HPC deployment tests were not run.
- Git metadata could not be initialized in this workspace because `.git` writes are denied. The initial development commit was subsequently pushed from an isolated checkout; no release was created.

## Automated coverage

### UI simplification verification

The sidebar now contains Workspace and Analyses. Workspace opens directly on the Samples/Files explorer; analysis setup is reached from its New analysis button or the current selection. Job information, logs, actual parsed QC metrics, and report downloads are nested under individual analyses. The UI shows recorded job states and stages, without a percentage estimate.

- Eleven frontend tests cover confirmed pairs, incomplete and ambiguous pairs, unrecognized filenames, separate directories, searching either mate, partial selection across views, pagination, report selection, and missing inputs.
- Server-side React render checks verified sample disclosures, mixed selection states, accessible analysis tab/panel associations, actual stage/log output, empty metrics behavior, and download URLs under the proxy prefix. These checks do not replace live interaction or visual QA.
- The TypeScript/Vite production build passed with the real ECharts dependency. All 29 existing backend tests passed, and backend source files were verified unchanged from the initial published commit.
- No browser provider was connected for live visual or interaction QA. Responsive CSS, native keyboard controls, directory focus handling, and arrow/Home/End navigation between analysis detail tabs are implemented; browser verification remains outstanding.

Further work should prioritize real FastQC/MultiQC end-to-end execution on standalone Linux and HPC systems.

### Backend coverage

Backend tests execute fixture QC tools as actual child processes through LocalExecutor. They cover file pairing, missing mates, traversal, escaped symlinks, authentication/cookie/CSRF boundaries, unauthorized downloads, opaque HTML attachments, all three modes, partial and failed execution, exact parsed quality statistics, immutable original FASTQ inputs, cancellation, process-group cleanup, resource validation, persistent restart recovery, exclusive output ownership, artifact substitution, malformed metrics, ZIP non-extraction, and proxy prefixes.

The managed macOS development sandbox denies `ps`, so its backend tests replace only the RSS sampler with deterministic readings. Linux tests use the native `/proc` sampler. Fixture QC executables validate orchestration, not FastQC/MultiQC's scientific behavior. Real-tool acceptance is a separate smoke script and CI job.

## Required before release

- [x] Frontend TypeScript and Vite production build with the real ECharts dependency.
- [ ] Browser QA of Workspace, analysis setup, Analyses, all analysis detail sections, authentication, live SSE, downloads, and mobile layout.
- [x] Linux backend suite with real process and resource monitoring; see [evidence](LINUX-VALIDATION.md).
- [x] Real FastQC 0.13.0 + MultiQC end-to-end smoke on standalone Linux; fixed 1.25.1/1.35 and latest-1.x CI targets pass.
- [x] Native chart points compared to actual FastQC output, including grouped bases and quartiles, with ECharts rendering tests. Live browser QA remains separate.
- [ ] HPC site configuration and end-to-end acceptance under the actual OOD reverse proxy.
- [ ] Large-file cancellation, memory-limit failure, graceful shutdown, and abrupt-session interruption on Linux/PBS.
- [ ] Historical reports restored after an OOD restart from persistent storage.
- [ ] Traversal, symlink escape, unauthenticated download, and command-injection checks in both deployment environments.

FastQC's documented per-base chart uses a median, interquartile box, 10th/90th percentile whiskers and mean line; QualiDock preserves those values rather than inferring new quality statistics. See [the official FastQC interpretation](https://www.bioinformatics.babraham.ac.uk/projects/fastqc/Help/3%20Analysis%20Modules/2%20Per%20Base%20Sequence%20Quality.html). MultiQC runs with an explicit output directory and JSON data output, following [its CLI documentation](https://docs.seqera.io/multiqc/getting_started/running_multiqc).
