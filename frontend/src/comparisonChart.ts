import type * as echarts from "echarts";
import type { Sample } from "./types";
import { chartOptions } from "./chartOptions.ts";
import { compareModules, comparisonTooltip } from "./comparison.ts";
import { inputFilename, moduleKey } from "./qc.ts";

export function comparisonChartOptions(
  r1: Sample,
  r2: Sample,
  metric: string,
  median = false,
): echarts.EChartsOption {
  const comparison = compareModules(r1, r2, metric, median);
  if (comparison.mode !== "overlay") return {};
  const option = chartOptions(r1, metric);
  const quality = moduleKey(metric) === "perbasesequencequality";
  const bases = moduleKey(metric) === "perbasesequencecontent";
  const palette = [
    "#256c54",
    "#4668a5",
    "#9b702b",
    "#ab5650",
    "#75608e",
    "#4e7780",
  ];
  const baseColors: Record<string, string> = {
    A: "#256c54",
    C: "#4668a5",
    G: "#9b702b",
    T: "#ab5650",
  };
  const columns = [
    ...new Set(comparison.series.map((series) => series.column)),
  ];
  const maxQuality = [r1, r2].reduce(
    (max, sample) =>
      sample.per_base_quality.reduce(
        (value, bin) => Math.max(value, bin.mean ?? 0, bin.percentile_90 ?? 0),
        max,
      ),
    45,
  );
  return {
    ...option,
    xAxis: {
      ...option.xAxis,
      type: "category",
      data: comparison.categories,
      axisPointer: { show: true, snap: true },
    },
    yAxis: {
      ...option.yAxis,
      max: quality ? Math.ceil(maxQuality / 5) * 5 : undefined,
    },
    tooltip: {
      trigger: "axis",
      confine: true,
      renderMode: "richText",
      formatter: (params: unknown) => {
        const point = (Array.isArray(params) ? params[0] : params) as
          { dataIndex?: number } | undefined;
        return point?.dataIndex === undefined
          ? "Unavailable"
          : comparisonTooltip(comparison, point.dataIndex, [
              inputFilename(r1),
              inputFilename(r2),
            ]);
      },
    },
    series: comparison.series.map((series) => {
      const color =
        quality || columns.length === 1
          ? palette[series.read === "R1" ? 0 : 1]
          : bases
            ? baseColors[series.column] ||
              palette[columns.indexOf(series.column) % palette.length]
            : palette[columns.indexOf(series.column) % palette.length];
      return {
        name: series.name,
        type: "line",
        data: series.data,
        connectNulls: false,
        showSymbol: series.data.filter((value) => value !== null).length === 1,
        symbol: series.read === "R1" ? "circle" : "triangle",
        symbolSize: 5,
        lineStyle: {
          color,
          type: series.read === "R1" ? "solid" : "dashed",
          width: series.column === "Median" ? 1 : 2,
          opacity: series.column === "Median" ? 0.65 : 1,
        },
        itemStyle: { color },
        emphasis: { focus: "series" },
      };
    }),
  };
}
