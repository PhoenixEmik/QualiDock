# Issue validation record — 2026-10-16

The software issues are addressed incrementally without replacing working QC execution or report isolation. Individual GitHub issues contain their accepted CI evidence.

| Issues | Implementation / evidence |
|---|---|
| [#8](https://github.com/PhoenixEmik/QualiDock/issues/8), [#9](https://github.com/PhoenixEmik/QualiDock/issues/9) | Collision-safe report namespaces, exact input mappings and actual per-file outcomes, including partial/cancelled batches. |
| [#10](https://github.com/PhoenixEmik/QualiDock/issues/10) | Explicit spreadsheet-safe versus exact verbatim CSV/TSV exports; original reports remain unchanged. |
| [#11](https://github.com/PhoenixEmik/QualiDock/issues/11) | Bounded history pages, revision-only live updates, reconnect/polling and measured browser/API payload reductions. See [history evidence](HISTORY.md). |
| [#12](https://github.com/PhoenixEmik/QualiDock/issues/12) | Bounded fastp JSON report imports through real MultiQC, without running fastp or inventing FastQC modules. |
| [#13](https://github.com/PhoenixEmik/QualiDock/issues/13) | Full/quick streaming source/gzip/FASTQ validation, exact mate count/order evidence, source hashes and cancellation/restart provenance. |
| [#14](https://github.com/PhoenixEmik/QualiDock/issues/14), [#15](https://github.com/PhoenixEmik/QualiDock/issues/15) | Stable delivery inventory, independent expected-file reconciliation, explicit sample quantity contracts and actual denominator-qualified Q20/Q30. |
| [#16](https://github.com/PhoenixEmik/QualiDock/issues/16) | Byte-preserved Illumina SampleSheet / BCL Convert 3.6.3 and 3.9.3 evidence, exact index/lane reconciliation and explicit FASTQ-list associations. |
| [#17](https://github.com/PhoenixEmik/QualiDock/issues/17), [#18](https://github.com/PhoenixEmik/QualiDock/issues/18) | Versioned assay rules, reasoned review/waivers, stale evidence detection, and cancellable reference-only bundles with complete source checksums and explicit privacy controls. |
| [#19](https://github.com/PhoenixEmik/QualiDock/issues/19) | Opt-in offline Kraken2 adapter with explicit configured references, streamed database hashes, actual record coverage, saved taxonomic tables and preliminary interpretation. Genuine local tool tests use official simulated and public experimental reads; CI requires the pinned real tool/reference and browser interactions. See [screening](OFFLINE-SCREENING.md). |

Fully green validation at [`78ae750`](https://github.com/PhoenixEmik/QualiDock/actions/runs/38846841711) covers #8–#18: backend/frontend/build, fixed/latest MultiQC real-tool compatibility, Linux resource validation and all existing headless browser cases on standalone, `/node` and `/rnode` URLs. New optional screening validation is enforced by the same workflow; final accepted results are linked from #19.

Local checks after the screening integration: **258 backend tests passed**, including actual FastQC/Kraken2 execution; **138 frontend tests passed** and the production build passed. Later focused checks cover source/task identity and original-report fallback. The managed macOS test harness substitutes only the denied RSS sampler; Linux CI uses the real resource observer. No local GUI/server acceptance is inferred from those unit tests.

## External release gates

- [#4](https://github.com/PhoenixEmik/QualiDock/issues/4): actual authorized OOD/PBS allocation, HTTPS/session behavior and shared-filesystem acceptance. Proxy-prefixed loopback browser tests are not an actual site deployment.
- [#5](https://github.com/PhoenixEmik/QualiDock/issues/5): actual large FASTQ input and representative shared storage. Small public/simulated fixtures and tiny offline references cannot establish 80 GB throughput or site resource defaults. The [benchmark procedure](BENCHMARKING.md) and private evidence script are ready.
- [#7](https://github.com/PhoenixEmik/QualiDock/issues/7): software v0.1.0 publication remains gated on those observations. No tag/release was created. Development versions are retained.

The application remains independent of any particular HPC installation. Existing generic deployment adapters are retained; no scheduler submission adapter or site-specific change was introduced.

---

# Historical validation record — 2026-10-15

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

Local checks at that historical snapshot: **103 backend tests passed, one real-MultiQC test skipped
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
