# Optional offline Kraken2 evidence

QualiDock can run an explicitly selected **Kraken2** installation and read-only offline reference after QC finishes. This is optional taxonomic screening, not a contamination verdict or a new preprocessing workflow. Nothing is installed/downloaded by the application, no reference is chosen automatically and reads are never uploaded to a third-party service.

## Configure explicit tools and references

Provide a trusted existing Kraken2 executable on PATH or through `QUALIDOCK_KRAKEN2`. Runtime detection accepts the supported 2.x interface (2.1+, below 3); actual regression evidence uses reported version **2.17.1**, source commit `e1a819d985d1a257e20a8fc57eb27a5d51f4c39e`. Unknown versions and incompatible layouts fail clearly. A serial/no-OpenMP build should use one thread.

Set administrator-controlled `QUALIDOCK_SCREENING_DATABASES` to a JSON list of at most 20 explicit references, for example:

```json
[
  {
    "id": "lab-reference",
    "name": "Curated reference for this assay",
    "path": "/persistent/references/kraken2/validated-release",
    "version": "actual-reference-release-or-build-id",
    "source": "actual upstream accession/release/citation",
    "reference_taxids": ["4932"]
  }
]
```

Use actual provenance, not these illustrative strings. The optional taxonomy-ID list is a **declared coverage annotation**, not a verified complete taxonomic inventory. Do not infer that an unlisted taxon is absent. Each reference must contain readable regular `hash.k2d`, `taxo.k2d` and the verified 64-byte `opts.k2d`. Symlink files/escapes and unknown configuration fields are rejected. Reference roots are explicitly administrator-configured read-only resources; the request supplies only a configured database ID, never an arbitrary path.

Database identity/version/source are declarations. SHA-256 for all three actual database files is streamed before every run, with before/after identity checks; these hashes identify the bytes actually used. Hashing a large reference can take substantial I/O time and is cancellable. No full database is read into application memory. Classification uses `--memory-mapping`. Private database locations are omitted from public summary exports; a path-valued source citation is redacted. Protected run-local configuration retains administrator provenance. Review free-text labels/notes before sharing.

Missing tools, references or malformed optional JSON do not break FastQC/MultiQC, historical reports or the core release workflow.

## Use and interpret

Open analysis **Overview & logs → Delivery manifest & yield → Optional offline screening**. Select read files, the known reference and assay context. Optionally annotate exact expected taxonomy IDs. Start explicitly; inspect job state, phase, actual completed-file counts, tool logs, per-file record coverage, database hashes and saved taxonomic tables. Cancel through the same resource-managed subprocess system. Auxiliary screening state is separate from the original QC job state.

Each FASTQ is classified **individually**, including R1/R2 and lane/chunk files. No FASTQ is copied/merged or altered; no paired-fragment or interleaved mode is inferred. Fixed recorded classification parameters are confidence 0, minimum hit groups 2, memory mapping, no subsampling, with threads restricted to the current allocation. These are technical classifier parameters, not biological contamination thresholds.

Only the verified standard six-column Kraken2 report is adapted. Native parsing is capped at 10,000 rows and 32 MiB/report; larger or unsupported reports remain available as original downloads and are not silently truncated into valid results. Original percentages/lexical rows are preserved; clade/direct counts, taxonomy IDs and rank labels come from the tool. Total processed read records use root clade count plus unclassified count. **Clade rows overlap and must not be summed.** Standard omitted zero-count taxa are handled explicitly; a wholly empty report alone does not establish zero reads. MPA-style, minimizer-expanded and multi-database reports need separate verified adapters.

Processed fractions use a current saved FastQC/full-integrity count with an explicit denominator. A missing/incomparable denominator or excess processed count is not evaluated; incomplete coverage is not called complete. Counts are per-read-file records, not pairs or biological sample abundance. Gzip/FASTQ structural integrity is the separate full integrity check; classifier count agreement does not replace it.

