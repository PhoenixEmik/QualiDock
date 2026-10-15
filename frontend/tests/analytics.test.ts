import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fixture } from "./fastqcFixture.ts";
import {
  analyticsSamples,
  sortStats,
  statsExport,
  rawUnit,
  statusMatrix,
  multiComparison,
  sourceExport,
  toggleSelection,
} from "../src/analytics.ts";
import { overlayOptions } from "../src/multiSampleChart.ts";
import { findModule } from "../src/qc.ts";
import type { Run, MultiQCSummary } from "../src/types.ts";
const samples = [fixture("R1"), fixture("R2")];
const run = { id: "run", inputs: samples.map((s) => "/data/" + s.name) } as Run;
const entities = () => analyticsSamples(run, samples);
for (const version of ["1.25.1", "1.35"]) {
  test(`genuine MultiQC ${version} columns, raw units, values, exact names and exports`, () => {
    const data = JSON.parse(
      readFileSync(
        new URL(
          `../../backend/tests/fixtures/multiqc/${version}/general-stats.json`,
          import.meta.url,
        ),
        "utf8",
      ),
    );
    const headers = Object.values(
      data.report_general_stats_headers,
    )[0] as Record<string, any>;
    const table = Object.values(data.report_general_stats_data)[0] as Record<
      string,
      Record<string, number>
    >;
    const summary: MultiQCSummary = {
      columns: Object.entries(headers).map(([key, c]) => ({
        key,
        title: c.title,
        description: c.description,
        namespace: c.namespace,
        unit: c.suffix || "",
        raw_key: key,
      })),
      rows: Object.entries(table).map(([sample, values]) => ({
        sample,
        values,
      })),
    };
    const mapped = analyticsSamples(run, samples, summary);
    assert.equal(mapped.length, 2);
    assert.equal(mapped[0].multiqcName, "coverage_R1");
    assert.equal(mapped[0].source, "/data/coverage_R1.fastq.gz");
    assert.equal(
      rawUnit(summary.columns.find((c) => c.raw_key === "total_sequences")!),
      "reads",
    );
    assert.equal(summary.rows[0].values.total_sequences, 400);
    const tsv = statsExport(summary.rows, summary.columns, "\t");
    assert.match(tsv, /Seqs \[total_sequences\] \(reads\)/);
    assert.match(tsv, /33.33333333333333/);
    assert.ok(!tsv.includes("(M)"));
  });
}
test("statistics sorting is numerical, multi-column, textual and always leaves missing last; zero preserved", () => {
  const rows = [
    { sample: "c", values: { n: 0, t: "z" } },
    { sample: "b", values: { n: 10, t: "a" } },
    { sample: "d", values: {} },
    { sample: "a", values: { n: 2, t: "a" } },
  ];
  assert.deepEqual(
    sortStats(rows, "", [{ key: "n", direction: 1 }]).map((r) => r.sample),
    ["c", "a", "b", "d"],
  );
  assert.deepEqual(
    sortStats(rows, "", [
      { key: "t", direction: 1 },
      { key: "n", direction: -1 },
    ]).map((r) => r.sample),
    ["b", "a", "c", "d"],
  );
  assert.deepEqual(
    sortStats(rows, "B", []).map((r) => r.sample),
    ["b"],
  );
  assert.equal(
    statsExport(
      rows,
      [
        {
          key: "n",
          title: "N",
          raw_key: "n",
          namespace: "",
          description: "",
          unit: "",
        },
      ],
      ",",
    ),
    "Sample,N [n]\r\nc,0\r\nb,10\r\nd,\r\na,2\r\n",
  );
});
test("duplicate filename stems never map MultiQC rows or imply pairs", () => {
  const dup = { ...samples[0], id: "inputs/other/coverage_R1_fastqc.zip" };
  const result = analyticsSamples(run, [samples[0], dup], {
    columns: [],
    rows: [{ sample: "coverage_R1", values: {} }],
  });
  assert.equal(result.length, 3);
  assert.equal(result[2].fastqc, undefined);
  assert.ok(result.every((e) => !e.read));
  assert.notEqual(result[0].id, result[1].id);
});
test("confirmed pairing preserves read, lane, file and source identity", () => {
  const paths = run.inputs;
  const paired = {
    ...run,
    input_pairing: samples.map((s, i) => ({
      path: paths[i],
      name: s.name,
      read: i ? "R2" : "R1",
      pair_key: "/data/coverage",
      paired: true,
      mate: paths[1 - i],
    })),
  };
  const result = analyticsSamples(paired, samples);
  assert.deepEqual(
    result.map((e) => e.read),
    ["R1", "R2"],
  );
  assert.equal(result[0].pair, result[1].pair);
  assert.ok(
    analyticsSamples(
      { ...paired, input_pairing: [paired.input_pairing[0]] },
      samples,
    ).every((e) => !e.read),
  );
});
test("status matrix preserves every original classification and marks missing unavailable", () => {
  const result = statusMatrix(entities());
  for (const row of result.rows)
    for (const [i, name] of result.modules.entries())
      assert.equal(
        row.statuses[i],
        findModule(row.entity.fastqc!, name)?.status || "unavailable",
      );
  const missing = statusMatrix([
    { ...entities()[0], fastqc: { ...samples[0], modules: [] } },
  ]);
  assert.ok(missing.rows[0].statuses.every((s) => s === "unavailable"));
});
test("multi-sample quality values, grouped bins, raw precision and chart bands are unchanged", () => {
  const before = JSON.stringify(samples),
    model = multiComparison(entities(), "Per base sequence quality");
  assert.equal(model.groups.length, 1);
  const group = model.groups[0];
  assert.deepEqual(
    group.categories,
    findModule(samples[0], "Per base sequence quality")!.rows.map((r) => r[0]),
  );
  assert.ok(group.categories.includes("10-14"));
  assert.deepEqual(
    group.series[0].values,
    samples[0].per_base_quality.map((p) => p.mean),
  );
  const options = overlayOptions(group, true);
  const series = options.series as any[];
  assert.equal(series[0].connectNulls, false);
  assert.equal(series.at(-1).markArea.data[1][0].yAxis, 20);
  assert.equal(series.at(-1).markArea.data[2][0].yAxis, 28);
  assert.equal(JSON.stringify(samples), before);
  const output = sourceExport(entities(), "Per base sequence quality", "\t");
  assert.ok(
    output.includes(
      findModule(samples[0], "Per base sequence quality")!.rows[11][1],
    ),
  );
  assert.match(output, /10-14/);
});
test("incompatible or overlapping position bins are split; different lengths retain unmatched gaps", () => {
  const changed = structuredClone(samples[1]);
  findModule(changed, "Per base sequence quality")!.rows[9][0] = "10-12";
  assert.equal(
    multiComparison(
      analyticsSamples(run, [samples[0], changed]),
      "Per base sequence quality",
    ).groups.length,
    2,
  );
  const shorter = structuredClone(samples[1]);
  findModule(shorter, "Per base sequence quality")!.rows.pop();
  const group = multiComparison(
    analyticsSamples(run, [samples[0], shorter]),
    "Per base sequence quality",
  ).groups[0];
  assert.equal(group.series[1].values.at(-1), null);
});
test("different adapter categories and encodings remain separate; unknown modules are unsupported", () => {
  const changed = structuredClone(samples[1]);
  findModule(changed, "Adapter Content")!.columns[1] = "Another adapter";
  changed.encoding = "Unknown";
  const e = analyticsSamples(run, [samples[0], changed]);
  assert.equal(multiComparison(e, "Adapter Content").groups.length, 2);
  assert.equal(
    multiComparison(e, "Per base sequence quality").groups.length,
    2,
  );
  assert.equal(multiComparison(e, "Kmer Content").groups.length, 0);
});
test("normalization is explicit and requires complete counts matching reported total", () => {
  const metric = "Per sequence quality scores",
    e = entities(),
    counts = findModule(samples[0], metric)!.rows;
  const normalized = multiComparison(e, metric, true);
  assert.equal(normalized.unavailable.length, 0);
  assert.deepEqual(
    normalized.groups[0].series[0].values,
    normalized.groups[0].categories.map((label) => {
      const row = counts.find((r) => r[0] === label);
      return row ? (Number(row[1]) / samples[0].total_sequences!) * 100 : null;
    }),
  );
  const changed = structuredClone(samples[1]);
  changed.total_sequences = 401;
  const bad = multiComparison(
    analyticsSamples(run, [samples[0], changed]),
    metric,
    true,
  );
  assert.equal(bad.unavailable.length, 1);
  assert.equal(bad.groups[0].members.length, 1);
});
test("missing metrics/numbers are unavailable; exact zero is never treated as missing", () => {
  const changed = structuredClone(samples[1]);
  const module = findModule(changed, "Per base sequence quality")!;
  module.rows[0][1] = "";
  module.rows[1][1] = "0";
  const group = multiComparison(
    analyticsSamples(run, [samples[0], changed]),
    module.name,
  ).groups[0];
  assert.equal(group.series[1].values[0], null);
  assert.equal(group.series[1].values[1], 0);
  module.available = false;
  assert.equal(
    multiComparison(analyticsSamples(run, [changed]), module.name).unavailable
      .length,
    1,
  );
});
test("shared selection is immutable, stable across view filtering, and supports clearing", () => {
  const old = new Set(["a"]);
  const next = toggleSelection(old, "b");
  assert.deepEqual([...old], ["a"]);
  assert.deepEqual([...next], ["a", "b"]);
  assert.deepEqual([...toggleSelection(next, "a")], ["b"]);
});
test("100 clearly synthetic schema-derived records keep identities and transformations bounded", () => {
  const synthetic = Array.from({ length: 100 }, (_, i) => ({
    ...samples[i % 2],
    id: `synthetic/${i}`,
    name: `synthetic_${i}.fastq.gz`,
  }));
  const start = performance.now(),
    e = analyticsSamples({ ...run, inputs: [] }, synthetic);
  assert.equal(new Set(e.map((s) => s.id)).size, 100);
  assert.equal(statusMatrix(e).rows.length, 100);
  assert.equal(
    multiComparison(e, "Per base sequence quality").groups[0].series.length,
    100,
  );
  assert.ok(performance.now() - start < 2500);
});

