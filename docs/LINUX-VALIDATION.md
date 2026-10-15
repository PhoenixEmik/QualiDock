# Actual Linux process and resource acceptance

The test-only `scripts/linux-validation.Dockerfile` and
`scripts/validate-linux-execution.py` run the existing production executor and
manager with actual FastQC/Java/MultiQC. They do not replace the RSS sampler,
CPU affinity, guardian, QC executables or persisted results with mocks.

## Recorded result — 2026-10-15

[Successful CI run 38700739334](https://github.com/PhoenixEmik/QualiDock/actions/runs/38700739334),
`linux-resources` job:

- Linux kernel `6.17.0-1022-azure`, x86_64, glibc 2.36; UID **1001**.
- Docker cgroup v2: **1 CPU quota, 1,024 MiB memory**, no extra capabilities,
  no-new-privileges, and no swap allowance beyond the memory limit.
- Container affinity initially exposed CPUs 0–3; each observed worker, Java and
  MultiQC process in the analysis group was constrained to the requested **one
  CPU** by the production worker. Thread library limits remained enabled.
- Actual FastQC **0.13.0** and MultiQC **1.35**.
- Cancelled FastQC/Java; no live group members remained and the queued following
  FastQC run completed with real reports.
- Cancelled actual MultiQC; no live group members remained and parsed FastQC
  results were retained.
- FastQC rejected a genuinely truncated FASTQ; the run was failed with exit 1
  and missing-output diagnostics. Previously completed results were unaffected.
- A separate, bounded Python process deliberately allocated 192 MiB against a
  **64 MiB** process-group budget. The native `/proc` sampler observed
  **221,966,336 bytes**, terminated it with recorded code **137** after about
  **0.506 s**, and a following process ran successfully.
- Graceful shutdown marked running and queued analyses interrupted. Restart
  preserved a completed run and correctly restored interrupted history.
- Killing a separate server parent while actual Java was running activated the
  worker guardian. No live group members remained; restart marked its run
  interrupted. Source file metadata and hashes remained unchanged.

The workflow artifact `linux-resource-evidence` contains the kernel/cgroup record,
process IDs and affinities, sampled RSS, execution parameters, manifests and logs.
Stopped zombie entries may remain until the container's init reaps them; the
validator distinguishes those from live QC processes and records live membership.
The container is removed after validation. CPU/RSS polling is not a substitute
for the kernel cgroup hard boundary, and sampled RSS is not an exact peak.

## Reproduce

On a Linux host with Docker available, from the repository root:

```sh
docker build -f scripts/linux-validation.Dockerfile -t qualidock-linux-validation .
mkdir -p validation/linux
# The image runs UID 1001. Ensure the test-owned evidence directory is writable
# by that UID; do not alter permissions of production result directories.
docker run --rm --cpus=1 --memory=1g --memory-swap=1g \
  --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$PWD/validation/linux:/evidence" qualidock-linux-validation
```

Alternatively, run the validator under an ordinary account in an existing Linux
allocation with the tools installed. It creates/removes only its own temporary
synthetic inputs and result store and preserves its evidence under `--output`.
The Dockerfile is for testing; standalone deployment does not require Docker.

## Boundaries of this evidence

This validates application lifecycle and cgroup enforcement on Linux. It does
not establish PBS/OOD proxy behavior, NFS/Lustre performance, an 80 GB analysis,
or live browser acceptance on a particular HPC installation. Those remain the
separate site and large-input gates. The macOS managed sandbox still denies its
native `ps` subprocess; local test-only substitution is not counted as Linux
resource evidence.
