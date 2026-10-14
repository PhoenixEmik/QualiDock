# Validation and release gate

This repository is an MVP development implementation, not a validated v0.1.0 release.

## Local verification record — 2026-10-14

- **29 backend tests passed** on Python 3.13 in the managed macOS workspace. QC orchestration used real fixture subprocesses. The macOS RSS sampler was replaced in tests because the sandbox denies `ps`; separate tests exercise Linux `/proc` parsing and the over-budget termination response.
- OOD ERB templates rendered, submission YAML parsed, CPU/memory values matched the requested PBS allocation, invalid PBS tokens were rejected, and rendered launch scripts passed `bash -n`.
- Python sources compiled successfully. On the follow-up local-run request, the real frontend dependencies were downloaded through permitted `curl` calls, verified against lockfile integrity hashes, and installed with `npm ci --offline`. The full TypeScript and Vite production build **passed**, including the real ECharts dependency. A reproducible `frontend/package-lock.json` is now present.
- FastAPI served the production HTML and all referenced JS/CSS assets successfully through TestClient. Earlier temporary UI-check stubs were discarded; the production build contains real ECharts.
- Browser QA was unavailable: no browser providers were connected, and the sandbox rejected binding the local server port.
- The real-tool smoke test stopped with a clear missing-FastQC message. Neither FastQC nor MultiQC was available. Generic dependency-manager network access was blocked, although permitted `curl` downloads enabled the frontend installation. Standalone Linux and HPCF3 tests were not run.
- Git metadata could not be initialized because the workspace denies writes to `.git`. Source, CI configuration, and deployment templates are present; no commit or release was created.

## Automated coverage

Backend tests execute fixture QC tools as actual child processes through LocalExecutor. They cover file pairing, missing mates, traversal, escaped symlinks, authentication/cookie/CSRF boundaries, unauthorized downloads, opaque HTML attachments, all three modes, partial and failed execution, exact parsed quality statistics, immutable original FASTQ inputs, cancellation, process-group cleanup, resource validation, persistent restart recovery, exclusive output ownership, artifact substitution, malformed metrics, ZIP non-extraction, and proxy prefixes.

The managed macOS development sandbox denies `ps`, so its backend tests replace only the RSS sampler with deterministic readings. Linux tests use the native `/proc` sampler. Fixture QC executables validate orchestration, not FastQC/MultiQC's scientific behavior. Real-tool acceptance is a separate smoke script and CI job.

## Required before release

- [x] Frontend TypeScript and Vite production build with the real ECharts dependency.
- [ ] Browser QA of all five views, authentication, live SSE, downloads, and mobile layout.
- [ ] Linux backend suite with real process and resource monitoring.
- [ ] Real FastQC 0.12.1 + MultiQC end-to-end smoke on standalone Linux.
- [ ] Accurate native chart comparison to official FastQC data, including grouped bases and quartiles.
- [ ] HPCF3 site configuration and end-to-end acceptance under the actual OOD reverse proxy.
- [ ] Large-file cancellation, memory-limit failure, graceful shutdown, and abrupt-session interruption on Linux/PBS.
- [ ] Historical reports restored after an OOD restart from persistent storage.
- [ ] Traversal, symlink escape, unauthenticated download, and command-injection checks in both deployment environments.

FastQC's documented per-base chart uses a median, interquartile box, 10th/90th percentile whiskers and mean line; QualiDock preserves those values rather than inferring new quality statistics. See [the official FastQC interpretation](https://www.bioinformatics.babraham.ac.uk/projects/fastqc/Help/3%20Analysis%20Modules/2%20Per%20Base%20Sequence%20Quality.html). MultiQC runs with an explicit output directory and JSON data output, following [its CLI documentation](https://docs.seqera.io/multiqc/getting_started/running_multiqc).
