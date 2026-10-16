import test from "node:test";
import assert from "node:assert/strict";
import type { SampleConfiguration, Entry, Run } from "../src/types.ts";
import {
  assignPair,
  removePair,
  moveToGroup,
  reconcileConfig,
} from "../src/sampleConfig.ts";
import { explorerRows, rowInputPaths, explorerLanes } from "../src/explorer.ts";
import { analyticsSamples } from "../src/analytics.ts";
import { confirmedPairs } from "../src/pairing.ts";
import { fixture } from "./fastqcFixture.ts";
const paths = [
  "/data/facility forward.fastq.gz",
  "/data/facility reverse.fastq.gz",
  "/data/another.fastq.gz",
];
const config = (): SampleConfiguration => ({
  input_pairing: paths.map((path) => ({
    path,
    name: path.split("/").pop()!,
    read: null,
    paired: false,
    pair_key: null,
    mate: null,
    source: "auto",
    assignment: "unpaired",
  })),
  sample_groups: paths.map((path, i) => ({
    id: `g${i}`,
    display_name: `Group ${i}`,
    files: [path],
    source: "auto",
  })),
});
test("manual nonstandard pair is mutual, exact, stable, and moves both files to the R1 sample", () => {
  const before = config(),
    after = assignPair(
      before,
      "manual:pair",
      paths[0],
      paths[1],
      "L001",
      "001",
    );
  assert.equal(before.input_pairing[0].paired, false);
  assert.equal(after.input_pairing[0].read, "R1");
  assert.equal(after.input_pairing[1].read, "R2");
  assert.equal(after.input_pairing[0].mate, paths[1]);
  assert.equal(after.input_pairing[0].source, "manual");
  assert.equal(after.input_pairing[0].lane, "L001");
  assert.deepEqual(after.sample_groups[0].files, paths.slice(0, 2));
  assert.equal(after.sample_groups.length, 2);
});
test("self-pairs, unselected inputs and conflicting assignments are rejected", () => {
  assert.throws(
    () => assignPair(config(), "p", paths[0], paths[0], null, null),
    /different/,
  );
  assert.throws(
    () => assignPair(config(), "p", paths[0], "/unknown.fastq", null, null),
    /unselected/,
  );
  const paired = assignPair(config(), "p", paths[0], paths[1], null, null);
  assert.throws(
    () => assignPair(paired, "other", paths[1], paths[2], null, null),
    /another pair/,
  );
});
test("cross-group manual pairing updates affected group provenance only", () => {
  const before = config();
  const fourth = "/data/fourth.fastq.gz";
  before.input_pairing.push({
    ...before.input_pairing[2],
    path: fourth,
    name: "fourth.fastq.gz",
  });
  before.sample_groups[1].files.push(fourth);
  const paired = assignPair(
    before,
    "manual:cross-group",
    paths[0],
    paths[1],
    null,
    null,
  );
  assert.deepEqual(paired.sample_groups[1].files, [fourth]);
  assert.equal(paired.sample_groups[1].source, "manual");
  assert.equal(paired.sample_groups[2].source, "auto");
  const moved = moveToGroup(before, paths[0], "g1");
  assert.equal(
    moved.sample_groups.find((g) => g.id === "g1")!.source,
    "manual",
  );
  assert.equal(moved.sample_groups.find((g) => g.id === "g2")!.source, "auto");
});
test("remove and reassign a pair without renaming or modifying source references", () => {
  const removed = removePair(
    assignPair(config(), "p", paths[0], paths[1], null, null),
    "p",
  );
  assert.ok(removed.input_pairing.every((r) => !r.paired));
  const next = assignPair(removed, "new", paths[1], paths[0], null, null);
  assert.equal(next.input_pairing.find((r) => r.path === paths[1])!.read, "R1");
});
test("moving a pair preserves both read identities; partial removal leaves an unpaired read", () => {
  const paired = assignPair(config(), "p", paths[0], paths[1], "L002", "002");
  const moved = moveToGroup(paired, paths[0], "g2");
  assert.deepEqual(moved.sample_groups[0].files, [
    paths[2],
    paths[0],
    paths[1],
  ]);
  assert.equal(moved.input_pairing[0].read, "R1");
  const partial = reconcileConfig(paired, [paths[0], paths[2]]);
  assert.equal(partial.input_pairing[0].paired, false);
  assert.equal(partial.input_pairing[0].mate, null);
  assert.deepEqual(
    partial.sample_groups.flatMap((g) => g.files).sort(),
    [paths[0], paths[2]].sort(),
  );
});
const entry = (lane: string, read: 1 | 2): Entry => ({
  path: `/data/C15_S1_${lane}_R${read}_001.fastq.gz`,
  name: `C15_S1_${lane}_R${read}_001.fastq.gz`,
  kind: "fastq",
  size: 123,
  modified: 1,
  read: `R${read}`,
  paired: true,
  mate: `/data/C15_S1_${lane}_R${read === 1 ? 2 : 1}_001.fastq.gz`,
  pair_key: `/data/C15_S1_${lane}_001`,
  sample_key: "/data/C15_S1",
  sample_name: "C15",
  lane,
  chunk: "001",
});
test("multi-lane explorer groups samples, preserves individual lanes, and selects unseen pages", () => {
  const entries = [
    entry("L001", 1),
    entry("L001", 2),
    entry("L002", 1),
    entry("L002", 2),
  ];
  const [row] = explorerRows(entries, "samples");
  assert.equal(row.name, "C15");
  assert.equal(row.files.length, 4);
  assert.equal(explorerLanes(row).length, 2);
  assert.equal(row.pairing, "Paired-end");
  assert.deepEqual(
    rowInputPaths(row),
    entries.map((e) => e.path),
  );
  assert.equal(explorerRows(entries, "files").length, 4);
  const [page] = explorerRows([entries[0]], "samples", {
    "/data/C15_S1": { paths: entries.map((e) => e.path), total: 4 },
  });
  assert.deepEqual(
    rowInputPaths(page),
    entries.map((e) => e.path),
  );
});
test("different directories and ambiguous names stay independent; incomplete lanes remain visible", () => {
  const first = entry("L001", 1),
    second = { ...entry("L002", 1), paired: false, mate: null };
  const [row] = explorerRows([first, second], "samples");
  assert.equal(row.pairing, "Incomplete pair");
  assert.equal(explorerLanes(row)[1].incomplete, true);
  assert.equal(
    explorerRows(
      [
        first,
        { ...first, path: "/other/a.fastq", sample_key: "/other/C15_S1" },
      ],
      "samples",
    ).length,
    2,
  );
  assert.equal(
    explorerRows(
      [
        { ...first, ambiguous: true },
        { ...second, ambiguous: true },
      ],
      "samples",
    ).length,
    2,
  );
});

