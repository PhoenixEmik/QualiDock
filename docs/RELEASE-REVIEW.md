# Assay rules, review and reference bundles

Open **Overview & logs → Delivery manifest & yield → Release review & reference bundle**. This adds an auditable handoff workflow to one analysis, without modifying FastQC/MultiQC output, introducing a database or copying FASTQs.

## Explicit policy and sample scope

Select whole saved sample groups; file/lane identity is retained. Configure a nonempty assay/project label and policy version. Each save creates an immutable policy sidecar and advances the configuration revision, even if the same version text is reused. An RNA-seq, WGS or amplicon contract can require source integrity, independent expected-file reconciliation and its own explicit quantity minima; thresholds come from the actual agreement, never a universal built-in yield/Q30 cutoff. Illumina evidence is optional unless explicitly required.

Supported required checks:

- **Integrity** is always required and cannot be waived. Every selected source needs full current structural/hash evidence; configured mates need matching count and identifier-order evidence. The scan task must have completed. Failed, cancelled, interrupted or stale evidence cannot authorize a complete bundle. A completed scan with failures in excluded groups can still establish the independently successful selected groups.
- **Expected delivery** uses exact independent expectations, including supplied counts/hashes. Rows attributable to excluded groups are excluded; missing expectations whose scope is unknown remain visible for explicit review. Absent expectations are not evaluated.
- **Quantity** requires a saved, comparable explicit minimum for every selected group. Reads, read pairs and bases retain their separate definitions. High Q30 does not compensate for insufficient yield.
- **Demultiplexing** requires supported SampleSheet/statistics reconciliation **and** unique explicit FASTQ-list associations for every selected input. A genuine report from another experiment, or a matching sample sheet without downstream file associations, cannot silently satisfy this check. Reported/declared versions stay separate.

FastQC classifications remain informational by default. Optional explicit module rules can require particular original PASS/WARN/FAIL statuses. A missing/disabled module or an unverified historical input snapshot is not evaluated, even if its summary happens to say PASS. Permitting a status in a contract does not change the official module classification. RNA-seq, amplicon, targeted and methylation-related assays can have protocol-specific profiles; warnings are not automatic instructions to trim/discard reads. Optional [offline Kraken2 screening](OFFLINE-SCREENING.md) remains not evaluated until explicitly requested. A configured required screening check establishes current evidence/provenance availability, never contamination clearance. Rule evaluator 1.1 includes that evidence; earlier decisions can require explicit rereview.

## Readiness and human decisions

No policy means **review required**. A nonpassing/unevaluated required check means **blocked** unless it has a current, reasoned waiver. All required checks passing or explicitly waived means **ready**. Informational FastQC warnings alone do not block readiness. Readiness is separate from approval: no human decision is invented.

Record **needs review**, **block**, **approve**, or **waive one required rule**. A reason is mandatory. Integrity cannot be waived; approval is refused while required checks remain blocked. Events retain the actual Unix UID/user, timestamp, scope, reason and evidence fingerprint. An optional reviewer label is self-declared: the current single-user authentication does not establish separate human identities behind a shared Unix account.

Fingerprints cover selected identities/current file metadata, source checksums, saved QC metric content, original-report metadata, tool/execution provenance, policy/configuration revisions and imported demultiplex evidence. Changes make previous decisions/waivers stale. Reverting A → B → A does not revive an old approval because configuration revisions advance. Review/history sidecars do not invalidate their own decisions. A stale browser submission is rejected; **Refresh release evidence** checks externally changed files without rerunning QC.

Filesystem freshness uses metadata plus the previously completed full source digest; this is not a tamper-proof signature against a malicious user who can rewrite their own files/manifests and forge timestamps. Revalidate after source changes, and verify checksums independently after transfer.

## Reference-only bundle

Export runs as a cancellable, resource-limited LocalExecutor task through the existing shared execution slot. Full FASTQ checksums are computed by the existing streaming integrity worker; the exporter reuses that verified evidence and rechecks its current scope before and after packaging. It does not rescan source FASTQs merely to change views or copy them into a ZIP.

A current explicit approval plus ready policy produces an **approved** bundle. Otherwise a complete-hash diagnostic export is prominently **review_required**. Incomplete hashing cannot produce either complete bundle. Missing/cancelled exports never become registered ZIP downloads; restart marks active exports interrupted. Original analyses/reports remain intact.

The ZIP contains:

- CSV/JSON file manifest, selected per-group quantities, source SHA-256 and logical relative FASTQ references.
- Exact saved native FastQC module data for selected files, without combining scientific distributions.
- Tool versions, execution settings, declared raw/processed stage and upstream adapter/UMI notes.
- Versioned policy, review decision, exceptions/waivers and history for that scope.
- A static, escaped human-readable HTML review and README.
- `checksums.sha256` for referenced FASTQs and bundled metadata/reports, excluding the checksum file itself.

After independently transferring FASTQs into the logical locations in the manifest, run `sha256sum -c checksums.sha256` at the destination. Until then, missing referenced FASTQs are expected. Source checksum computation is **not** post-transfer verification or proof of biological sample identity. The complete ZIP SHA-256 is recorded separately in QualiDock.

Original reports are an explicit opt-in acknowledgment because unchanged FastQC/MultiQC HTML/structured outputs can contain private upstream paths and, for combined reports, excluded samples. Their original bytes are preserved. Default packages omit these originals and absolute input paths. A separate explicit option includes private input paths. Free-text assay/sample names, reviewer reasons and processing notes are preserved; review them before sharing. CSV defaults to spreadsheet-safe text escaping with an explicit verbatim option.

Artifacts stream in 1 MiB chunks with containment, regular-file and pre/post metadata checks. Portable archive names use stable namespaces; traversal, symlinks, alternate streams and collisions are rejected. Source FASTQs are never modified. A 2 GiB original-report limit and an available-space check bound initial export scope; omit originals for larger report sets. Metadata and final ZIP checksums use bounded streaming I/O. Partial worker files can remain on disk for diagnosis, but are unregistered; there is no implicit deletion/retention policy.

Repeated exports of the same scientific/review snapshot use canonical JSON, fixed ZIP timestamps and stable names. Tests verify identical bytes on the same runtime; this is not a claim of identical compression bytes across Python/zlib implementations. These JSON/checksum records are not cryptographic signatures.

## API and compatibility

Authenticated endpoints, using existing CSRF/request-header protections:

- `POST /api/runs/{id}/release-policy`
- `POST /api/runs/{id}/release-review/evaluate` (read-only evaluation, body `sample_ids`)
- `POST /api/runs/{id}/release-review` (current fingerprint, action, reason, optional rule/label)
- `POST /api/runs/{id}/release-exports` (current fingerprint/scope and explicit inclusion options)
- `POST /api/runs/{id}/release-exports/cancel`

Downloads use the unchanged registered attachment endpoint. API/UI paths retain reverse-proxy prefix compatibility. Existing analyses without optional policy/review/export metadata remain readable and unapproved. Historical QC without a verified input snapshot remains inspectable, but cannot silently establish current release evidence. No OOD/PBS executor, new processing engine, authentication redesign or destructive cleanup is introduced.
