# v0.1.0 release procedure

**Not yet released.** Development versions remain in place until all release
gates have actual evidence. A green CI run does not establish an actual HPC deployment or large-file performance. Automated real-browser standalone/proxy-prefix acceptance is recorded separately from actual site/HTTPS validation.

## Required evidence

1. Backend/frontend tests and all fixed/latest-1.x real-QC CI targets pass at the
   intended release commit. Verify actual FastQC-only, combined, imported results,
   reports, security checks and restart persistence.
2. Linux resource/process validation passes under the recorded cgroup limits.
3. Complete `docs/OOD.md` site acceptance under the actual HTTPS reverse proxy,
   PBS allocation, installed modules, user identity and NFS/Lustre paths.
4. Complete authorized large-input validation following `docs/BENCHMARKING.md`.
   Record actual observations; do not invent CPU/RAM/walltime recommendations.
5. Perform live browser QA: token login/logout, Workspace, pairing and paging,
   changed-directory refresh, Analyses, all module charts/tables, sample switching,
   collapsed details, logs, cancellation, live SSE, attachment downloads, and
   narrow/mobile layouts. Record browser/version, proxy prefix and any limitations.
6. Review `docs/VALIDATION.md`, `docs/ISSUES.md`, README and the compatibility matrix
   against evidence, plus repository/dependency license notices. Keep protected
   input data, private paths, credentials and downloaded tool binaries out of the
   release source. Test fixtures must retain their public source, license and exact synthetic/experimental derivation provenance.

## Candidate release notes

Supported runtime: standalone Linux or an existing Open OnDemand/OpenPBS compute
allocation, Python 3.11+, Java, FastQC 0.13.0 (0.12.1 compatibility retained), and
MultiQC >=1.25,<2. Frontend builds require Node.js 22+.

Features: server-side paired FASTQ selection; native visualizations/tables for
12 FastQC modules where reported; three QC modes; aggregation from saved results;
version detection; logs/cancellation; isolated official report previews and downloads; native multi-sample analytics; JSON persistence; bounded history/directory updates; manual/lane sample metadata; configured output roots; delivery/yield contracts; auditable data-release review and reference bundles; and opt-in offline screening with explicitly configured references.

Known limits: one analysis at a time; directory snapshots cap 200,000 names and
expire after five idle minutes; cold directory indexing is O(n) and can still
incur filesystem metadata reads; native MultiQC summaries cover observed 1.x
General Statistics schemas; QC inputs for aggregation use an explicit FastQC / fastp-JSON allowlist; optional Kraken2 screening requires an existing executable and explicit offline reference, with preliminary assignments rather than a contamination verdict; K-mer
availability follows FastQC configuration. RSS enforcement is sampled; the
scheduler/cgroup remains the hard boundary. The current full ECharts bundle emits
a Vite size warning. Site and browser claims must match the recorded acceptance.

## Versioning, packaging and publication

Only after blockers are resolved:

- Set `pyproject.toml`, `frontend/package.json` and its lockfile, and the FastAPI
  application version to `0.1.0` consistently.
- Rebuild and rerun required CI at that exact commit. Record successful workflow
  links and accepted deployment/benchmark evidence in the release notes.
- Tag `v0.1.0` and create the GitHub Release from the validated commit, including
  supported tools, installation, limitations and upgrade/rollback instructions.
- Repository owners may require CI through branch protection. Do not change
  repository access or protection settings as a side effect of a code fix.

## Upgrade and rollback

1. Stop accepting new work and end the current session normally; verify its QC
   process groups have stopped. Back up the private persistent result store using
   the site's normal snapshot/backup procedure, without duplicating source FASTQs.
2. Install the candidate into a separate versioned software directory with its own
   Python environment and built frontend. Preserve configured input roots and
   persistent output location. Never run two servers on one result store.
3. Start the new version under the same Unix user. Verify historical downloads,
   metrics, authentication, proxy/SSE and one small real analysis before general
   use. Completed version-1 records remain readable without rewriting them.
4. To roll back, stop the new server and switch the installation path to the
   previous tested build. Keep backups intact. Do not rewrite manifests in place
   or downgrade the saved schema blindly; verify the previous build can read a
   copied/snapshotted result store before reusing the production output directory.

Issue #7 remains open while required actual-site/large-input gates lack evidence. Automated real-browser acceptance does not replace those site observations.
No release tag or publication is authorized by an unverified checklist.
