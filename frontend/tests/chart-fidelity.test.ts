import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as echarts from "echarts";
import { fixture } from "./fastqcFixture.ts";
import { chartOptions } from "../src/chartOptions.ts";
import { comparisonChartOptions } from "../src/comparisonChart.ts";
import {
  fastqcColors,
  scientificColor,
  gcReferenceUnavailable,
} from "../src/fastqcTheme.ts";
import { qualityUpperLimit, renderQualityBox } from "../src/qualityPlot.ts";
import { findModule, tableOnly } from "../src/qc.ts";

const r1 = fixture("R1"),
  r2 = fixture("R2");
const quality = "Per base sequence quality";
type Series = {
  name: string;
  type: string;
  data: unknown[];
  lineStyle?: { color: string; type?: string };
  markArea?: {
    data: [
      { yAxis: number; itemStyle: { color: string } },
      { yAxis: number },
    ][];
  };
};
const series = (option: echarts.EChartsOption) => option.series as Series[];

test("individual quality glyphs and mean retain every genuine reported statistic", () => {
  const before = JSON.stringify(r1);
  const option = chartOptions(r1, quality);
  const rows = findModule(r1, quality)!.rows;
  assert.equal(series(option)[0].type, "custom");
  assert.deepEqual(
    series(option)[0].data,
    rows.map((row) => [row[5], row[3], row[2], row[4], row[6]].map(Number)),
  );
  assert.deepEqual(
    series(option)[1].data,
    rows.map((row) => Number(row[1])),
  );
  assert.equal(series(option)[1].lineStyle!.color, "#0000C8");
  assert.equal(JSON.stringify(r1), before);
});

test("the red median is a horizontal segment inside each yellow box, with exact percentile whiskers", () => {
  const row = findModule(r1, quality)!.rows.find((row) => row[0] === "20-24")!;
  const values = [row[5], row[3], row[2], row[4], row[6]].map(Number);
  // A simple pixel transform verifies the renderer's geometry independently of its colors.
  const params = {
    dataIndex: 11,
    coordSys: { x: 0, y: 0, width: 1000, height: 500 },
  };
  const api = {
    value: (i: number) => values[i],
    coord: ([x, y]: number[]) => [x * 20, 450 - y * 10],
    size: () => [20, 0],
  };
  const glyph = renderQualityBox(
    params as unknown as Parameters<typeof renderQualityBox>[0],
    api as unknown as Parameters<typeof renderQualityBox>[1],
  ) as {
    children: {
      type: string;
      shape: Record<string, number>;
      style: { fill?: string; stroke: string };
    }[];
  };
  const box = glyph.children.find((child) => child.type === "rect")!;
  const median = glyph.children.find(
    (child) => child.style.stroke === "#C80000",
  )!;
  assert.equal(box.style.fill, "#F0F000");
  assert.equal(box.shape.y, 450 - Number(row[4]) * 10);
  assert.ok(
    Math.abs(box.shape.height - (Number(row[4]) - Number(row[3])) * 10) < 1e-9,
  );
  assert.equal(median.shape.y1, 450 - Number(row[2]) * 10);
  assert.equal(median.shape.y1, median.shape.y2);
  assert.equal(median.shape.x1, box.shape.x);
  assert.equal(median.shape.x2, box.shape.x + box.shape.width);
  assert.equal(glyph.children[0].shape.y1, 450 - Number(row[5]) * 10);
  assert.equal(glyph.children[2].shape.y2, 450 - Number(row[6]) * 10);
  assert.equal(
    glyph.children.filter((child) => child.type === "line").length,
    5,
  );
  for (const value of [null, undefined, NaN]) {
    const missing = {
      ...api,
      value: (i: number) => (i === 0 ? value : values[i]),
    };
    assert.equal(
      renderQualityBox(params as never, missing as never),
      undefined,
    );
  }
});

