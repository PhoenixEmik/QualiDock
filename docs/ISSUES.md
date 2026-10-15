# Issue validation record — 2026-10-15

| Issue | Result | Evidence / remaining requirement |
|---|---|---|
| [#1](https://github.com/PhoenixEmik/QualiDock/issues/1) MultiQC statistics | Fixed | Supports list and section-keyed 1.x schemas; explicit missing/empty/unsupported/invalid states; actual combined/imported runs pass. |
| [#2](https://github.com/PhoenixEmik/QualiDock/issues/2) Genuine regression fixtures | Fixed | Actual 1.25.1 and 1.35 output subsets with hashes/provenance; normal parser tests need no tools; fixed and latest-1.x compatibility CI. |
| [#3](https://github.com/PhoenixEmik/QualiDock/issues/3) Linux lifecycle/resources | Validated | Actual Java/MultiQC under UID 1001 and a 1 CPU / 1 GiB cgroup; native RSS overrun, cancellation, queue recovery, guardian and restart checks. See [record](LINUX-VALIDATION.md). |
| [#4](https://github.com/PhoenixEmik/QualiDock/issues/4) OOD/PBS site acceptance | Pending external environment | Generic adapter and acceptance/troubleshooting instructions ready. Requires an actual authorized site, configuration and allocation; no site validation claimed. |
| [#5](https://github.com/PhoenixEmik/QualiDock/issues/5) Large FASTQ benchmark | Pending actual data/storage | Private benchmark command and [procedure](BENCHMARKING.md) ready and smoke-tested on real small FastQC input. Requires authorized large FASTQ and real shared-storage observations. |
| [#6](https://github.com/PhoenixEmik/QualiDock/issues/6) Directory performance | Fixed and locally benchmarked | Bounded sorted name snapshots, page/mate metadata reads, stale-page rejection, complete pairing index and regressions. [100,000-name comparison](BROWSING.md); actual NFS/Lustre measurements remain site work. |
| [#7](https://github.com/PhoenixEmik/QualiDock/issues/7) v0.1.0 release | Pending acceptance | [Release notes/procedure and rollback](RELEASING.md) prepared. Site, large-input and live browser acceptance are still required; development versions retained, no release/tag created. |

## Passing Linux CI evidence

- [38699403039](https://github.com/PhoenixEmik/QualiDock/actions/runs/38699403039):
  fixed MultiQC 1.25.1 and 1.35, latest-supported 1.x, actual combined and saved-run
  aggregation, and genuine fixture capture all passed; backend/frontend passed.
- [38700739334](https://github.com/PhoenixEmik/QualiDock/actions/runs/38700739334):
  those checks plus actual Linux cgroup/process validation all passed.
- [38701011932](https://github.com/PhoenixEmik/QualiDock/actions/runs/38701011932):
  all checks passed with the directory browsing changes and regressions.

The `multiqc-*-evidence` artifacts preserve official synthetic reports/structured
outputs and provenance. `linux-resource-evidence` contains actual environment,
process and resource records. Patient data and secrets were not used.

Local final code checks: **103 backend tests passed, one real-MultiQC test skipped
because it is absent locally; 39 frontend tests passed; production build passed.**
Real MultiQC and native Linux resource checks were executed in the linked CI,
not inferred from the local test skip. The benchmark command additionally receives
an actual small-FastQC smoke in the Linux validation job.

- [38701507171](https://github.com/PhoenixEmik/QualiDock/actions/runs/38701507171):
  all checks passed again, including the actual small-FastQC smoke of the private
  benchmark command under Linux/cgroup limits.

## Root causes and scope

MultiQC 1.35 replaced list-based General Statistics with section-keyed objects.
The former parser silently returned an empty result for those valid objects.
The fix preserves original values/column metadata in both formats and does not
weaken the two-sample real-tool assertion. Legitimate emptiness now has an explicit
status/message in API and Reports, separate from missing or malformed data.

Large directory responses used to run a full resolve/stat/sort pass for every
page. The replacement retains bounded names/pairing indexes, rechecks containment
and page/mate metadata, and uses generation tokens to avoid mixing filesystem
states. It intentionally documents initial O(n) indexing and cache limits rather
than claiming unbounded constant-time shared-filesystem browsing.

The resource pass also fixed detection of nested cgroup/ancestor CPU and memory
limits. Application measurements remain sampled; kernel/scheduler limits are the
hard boundary. A truly truncated FASTQ is used for malformed-input validation;
FastQC 0.13.0 accepts some unequal sequence/quality lengths, so those were not
falsely asserted to be an upstream execution failure.

## Remaining inputs

For #4/#5, provide an authorized SSH/OOD environment, site cluster/queue/module
settings, persistent private results location, and actual FASTQ paths. Do not
publish passwords, session tokens, protected reads or private identifiers.
Until those observations and browser acceptance are recorded, #4/#5/#7 remain
open and v0.1.0 is not published. QualiDock remains a general HPC platform; no
particular cluster's configuration or unmeasured defaults are built into the core.
