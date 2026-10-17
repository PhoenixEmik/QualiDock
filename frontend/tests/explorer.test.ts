import assert from "node:assert/strict";
import test from "node:test";
import {
  explorerRows,
  listingUrl,
  matchesRow,
  resolveEntries,
  rowInputPaths,
  selectionState,
} from "../src/explorer.ts";
import type { Entry, Listing } from "../src/types.ts";

const directory = "/data";
function entry(name: string, overrides: Partial<Entry> = {}): Entry {
  return {
    name,
    path: `${directory}/${name}`,
    kind: "fastq",
    size: 100,
    modified: 1,
    read: null,
    pair_key: null,
    paired: false,
    mate: null,
    ...overrides,
  };
}
const r1 = entry("sample_R1_001.fastq.gz", {
  read: "R1",
  pair_key: "/data/sample_001",
  paired: true,
  mate: "/data/sample_R2_001.fastq.gz",
});
const r2 = entry("sample_R2_001.fastq.gz", {
  read: "R2",
  pair_key: "/data/sample_001",
  paired: true,
  mate: r1.path,
});

test("Samples groups confirmed mates; Files keeps individually selectable reads", () => {
  const samples = explorerRows([r1, r2], "samples");
  assert.equal(samples.length, 1);
  assert.equal(samples[0].pairing, "Paired-end");
  assert.deepEqual(rowInputPaths(samples[0]), [r1.path, r2.path]);
  const files = explorerRows([r1, r2], "files");
  assert.equal(files.length, 2);
  assert.deepEqual(rowInputPaths(files[0]), [r1.path]);
});

test("missing R1 and R2 mates remain visible as incomplete samples", () => {
  for (const read of ["R1", "R2"]) {
    const file = entry(`orphan_${read}.fq`, { read, pair_key: "/data/orphan" });
    const [row] = explorerRows([file], "samples");
    assert.equal(row.pairing, "Incomplete pair");
    assert.match(
      row.description,
      new RegExp(read === "R1" ? "R2 missing" : "R1 missing"),
    );
    assert.deepEqual(rowInputPaths(row), [file.path]);
  }
});

test("single-end and unrecognized naming never acquire guessed mates", () => {
  const inputs = [
    entry("single.fastq"),
    entry("arbitrary_forward.fq.gz"),
    entry("arbitrary_reverse.fq.gz"),
  ];
  const rows = explorerRows(inputs, "samples");
  assert.equal(rows.length, 3);
  assert.ok(rows.every((row) => row.pairing === "Single / unassigned"));
  assert.deepEqual(
    rows.flatMap(rowInputPaths),
    inputs.map((file) => file.path),
  );
});

test("ambiguous read names are not presented as a complete pair", () => {
  const inputs = [
    { ...r1, paired: false, mate: null },
    { ...r2, paired: false, mate: null },
    entry("sample_1_001.fq", { read: "R1", pair_key: r1.pair_key }),
  ];
  const [row] = explorerRows(inputs, "samples");
  assert.equal(row.pairing, "Ambiguous naming");
  assert.equal(row.files.length, 3);
  assert.equal(rowInputPaths(row).length, 3);
});

test("the same sample name in different directories stays separate", () => {
  const other = {
    ...r1,
    path: "/other/sample_R1_001.fastq.gz",
    pair_key: "/other/sample_001",
    mate: "/other/sample_R2_001.fastq.gz",
  };
  assert.equal(explorerRows([r1, other], "samples").length, 2);
});

test("searching either mate retains the full sample selection", () => {
  const rows = explorerRows([r1, r2], "samples").filter((row) =>
    matchesRow(row, " R2_001 "),
  );
  assert.equal(rows.length, 1);
  assert.deepEqual(rowInputPaths(rows[0]), [r1.path, r2.path]);
});

test("switching from an individual read to Samples preserves partial selection", () => {
  const selected = new Map([[r1.path, r1]]);
  const sample = explorerRows([r1, r2], "samples")[0];
  assert.deepEqual(selectionState(rowInputPaths(sample), selected), {
    all: false,
    some: true,
  });
  selected.set(r2.path, r2);
  assert.deepEqual(selectionState(rowInputPaths(sample), selected), {
    all: true,
    some: false,
  });
  assert.deepEqual(selectionState([], selected), { all: false, some: false });
});

