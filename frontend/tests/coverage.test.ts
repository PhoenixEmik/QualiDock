import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import * as echarts from "echarts";
import { coverageView } from "../src/coverageChart.ts";
import type { CoverageMetrics } from "../src/types.ts";

const fixture = new URL(
  "../../backend/tests/fixtures/mosdepth-0.3.14/coverage.mosdepth.global.dist.txt",
  import.meta.url,
);
const rows = readFileSync(fixture, "utf8")
  .trim()
  .split("\n")
  .map((l) => l.split("\t"))
  .filter((r) => r[0] === "total")
  .map((r) => r.slice(1));
const data = {
  distribution: {
    columns: ["Depth", "Reported fraction ≥ depth"],
    rows,
    total_rows: rows.length,
  },
  reported_reference_bases: 100,
  header_reference_bases: 150,
} as CoverageMetrics;

test("genuine mosdepth points preserve original CDF fractions and omit unreported tail bins", () => {
  const before = structuredClone(data);
  const view = coverageView(data);
  const series = view.options.series as {
    type: string;
    step: string;
    data: { value: number[]; raw: string[] }[];
  }[];
  assert.equal(series[0].type, "line");
  assert.equal(series[0].step, "end");
  assert.deepEqual(series[0].data, [
    { value: [0, 1], raw: ["0", "1.00000"] },
    { value: [1, 0.25], raw: ["1", "0.25000"] },
  ]);
  assert.match(view.summary, /100 reported reference bases/);
  assert.deepEqual(data, before);
  assert.ok(!("markArea" in series[0]));
  const formatter = (view.options.tooltip as { formatter: Function }).formatter;
  assert.match(formatter([{ data: series[0].data[1] }]), /0\.25000/);
  assert.match(
    formatter([{ data: series[0].data[1] }]),
    /100 reported reference bases/,
  );
});

test("coverage CDF uses existing ECharts for a responsive finite SVG", () => {
  const chart = echarts.init(null, undefined, {
    renderer: "svg",
    ssr: true,
    width: 390,
    height: 420,
  });
  try {
    chart.setOption(coverageView(data).options);
    const svg = chart.renderToSVGString();
    assert.match(svg, /<svg/);
    assert.doesNotMatch(svg, /NaN|Infinity/);
    assert.match(svg, /Reported global CDF/);
  } finally {
    chart.dispose();
  }
});