test("quality regions cover precisely Q0–20, Q20–28 and Q28 to the actual shared upper bound", () => {
  const high = {
    ...r2,
    per_base_quality: r2.per_base_quality.map((bin, i) =>
      i === 0 ? { ...bin, percentile_90: 52 } : bin,
    ),
  };
  for (const option of [
    chartOptions(r1, quality),
    comparisonChartOptions(r1, high, quality),
  ]) {
    const max = (option.yAxis as { max: number }).max;
    const regions = series(option).find(
      (item) => item.name === "Quality regions",
    )!;
    assert.deepEqual(
      regions.markArea!.data.map(([a, b]) => [
        a.yAxis,
        b.yAxis,
        a.itemStyle.color,
      ]),
      [
        [0, 20, "#F9DEDE"],
        [20, 28, "#FFF0C9"],
        [28, max, "#DDF2DF"],
      ],
    );
    assert.deepEqual(regions.data, []);
    assert.ok(
      !(option.legend as { data: string[] }).data.includes(regions.name),
    );
  }
  assert.equal(qualityUpperLimit([r1, high]), 55);
});

for (const width of [350, 1000])
  test(`quality SVG keeps statistical colors and quality bands after zoom and resize (${width}px)`, () => {
    const chart = echarts.init(null, undefined, {
      renderer: "svg",
      ssr: true,
      width,
      height: 440,
    });
    try {
      chart.setOption(chartOptions(r1, quality));
      const check = () => {
        const svg = chart.renderToSVGString();
        assert.ok(!/NaN|Infinity/.test(svg));
        for (const color of Object.values(fastqcColors.quality))
          assert.ok(svg.toLowerCase().includes(color.toLowerCase()), color);
        assert.equal(
          chart.convertToPixel({ yAxisIndex: 0 }, 0),
          chart.getHeight() - 124,
        );
        assert.ok(
          (chart.convertToPixel({ yAxisIndex: 0 }, 28) as number) <
            (chart.convertToPixel({ yAxisIndex: 0 }, 20) as number),
        );
      };
      check();
      chart.dispatchAction({ type: "dataZoom", startValue: 9, endValue: 16 });
      check();
      chart.resize({ width: width + 100, height: 440 });
      check();
      chart.dispatchAction({
        type: "legendUnSelect",
        name: "Quartiles · 10th–90th whiskers",
      });
      chart.dispatchAction({ type: "legendUnSelect", name: "Mean quality" });
      const empty = chart.renderToSVGString().toLowerCase();
      for (const color of [
        fastqcColors.quality.poor,
        fastqcColors.quality.reasonable,
        fastqcColors.quality.good,
      ])
        assert.ok(empty.includes(color.toLowerCase()));
    } finally {
      chart.dispose();
    }
  });

test("single and paired nucleotide profiles use the same A/C/G/T identities; read style is separate", () => {
  const name = "Per base sequence content";
  assert.deepEqual(fastqcColors.bases, {
    A: "#2CA02C",
    C: "#1F77B4",
    G: "#444444",
    T: "#D62728",
  });
  for (const item of series(chartOptions(r1, name)))
    assert.equal(item.lineStyle!.color, fastqcColors.bases[item.name]);
  for (const base of ["A", "C", "G", "T"]) {
    const paired = series(comparisonChartOptions(r1, r2, name));
    const left = paired.find((item) => item.name === `R1 · ${base}`)!,
      right = paired.find((item) => item.name === `R2 · ${base}`)!;
    assert.equal(left.lineStyle!.color, fastqcColors.bases[base]);
    assert.equal(right.lineStyle!.color, left.lineStyle!.color);
    assert.equal(left.lineStyle!.type, "solid");
    assert.equal(right.lineStyle!.type, "dashed");
  }
});

test("GC observed data is red, theoretical data blue only when supplied; no model is fabricated", () => {
  const name = "Per sequence GC content",
    module = findModule(r1, name)!;
  const plotted = series(chartOptions(r1, name));
  assert.equal(plotted.length, 1);
  assert.equal(plotted[0].name, "Observed GC count");
  assert.equal(plotted[0].lineStyle!.color, "#D62728");
  assert.deepEqual(
    plotted[0].data,
    module.rows.map((row) => Number(row[1])),
  );
  assert.equal(gcReferenceUnavailable(module), true);
  assert.equal(scientificColor(name, "Theoretical Distribution", 1), "#1F77B4");
  assert.equal(
    gcReferenceUnavailable({
      ...module,
      columns: [...module.columns, "Theoretical Distribution"],
    }),
    false,
  );
  assert.ok(
    series(comparisonChartOptions(r1, r2, name)).every(
      (item) => item.lineStyle!.color === "#D62728",
    ),
  );
});