test("all verified comparison modules preserve source data and render finite responsive SVG exports", async () => {
  const echarts = await import("echarts");
  for (const metric of [
    "Per base sequence quality",
    "Per sequence quality scores",
    "Per sequence GC content",
    "Sequence Duplication Levels",
    "Adapter Content",
    "Sequence Length Distribution",
  ]) {
    const group = multiComparison(entities(), metric).groups[0];
    assert.ok(group, metric);
    for (const series of group.series)
      for (const [i, bin] of group.categories.entries()) {
        const module = findModule(series.entity.fastqc!, metric)!;
        const raw = module.rows.find((r) => r[0] === bin)?.[
          module.columns.indexOf(series.column)
        ];
        assert.equal(series.raw[i], raw);
      }
    for (const width of [350, 1200]) {
      const chart = echarts.init(null, undefined, {
        renderer: "svg",
        ssr: true,
        width,
        height: 480,
      });
      try {
        chart.setOption(
          overlayOptions(group, metric === "Per base sequence quality"),
        );
        chart.dispatchAction({ type: "dataZoom", start: 10, end: 80 });
        const svg = chart.renderToSVGString();
        assert.match(svg, /<svg/);
        assert.ok(!svg.includes("NaN"), metric);
      } finally {
        chart.dispose();
      }
    }
  }
});

test("unverified MultiQC suffixes never become scientific raw units", () => {
  assert.equal(
    rawUnit({
      key: "x",
      title: "X",
      description: "",
      namespace: "Other tool",
      unit: "%",
      raw_key: "fraction",
    }),
    "",
  );
  assert.equal(
    rawUnit({
      key: "x",
      title: "X",
      description: "",
      namespace: "FastQC",
      unit: "%",
      raw_key: "unknown",
    }),
    "",
  );
});
test("unknown columns are not plotted as counts and theoretical GC data is not substituted", () => {
  const changed = structuredClone(samples[0]);
  const module = findModule(changed, "Per sequence GC content")!;
  module.columns[1] = "Theoretical distribution";
  assert.equal(
    multiComparison(analyticsSamples(run, [changed]), module.name).groups
      .length,
    0,
  );
});

test("all-missing numeric modules have an explicit unavailable state", () => {
  const changed = structuredClone(samples[0]);
  const module = findModule(changed, "Per base sequence quality")!;
  for (const row of module.rows) row[1] = "";
  const result = multiComparison(analyticsSamples(run, [changed]), module.name);
  assert.equal(result.groups.length, 0);
  assert.match(result.unavailable[0], /no numeric values/);
});