test("saved manual pairing and sample/lane metadata map to genuine FastQC results without changing values", () => {
  const samples = [fixture("R1"), fixture("R2")];
  const inputs = samples.map((s) => "/data/" + s.name);
  const run = {
    id: "analysis",
    inputs,
    sample_groups: [
      { id: "g", display_name: "User sample", files: inputs, source: "manual" },
    ],
    input_pairing: inputs.map((path, i) => ({
      path,
      name: samples[i].name,
      read: i ? "R2" : "R1",
      paired: true,
      pair_key: "manual:p",
      mate: inputs[1 - i],
      source: "manual",
      lane: "L003",
      chunk: "002",
    })),
  } as Run;
  const before = JSON.stringify(samples),
    entities = analyticsSamples(run, samples);
  assert.ok(
    entities.every(
      (e) =>
        e.groupName === "User sample" && e.lane === "L003" && e.chunk === "002",
    ),
  );
  assert.equal(confirmedPairs(run, samples).length, 1);
  assert.equal(JSON.stringify(samples), before);
  const aggregated = {
    ...run,
    inputs: ["/results/source/fastqc"],
    sample_input_paths: inputs,
  };
  assert.equal(confirmedPairs(aggregated, samples).length, 1);
  assert.equal(analyticsSamples(aggregated, samples)[0].source, inputs[0]);
});