test("only per-base Phred charts receive quality bands; distributions retain actual counts and tile deviations", () => {
  for (const name of [
    "Per base sequence content",
    "Per base N content",
    "Adapter Content",
  ]) {
    for (const option of [
      chartOptions(r1, name),
      comparisonChartOptions(r1, r2, name),
    ]) {
      assert.equal((option.yAxis as { min: number; max: number }).min, 0);
      assert.equal((option.yAxis as { min: number; max: number }).max, 100);
    }
  }
  for (const module of r1.modules.filter(
    (module) => !tableOnly(module) && module.name !== quality,
  )) {
    const option = chartOptions(r1, module.name);
    assert.ok(series(option).every((item) => !item.markArea));
    if (
      ["Per sequence quality scores", "Sequence Length Distribution"].includes(
        module.name,
      )
    )
      assert.equal(series(option)[0].type, "line");
  }
  const tile = chartOptions(r1, "Per tile sequence quality");
  const scale = tile.visualMap as { max: number; inRange: { color: string[] } };
  assert.equal(scale.max, 0);
  assert.deepEqual(scale.inRange.color, fastqcColors.tile);
  assert.deepEqual(
    (series(tile)[0].data as number[][]).map((point) => point[2]),
    findModule(r1, "Per tile sequence quality")!.rows.map((row) =>
      Number(row[2]),
    ),
  );
});

test("paired quality read colors, legends, missing values and grouped bins remain intact", () => {
  const option = comparisonChartOptions(r1, r2, quality, true),
    plotted = series(option);
  assert.deepEqual(
    plotted.slice(0, 4).map((item) => item.lineStyle!.color),
    ["#1F77B4", "#1F77B4", "#D97706", "#D97706"],
  );
  assert.deepEqual(
    (option.legend as { data: string[] }).data,
    plotted.slice(0, 4).map((item) => item.name),
  );
  assert.ok((option.xAxis as { data: string[] }).data.includes("10-14"));
  assert.ok(!(option.xAxis as { data: string[] }).data.includes("10"));
});

test("neutral application text, accent and semantic statuses meet AA contrast on their surfaces", () => {
  const css = readFileSync(
    new URL("../src/styles.css", import.meta.url),
    "utf8",
  );
  const tokens = Object.fromEntries(
    [...css.matchAll(/--([\w-]+):\s*(#[\da-fA-F]{6});/g)].map((match) => [
      match[1],
      match[2],
    ]),
  );
  const luminance = (hex: string) => {
    const channels = hex
      .slice(1)
      .match(/../g)!
      .map((value) => parseInt(value, 16) / 255)
      .map((value) =>
        value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
      );
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  };
  for (const [foreground, backgrounds] of [
    ["text", ["surface", "background", "sidebar"]],
    ["text-secondary", ["surface", "surface-muted", "sidebar", "selected"]],
    ["accent", ["surface", "selected", "selected-hover"]],
    ["surface", ["accent", "accent-hover"]],
    ["success", ["success-bg"]],
    ["warning", ["warning-bg"]],
    ["error", ["error-bg"]],
    ["inverse-text", ["inverse-bg"]],
  ] as [string, string[]][])
    for (const background of backgrounds) {
      const values = [
        luminance(tokens[foreground]),
        luminance(tokens[background]),
      ].sort((a, b) => a - b);
      assert.ok(
        (values[1] + 0.05) / (values[0] + 0.05) >= 4.5,
        `${foreground} on ${background}`,
      );
    }
  assert.equal(tokens.accent.toLowerCase(), "#315d8f");
  assert.ok(!css.includes("var(--green)"));
});
