import test from "node:test";
import assert from "node:assert/strict";
import {
  defaults,
  isProcessing,
  retention,
  downloadDataset,
  processingModes,
  publishedDatasets,
  selectedReferences,
} from "../src/processing.ts";
test("processing modes and defaults stay independent from QC", () => {
  assert.ok(processingModes.every(isProcessing));
  assert.equal(isProcessing("both"), false);
  assert.deepEqual(defaults("fastp"), {
    adapter_trimming: true,
    quality_filtering: true,
    qualified_quality: 15,
    unqualified_percent: 40,
    min_length: 15,
    gzip: true,
    compare_qc: true,
    multiqc: false,
  });
  assert.equal(defaults("seqkit-sample").seed, 11);
});
test("retention derives only from explicit compatible reported counts", () => {
  assert.deepEqual(retention(400, 300), { retained: 75, removed: 25 });
  for (const [a, b] of [
    [0, 0],
    [undefined, 1],
    [10, 11],
    [10, -1],
    [NaN, 1],
  ])
    assert.equal(retention(a, b), null);
});
test("derived downloads preserve exact identities and escape paths", () => {
  const href = downloadDataset(
    { id: "a".repeat(32) },
    "processing/u0001/a & b.fastq.gz",
  );
  assert.equal(
    new URL(href, "https://localhost/").searchParams.get("path"),
    "processing/u0001/a & b.fastq.gz",
  );
});

import { fixture } from "./fastqcFixture.ts";
import { confirmedPairs } from "../src/pairing.ts";
import { analyticsSamples } from "../src/analytics.ts";
import { sampleSource, sampleLabel } from "../src/sampleIdentity.ts";
import type { Run } from "../src/types.ts";
test("declared raw and validated processed pairs retain distinct stage identities", () => {
  const raw = [fixture("R1"), fixture("R2")];
  const processed = raw.map((sample, index) => ({
    ...sample,
    id: `fastqc/u0001/processed/processed_R${index + 1}_fastqc.zip`,
    name: `processed_R${index + 1}.fastq.gz`,
  }));
  const paths = raw.map((sample) => `/data/${sample.name}`);
  const run = {
    id: "run",
    inputs: paths,
    output_directory: "/results/run",
    input_pairing: paths.map((path, i) => ({
      path,
      name: raw[i].name,
      read: `R${i + 1}`,
      paired: true,
      mate: paths[1 - i],
      pair_key: "original",
      lane: "L001",
      chunk: "001",
    })),
    sample_groups: [
      { id: "s", display_name: "Coverage", files: paths, source: "auto" },
    ],
    processing: {
      schema_version: 1,
      options: {},
      units: [
        {
          id: "u0001",
          inputs: paths,
          outputs: [],
          state: "completed",
          error: null,
          lane: "L001",
          chunk: "001",
        },
      ],
    },
    derived_datasets: processed.map((sample, i) => ({
      id: `u0001:${i + 1}`,
      unit_id: "u0001",
      path: `processing/u0001/${sample.name}`,
      source: paths[i],
      stage: "processed",
      paired: true,
      read: `R${i + 1}`,
      sha256: "test-only",
      records: 0,
      bases: 0,
    })),
    report_input_map: Object.fromEntries([
      ...raw.map((sample, i) => [
        sample.id,
        { id: `raw${i}`, path: paths[i], processing_stage: "raw" },
      ]),
      ...processed.map((sample, i) => [
        sample.id,
        {
          id: `processed${i}`,
          path: `/results/run/processing/u0001/${sample.name}`,
          processing_stage: "processed",
        },
      ]),
    ]),
  } as Run;
  const all = [...raw, ...processed];
  assert.equal(confirmedPairs(run, all).length, 2);
  assert.match(
    sampleLabel(run, processed[0], all),
    /^Processed · coverage_R1.fastq.gz/,
  );
  assert.equal(
    sampleSource(run, processed[0]),
    "/results/run/processing/u0001/processed_R1.fastq.gz",
  );
  const entity = analyticsSamples(run, all).find(
    (row) => row.id === processed[0].id,
  )!;
  assert.equal(entity.read, "R1");
  assert.equal(entity.groupName, "Coverage");
  assert.equal(entity.lane, "L001");
  run.derived_datasets!.forEach((row) => (row.paired = false));
  assert.equal(confirmedPairs(run, all).length, 1); // independent SeqKit files cannot acquire a pair
});

test("processing downloads require completed or partial analysis, even with staged metadata", () => {
  const dataset = { id: "staged" } as any;
  for (const state of [
    "queued",
    "running",
    "failed",
    "cancelled",
    "interrupted",
  ] as const)
    assert.deepEqual(
      publishedDatasets({ state, derived_datasets: [dataset] }),
      [],
    );
  for (const state of ["completed", "partial"] as const)
    assert.deepEqual(
      publishedDatasets({ state, derived_datasets: [dataset] }),
      [dataset],
    );
});

test("same-basename manual pair labels expose declared read identities", () => {
  // Synthetic filename metadata over genuine FastQC fixture values.
  const samples = [fixture("R1"), fixture("R2")].map((sample, i) => ({
    ...sample,
    id: `fastqc/u0001/raw/i${i}/reads_fastqc.zip`,
    name: "reads.fastq.gz",
  }));
  const paths = ["/left/reads.fastq.gz", "/right/reads.fastq.gz"];
  const run = {
    inputs: paths,
    input_pairing: paths.map((path, i) => ({ path, read: `R${i + 1}` })),
    report_input_map: Object.fromEntries(
      samples.map((sample, i) => [
        sample.id,
        { id: `i${i}`, path: paths[i], processing_stage: "raw" },
      ]),
    ),
  } as Run;
  const labels = samples.map((sample) => sampleLabel(run, sample, samples));
  assert.equal(new Set(labels).size, 2);
  assert.match(labels[0], / · R1 · /);
  assert.match(labels[1], / · R2 · /);
});

test("only selected exact derived identities are sent; paths never grant siblings", () => {
  const references = [
    { run_id: "a", dataset_id: "r1", path: "/results/processed_R1.fastq.gz" },
    { run_id: "a", dataset_id: "r2", path: "/results/processed_R2.fastq.gz" },
  ];
  assert.deepEqual(
    selectedReferences(references, new Set([references[0].path])),
    [{ run_id: "a", dataset_id: "r1" }],
  );
  assert.deepEqual(
    selectedReferences(
      references,
      new Set(["/results/../results/processed_R1.fastq.gz"]),
    ),
    [],
  );
  assert.deepEqual(selectedReferences(references, new Set()), []);
});