test("confirmed mates split across pages are still selected together", async () => {
  const [row] = explorerRows([r1], "samples");
  assert.equal(row.pairing, "Paired-end");
  assert.match(row.description, /another file page/);
  const firstPage = [
    r1,
    ...Array.from({ length: 499 }, (_, i) => entry(`other-${i}.fq`)),
  ];
  const offsets: number[] = [];
  const result = await resolveEntries(
    rowInputPaths(row),
    [r1],
    async (path, offset): Promise<Listing> => {
      assert.equal(path, directory);
      offsets.push(offset);
      return {
        path: directory,
        parent: null,
        total: 501,
        entries: offset === 0 ? firstPage : [r2],
      };
    },
  );
  assert.deepEqual(offsets, [0, 500]);
  assert.deepEqual(result, [r1, r2]);
});

test("directories, reports, and unrelated files preserve their identity and selectability", () => {
  const folder = entry("nested", { kind: "directory", size: null });
  const report = entry("sample_fastqc.zip", { kind: "fastqc" });
  const unrelated = entry("notes.txt", { kind: "file" });
  const rows = explorerRows([folder, report, unrelated], "samples");
  assert.ok(rows.every((row) => !row.sample));
  assert.deepEqual(rows.map(rowInputPaths), [[], [report.path], []]);
});

test("existing selections need no extra requests and are deduplicated", async () => {
  const result = await resolveEntries(
    [r1.path, r2.path, r1.path],
    [r1, r2],
    async () => {
      throw new Error("Unexpected request");
    },
  );
  assert.deepEqual(result, [r1, r2]);
});

test("missing or inaccessible mates fail instead of inventing file metadata", async () => {
  await assert.rejects(
    resolveEntries([r2.path], [r1], async () => ({
      path: directory,
      parent: null,
      total: 1,
      entries: [r1],
    })),
    /no longer available/,
  );
  await assert.rejects(
    resolveEntries([r2.path], [], async () => {
      throw new Error("Path is outside the configured roots");
    }),
    /outside the configured roots/,
  );
});

test("selection sends snapshot tokens and advances over filtered empty pages", async () => {
  const input = entry("target.fastq");
  const calls: unknown[][] = [];
  const resolved = await resolveEntries(
    [input.path],
    [],
    async (directory, offset, snapshot) => {
      calls.push([directory, offset, snapshot]);
      if (offset === 0)
        return {
          path: directory,
          parent: null,
          entries: [],
          total: 3,
          snapshot: "stable",
          next_offset: 2,
        };
      return {
        path: directory,
        parent: null,
        entries: [input],
        total: 3,
        snapshot: "stable",
        next_offset: null,
      };
    },
  );
  assert.deepEqual(resolved, [input]);
  assert.deepEqual(calls, [
    ["/data", 0, undefined],
    ["/data", 2, "stable"],
  ]);
});

test("selection refuses to mix directory snapshots after filesystem changes", async () => {
  const input = entry("missing.fastq");
  await assert.rejects(
    resolveEntries([input.path], [], async (directory, offset) => ({
      path: directory,
      parent: null,
      entries: [entry(offset ? "other2.fastq" : "other.fastq")],
      total: 3,
      snapshot: offset ? "changed" : "original",
      next_offset: offset + 1,
    })),
    /listing changed/,
  );
});

test("listing queries preserve path and snapshot boundaries", () => {
  const query = new URLSearchParams(
    listingUrl("/data/a & b", 500, "token&refresh=true").split("?")[1],
  );
  assert.equal(query.get("path"), "/data/a & b");
  assert.equal(query.get("snapshot"), "token&refresh=true");
  assert.equal(query.has("refresh"), false);
  assert.equal(
    new URLSearchParams(
      listingUrl("/data", 0, undefined, true).split("?")[1],
    ).get("refresh"),
    "true",
  );
});

test("allowlisted QC JSON remains selectable without pairing metadata", () => {
  const report = entry("HG001.fastp.json", { kind: "qcreport" });
  const rows = explorerRows([report], "samples");
  assert.equal(rows[0].sample, false);
  assert.deepEqual(rowInputPaths(rows[0]), [report.path]);
});

test("BAM and CRAM remain independently selectable without FASTQ pairing", () => {
  const alignments = [
    entry("sample_R1.bam", { kind: "alignment" }),
    entry("sample_R2.cram", { kind: "alignment" }),
  ];
  const rows = explorerRows(alignments, "samples");
  assert.equal(rows.length, 2);
  assert.ok(rows.every((row) => !row.sample && !row.pairing));
  assert.deepEqual(
    rows.flatMap(rowInputPaths),
    alignments.map((e) => e.path),
  );
});
