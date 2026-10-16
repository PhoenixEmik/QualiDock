import test from "node:test";
import assert from "node:assert/strict";
import { fixture } from "./fastqcFixture.ts";
import { confirmedPairs } from "../src/pairing.ts";
import { analyticsSamples } from "../src/analytics.ts";
import { sampleSource, sampleLabel } from "../src/sampleIdentity.ts";
import type { Run } from "../src/types.ts";

test("same-basename reads retain exact report/source mapping and two independent pairs", () => {
  const a = fixture("R1"),
    b = fixture("R2");
  const samples = [
    { ...a, id: "fastqc/i_a/coverage_R1_fastqc.zip" },
    { ...b, id: "fastqc/i_b/coverage_R2_fastqc.zip" },
    { ...a, id: "fastqc/i_c/coverage_R1_fastqc.zip" },
    { ...b, id: "fastqc/i_d/coverage_R2_fastqc.zip" },
  ];
  const paths = samples.map(
    (sample, i) => `/data/study_${Math.floor(i / 2)}/${sample.name}`,
  );
  const mapping = Object.fromEntries(
    samples.map((sample, i) => [
      sample.id,
      {
        path: paths[i],
        id: `i_identity_${i}`,
        multiqc_name: `i_${i} | coverage_R${(i % 2) + 1}`,
      },
    ]),
  );
  const run = {
    id: "analysis",
    inputs: paths,
    report_input_map: mapping,
    input_pairing: paths.map((path, i) => ({
      path,
      name: samples[i].name,
      read: i % 2 ? "R2" : "R1",
      pair_key: `pair_${Math.floor(i / 2)}`,
      paired: true,
      mate: paths[i % 2 ? i - 1 : i + 1],
    })),
  } as Run;
  assert.equal(confirmedPairs(run, samples).length, 2);
  assert.deepEqual(
    samples.map((sample) => sampleSource(run, sample)),
    paths,
  );
  assert.equal(
    new Set(samples.map((sample) => sampleLabel(run, sample, samples))).size,
    4,
  );
  const entities = analyticsSamples(run, samples, {
    columns: [],
    rows: samples.map((s, i) => ({
      sample: mapping[s.id].multiqc_name,
      values: { count: i },
    })),
  });
  assert.equal(entities.length, 4);
  assert.deepEqual(
    entities.map((e) => e.source),
    paths,
  );
  assert.equal(new Set(entities.map((e) => e.multiqcName)).size, 4);
  assert.equal(
    confirmedPairs({ ...run, report_input_map: undefined }, samples).length,
    0,
    "old ambiguous names must not be guessed",
  );
  assert.equal(
    sampleSource(
      {
        ...run,
        report_input_map: {
          [samples[0].id]: { path: "/unselected", id: "bad" },
        },
      },
      samples[0],
    ),
    undefined,
  );
});
