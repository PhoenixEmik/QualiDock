import type * as echarts from "echarts";
import type { Sample } from "./types";
import { chartOptions } from "./chartOptions.ts";
import { compareModules, comparisonTooltip } from "./comparison.ts";
import { inputFilename, moduleKey } from "./qc.ts";
import { fastqcColors, scientificColor } from "./fastqcTheme.ts";
import { qualityRegions, qualityUpperLimit } from "./qualityPlot.ts";

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
  const columns = [
    ...new Set(comparison.series.map((series) => series.column)),
  ];
  const maxQuality = qualityUpperLimit([r1, r2]);
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
      ...(quality ? { max: maxQuality } : {}),
    },
    legend: {
      ...option.legend,
      data: comparison.series.map((series) => series.name),
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
    series: [
      ...comparison.series.map((series): echarts.LineSeriesOption => {
        const color = quality
          ? fastqcColors.reads[series.read === "R1" ? 0 : 1]
          : scientificColor(
              metric,
              series.column,
              columns.indexOf(series.column),
            );
        return {
          name: series.name,
          type: "line",
          data: series.data,
          connectNulls: false,
          showSymbol:
            series.data.filter((value) => value !== null).length === 1,
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
      ...(quality ? [qualityRegions(maxQuality)] : []),
    ],
  };
}
