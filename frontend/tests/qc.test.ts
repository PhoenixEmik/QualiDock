import test from "node:test";
import * as echarts from "echarts";
import { chartOptions } from "../src/chartOptions.ts";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  chartData,
  findModule,
  moduleNames,
  numeric,
  qualityData,
  rowTooltip,
  tableOnly,
  supportedModules,
} from "../src/qc.ts";
import type { Module, Sample } from "../src/types.ts";

// Parse the verbatim golden output only to verify frontend point construction independently.
const raw = readFileSync(
  new URL(
    "../../backend/tests/fixtures/fastqc-0.13.0/coverage_R1_fastqc/fastqc_data.txt",
    import.meta.url,
  ),
  "utf8",
);
const modules: Module[] = raw
  .split(">>")
  .filter((block) => !block.startsWith("END_MODULE") && !block.startsWith("##"))
  .map((block) => {
    const lines = block.trim().split("\n");
    const [name, status] = lines.shift()!.split("\t");
    const header = lines.find(
      (line) => line.startsWith("#") && !line.startsWith("#Total Deduplicated"),
    );
    return {
      name,
      status,
      columns: header?.slice(1).split("\t") || [],
      rows: lines
        .filter((line) => !line.startsWith("#"))
        .map((line) => line.split("\t")),
    };
  });
const sample = { modules } as Sample;
for (const name of supportedModules)
  test(`real FastQC module: ${name}`, () => {
    const module = findModule(sample, name)!;
    assert.ok(module, `${name} must exist in actual FastQC output`);
    assert.ok(moduleNames(sample).includes(name));
    if (tableOnly(module)) {
      assert.ok(module.rows.length);
      return;
    }
    const chart = chartData(module);
    if (chart.kind === "heatmap") {
      assert.deepEqual(chart.categories, [
        ...new Set(module.rows.map((row) => row[1])),
      ]);
      assert.deepEqual(chart.tiles, ["1101", "1102"]);
      chart.series[0].data.forEach((point, index) =>
        assert.deepEqual(point, [
          chart.categories.indexOf(module.rows[index][1]),
          chart.tiles.indexOf(module.rows[index][0]),
          Number(module.rows[index][2]),
        ]),
      );
    } else {
      assert.deepEqual(
        chart.categories,
        module.rows.map((row) => row[0]),
      );
      for (const series of chart.series) {
        const column = module.columns.indexOf(series.name);
        assert.deepEqual(
          series.data,
          module.rows.map((row) => Number(row[column])),
        );
      }
    }
    for (let index = 0; index < module.rows.length; index++) {
      for (const value of module.rows[index])
        assert.ok(rowTooltip(module, index).includes(value));
    }
  });
test("quality boxes preserve reported quantiles and grouped bins", () => {
  const module = findModule(sample, "Per base sequence quality")!;
  const per_base_quality = module.rows.map((row) => ({
    base: row[0],
    mean: Number(row[1]),
    median: Number(row[2]),
    lower_quartile: Number(row[3]),
    upper_quartile: Number(row[4]),
    percentile_10: Number(row[5]),
    percentile_90: Number(row[6]),
  }));
  const data = qualityData({ ...sample, per_base_quality });
  assert.deepEqual(
    data.boxes,
    module.rows.map((row) =>
      [row[5], row[3], row[2], row[4], row[6]].map(Number),
    ),
  );
  assert.deepEqual(
    data.means,
    module.rows.map((row) => Number(row[1])),
  );
  assert.ok(data.categories.includes("10-14"));
  assert.ok(data.categories.includes("15-19"));
  assert.ok(data.categories.includes("20-24"));
});
test("missing numeric cells stay gaps and raw precision stays in tooltips", () => {
  for (const missing of [undefined, "", " ", "NaN", "Infinity", "N/A"])
    assert.equal(numeric(missing), null);
  assert.equal(numeric("0"), 0);
  assert.equal(numeric("1e-20"), 1e-20);
  const module = findModule(sample, "Per tile sequence quality")!;
  assert.ok(rowTooltip(module, 1).includes(module.rows[1][2]));
});
test("module aliases and future modules remain inspectable", () => {
  assert.ok(findModule(sample, "K-mer Content"));
  const future = {
    name: "Future module",
    status: "unknown",
    columns: ["Field", "Value"],
    rows: [["A", "2"]],
  };
  assert.ok(
    moduleNames({ ...sample, modules: [future] }).includes("Future module"),
  );
  assert.ok(tableOnly(future));
});

for (const name of supportedModules.filter(
  (name) => !tableOnly(findModule(sample, name)!),
))
  test(`ECharts renders reported data: ${name}`, () => {
    const q = findModule(sample, "Per base sequence quality")!;
    const complete = {
      ...sample,
      name: "Actual FastQC output",
      per_base_quality: q.rows.map((row) => ({
        base: row[0],
        mean: Number(row[1]),
        median: Number(row[2]),
        lower_quartile: Number(row[3]),
        upper_quartile: Number(row[4]),
        percentile_10: Number(row[5]),
        percentile_90: Number(row[6]),
      })),
    };
    const chart = echarts.init(null, undefined, {
      renderer: "svg",
      ssr: true,
      width: 900,
      height: 400,
    });
    try {
      chart.setOption(chartOptions(complete, name));
      const svg = chart.renderToSVGString();
      assert.ok(svg.startsWith("<svg"));
      assert.ok(
        !svg.includes("NaN"),
        "Actual finite fixture points must render without invalid coordinates",
      );
      assert.ok(svg.includes("<path"));
    } finally {
      chart.dispose();
    }
  });
