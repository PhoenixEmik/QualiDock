# v0.1.0 release procedure

**Not yet released.** Development versions remain in place until all release
gates have actual evidence. The release target is standalone Linux. CI establishes the recorded automated
behavior, not large-file/shared-storage throughput or a real site deployment.
The retained OOD adapter has a separate, optional acceptance track.

## Required evidence

1. Backend/frontend tests and all fixed/latest-1.x real-QC CI targets pass at the
   intended release commit. Verify actual FastQC-only, combined, imported results,
   reports, security checks and restart persistence.
2. Linux resource/process validation passes under the recorded cgroup limits.
3. Review configured input/output roots, authentication, source immutability,
   derived reuse, cancellation and restart recovery on the standalone target.
4. Scope performance claims to actual observations in `docs/BENCHMARKING.md` and
   issue #5. Large-input/NFS/Lustre acceptance remains pending; do not advertise
   unmeasured throughput or invent CPU/RAM/walltime recommendations.
5. Perform live browser QA: token login/logout, Workspace, pairing and paging,
   changed-directory refresh, Results, Read Processing, all module charts/tables, sample switching,
   collapsed details, logs, cancellation, live SSE, attachment downloads, and
   narrow/mobile layouts. Record browser/version, proxy prefix and any limitations.
6. Review `docs/VALIDATION.md`, `docs/CORE-FIRST.md`, README and the compatibility matrix
   against evidence, plus repository/dependency license notices. Keep protected
   input data, private paths, credentials and downloaded tool binaries out of the
   release source. Test fixtures must retain their public source, license and exact synthetic/experimental derivation provenance.

## Candidate release notes

Supported release target: standalone Linux, Python 3.11+, Java, FastQC 0.13.0
(0.12.1 compatibility retained), MultiQC >=1.25,<2, optional fastp 0.23–1.x and
SeqKit 2.6–2.x. Exact-count sampling requires verified SeqKit 2.14+. Frontend
builds require Node.js 22+. Tools are external installations, never auto-installed.

Features: server-side FASTQ browsing and manual/lane metadata; FastQC-only,
combined and existing-report MultiQC; native module charts/tables and within-run
comparisons; isolated official previews/downloads; fastp and focused SeqKit
processing; synchronized paired filtering/ID extraction and reproducible exact
sampling; registered derived FASTQ reuse; bounded history/SSE updates; read-only
integrity checks; configured output roots and persistent JSON results.

Project catalogs, facility delivery/release review, retention administration and
Kraken2 screening are intentionally absent. Old scientific manifests and registered
artifacts remain readable; see [preservation and legacy export](CORE-FIRST.md).

Known limits: one analysis at a time; bounded directory/import snapshots; observed
MultiQC 1.x General Statistics schemas; an explicit FastQC/fastp import allowlist;
FastQC-configured K-mer availability; and sandboxed report features documented in
[REPORT-VIEWER.md](REPORT-VIEWER.md). RSS enforcement is sampled, with cgroups as
the hard boundary. The full ECharts bundle still emits a Vite size warning.
Large FASTQ/shared-storage performance is not accepted. List exact tested tool
versions and browsers from the candidate CI, rather than extrapolating ranges.

The existing OOD adapter is optional. A site may validate it using [OOD.md](OOD.md)
and issue #4, but its unverified HTTPS/PBS/shared-storage behavior must remain
explicitly separate from standalone acceptance. No scheduler job submission is
provided by the application.

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

Issue #7 tracks standalone candidate review, version alignment and eventual
publication. Issues #4 and #5 separately track site deployment and large-input
observations; they do not establish or silently broaden standalone release claims.
No release tag or publication is authorized by an unverified checklist.
