import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import * as echarts from "echarts";
import { variantViews } from "../src/variantChart.ts";
import type { VariantMetrics } from "../src/types.ts";

function genuine(name: string): VariantMetrics {
  const lines = readFileSync(new URL(`../../backend/tests/fixtures/bcftools-1.24/${name}.stats.txt`, import.meta.url), "utf8").split("\n").map(l => l.split("\t"));
  const rows = (code: string) => lines.filter(r => r[0] === code).map(r => r.slice(2));
  return {summary: {rows: rows("SN")}, tstv: {rows: rows("TSTV")}, quality: {chart_rows: rows("QUAL")}, depth: {chart_rows: rows("DP")}, quality_available: name === "multisample", site_depth_available: name === "multisample", genotype_depth_available: false} as VariantMetrics;
}

test("genuine nonadditive record composition stays unstacked and preserves counts", () => {
  const data = genuine("mixed"), before = structuredClone(data);
  const chart = variantViews(data).composition!;
  assert.deepEqual((chart.options.series as {data: number[]}[])[0].data, [2, 1, 2, 1, 1]);
  assert.match(chart.description, /overlapping/);
  assert.ok(!("stack" in (chart.options.series as object[])[0]));
  assert.deepEqual(data, before);
});

test("absent QUAL/depth never produces fabricated charts; genuine observed data does", () => {
  assert.equal(variantViews(genuine("missing-depth")).depth, null);
  assert.equal(variantViews(genuine("missing-depth")).quality, null);
  const data = genuine("multisample");
  for (const view of Object.values(variantViews(data))) {
    assert.ok(view);
    const chart = echarts.init(null, undefined, {renderer: "svg", ssr: true, width: 390, height: 420});
    try {chart.setOption(view.options); assert.doesNotMatch(chart.renderToSVGString(), /NaN|Infinity/);} finally {chart.dispose();}
  }
});

test("unsafe count precision and oversized distribution do not create rounded native charts", () => {
  const data = genuine("multisample");
  data.summary.rows.find(r => r[0] === "number of SNPs:")![1] = "9007199254740993";
  data.quality.chart_rows = null; data.depth.chart_rows = null;
  const views = variantViews(data);
  assert.equal(views.composition, null); assert.equal(views.quality, null); assert.equal(views.depth, null);
});