Assignments are **preliminary**. Reference composition, conserved sequences, missing taxa and assay/library preparation affect results. Unclassified reads do not establish absence or a clean sample. Expected IDs are exact annotations; there is no automatic lineage inference, species cutoff, sample swap, index-misassignment or contamination diagnosis. FastQC overrepresented sequences remain separate evidence. No AI interpretation, automatic trimming/filtering or release rejection is added.

Search/read-file switching and CSV/TSV exports use persisted data, never another analysis. Generated table exports reuse spreadsheet-safe/verbatim modes; original TSV downloads preserve the original bytes. Scientific QC charts, pairing and MultiQC/report viewing remain unchanged.

## Persistence, review and privacy

Each immutable task directory under the existing owned run contains configuration, logs, original per-file TSV, parsed JSON and a final task record. The manifest retains reported tool version, declared reference provenance, actual database hashes, parameters, Unix requester/time, execution exit/resource observations, file/source identities and coverage. Per-read IDs/classification output are discarded with `--output /dev/null`; no raw FASTQ copy is produced. Completed records/tables reopen after restart even when the tool/reference is currently unavailable. Active tasks are marked interrupted; failed/cancelled work is never a clean result.

Screening evidence is informational by default. An explicitly configured release check can require current full record coverage/provenance for every selected file; that check means **evidence available**, not contamination clearance. Missing screening does not block other contracts. New/stale evidence invalidates old review fingerprints. Rule evaluator 1.1 includes this evidence; earlier evaluator decisions can require explicit rereview after upgrade. Source integrity remains independently mandatory and nonwaivable.

Reference-only bundles include the selected screening summary and tool/database provenance. With explicit original-report inclusion, selected TSV/parsed JSON artifacts are byte-preserved; internal configuration is not bundled. Source-file changes are checked by current metadata and remain subject to the checksum/signature limitations described in [release review](RELEASE-REVIEW.md).

Authenticated endpoints:

- `GET /api/screening` — runtime tool and configured-reference availability.
- `POST /api/runs/{id}/screening` — `file_ids`, configured `database_id`, bounded `threads`, optional `assay` / `expected_taxids`.
- `POST /api/runs/{id}/screening/cancel`.
- `GET /api/runs/{id}/screening-metrics?file_id=...` — only a saved registered file result for that analysis.

Existing authentication, CSRF/origin checks, registered downloads, ownership locks, shared executor slot, resource guardian and proxy-relative URLs apply unchanged. Newline filenames are explicitly unsupported because of the external tool's decompression wrapper; spaces/shell punctuation are validated by genuine execution tests.

## Reproducible small validation

`backend/tests/fixtures/screening` contains pinned NCBI-derived viral reference files from Kraken2's official test corpus, frozen **simulated** viral reads and a genuine captured tool report, with hashes/provenance. It also contains the first 100 unchanged paired records from the already chrI-filtered/subsampled public nf-core SRR6357070 yeast RNA-seq fixture. These subsets are not a whole-experiment or assay-wide contamination benchmark. The viral-only reference is intentionally **not a production database** and does not establish yeast/human/microbial coverage.

With an existing tool installation, explicitly build the small offline test reference (new output directory only):

```sh
python scripts/prepare-screening-test-db.py \
  --kraken2-dir /path/to/existing/kraken2/bin \
  --output /canonical/new-test-reference
```

This helper performs no downloads/tool installation. It records a deterministic one-thread, no-masking, subblock-8192 fixture variant and its actual binary database hashes. The application never builds databases. `scripts/setup-screening-ci.sh` is a separate **explicit isolated CI/development bootstrap**: it downloads checksum-pinned source, compiles into a new temporary directory, builds this fixture and sets only the CI test environment. It never runs at application startup or changes the system PATH.

Real validation runs actual FastQC/Kraken2 on simulated and experimental reads, compares each saved TSV byte-for-byte with an independently executed official command, checks database/source hashes, shell-punctuation safety, partial failure/cancellation, allocation bounds, restart and authenticated metrics. CI requires the actual tools/reference for this target and exercises native browser interaction on standalone and proxy-prefixed routes. These tests establish adapter fidelity on small inputs, not a universal contamination sensitivity/specificity, large-database throughput or HPC-site acceptance.
