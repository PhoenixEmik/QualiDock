import type * as echarts from "echarts";
import type { Sample } from "./types";
import {
  chartData,
  findModule,
  rowTooltip,
  numeric,
  qualityData,
  moduleKey,
} from "./qc.ts";

/** Only arrange FastQC's reported points; do not derive scientific statistics. */
export function chartOptions(
  sample: Sample,
  metric: string,
): echarts.EChartsOption {
  const module = findModule(sample, metric);
  if (!module) return {};
  const quality = sample.per_base_quality;
  const reportedQuality = qualityData(sample);
  const isQuality = moduleKey(metric) === "perbasesequencequality";
  const data = chartData(module);
  const heatmap = data.kind === "heatmap";
  const palette = [
    "#25745b",
    "#74a68d",
    "#ce954c",
    "#697fbd",
    "#ae6d7a",
    "#67734c",
  ];
  const maxQuality = quality.reduce(
    (max, b) => Math.max(max, b.percentile_90 ?? 0, b.mean ?? 0),
    45,
  );
  let series: echarts.SeriesOption[];
  if (isQuality) {
    series = [
      {
        name: "Quartiles · 10th–90th whiskers",
        type: "boxplot",
        itemStyle: { color: "#dcebe0", borderColor: "#81a994" },
        data: reportedQuality.boxes.map((box) =>
          box.some((value) => value === null || !Number.isFinite(value))
            ? [NaN, NaN, NaN, NaN, NaN]
            : (box as number[]),
        ),
      },
      {
        name: "Mean quality",
        type: "line",
        data: reportedQuality.means,
        connectNulls: false,
        symbol:
          reportedQuality.means.filter((value) => value !== null).length === 1
            ? "circle"
            : "none",
        lineStyle: { color: palette[0], width: 2.5 },
        itemStyle: { color: palette[0] },
      },
    ];
  } else if (heatmap) {
    series = [
      {
        name: module.columns[2],
        type: "heatmap",
        data: data.series[0].data.filter(
          (point) => Array.isArray(point) && point[2] !== null,
        ),
        progressive: 1000,
      } as echarts.SeriesOption,
    ];
  } else {
    series = data.series.map(
      (series, index) =>
        ({
          name: series.name,
          type: data.kind,
          showSymbol: module.rows.length === 1,
          connectNulls: false,
          data: series.data,
          lineStyle: { width: 2, color: palette[index % palette.length] },
          itemStyle: { color: palette[index % palette.length] },
        }) as echarts.SeriesOption,
    );
  }
  const tileValues = heatmap
    ? module.rows
        .map((row) => numeric(row[2]))
        .filter((value): value is number => value !== null)
    : [];
  const minimum = tileValues.reduce(
    (min, value) => Math.min(min, value),
    tileValues[0] ?? 0,
  );
  const maximum = tileValues.reduce(
    (max, value) => Math.max(max, value),
    tileValues[0] ?? 0,
  );
  const heatmapRows = heatmap
    ? module.rows.filter((row) => numeric(row[2]) !== null)
    : [];
  const units: Record<string, string> = {
    persequencequalityscores: "Read count",
    perbasesequencecontent: "Base content (%)",
    persequencegccontent: "Read count",
    perbasencontent: "N content (%)",
    sequencelengthdistribution: "Read count",
    sequenceduplicationlevels: "Percentage (%)",
    adaptercontent: "Adapter content (%)",
    pertilesequencequality: "Tile",
    kmercontent: "Observed / expected",
  };
  return {
    animation: false,
    textStyle: {
      fontFamily: "Inter, -apple-system, sans-serif",
      color: "#52665c",
    },
    // Reserve separate rows for axis labels/title, zoom controls, and legend.
    grid: { left: 60, right: heatmap ? 85 : 24, top: 30, bottom: 124 },
    tooltip: {
      trigger: heatmap || isQuality ? "item" : "axis",
      renderMode: "richText",
      confine: true,
      formatter: (params: unknown) => {
        const p = (Array.isArray(params) ? params[0] : params) as
          | {
              dataIndex: number;
            }
          | undefined;
        if (!p) return "Unavailable";
        const index = heatmap ? heatmapRows[p.dataIndex] : null;
        if (index)
          return module.columns
            .map((name, i) => `${name}: ${index[i] ?? "Unavailable"}`)
            .join("\n");
        return rowTooltip(module, p.dataIndex);
      },
    },
    legend: heatmap
      ? undefined
      : {
          type: "scroll",
          bottom: 4,
          itemWidth: 14,
          itemHeight: 8,
          textStyle: { fontSize: 11 },
        },
    xAxis: {
      type: "category",
      data: isQuality ? quality.map((b) => b.base) : data.categories,
      name: isQuality
        ? "Position in read (bp)"
        : module.columns[heatmap ? 1 : 0],
      nameLocation: "middle",
      nameGap: 32,
      axisTick: { show: false },
      axisLabel: { fontSize: 10, hideOverlap: true },
    },
    yAxis: {
      type: heatmap ? "category" : "value",
      data: heatmap ? data.tiles : undefined,
      min: isQuality ? 0 : undefined,
      max: isQuality ? Math.ceil(maxQuality / 5) * 5 : undefined,
      name: isQuality ? "Phred score" : units[moduleKey(metric)],
      nameTextStyle: { fontSize: 10 },
      splitLine: { lineStyle: { color: "#e8ece9", type: "dashed" } },
      axisLabel: { fontSize: 10 },
    },
    visualMap: heatmap
      ? {
          min: minimum,
          max: maximum,
          calculable: true,
          orient: "vertical",
          right: 0,
          top: "middle",
          inRange: { color: ["#ae6d7a", "#f2f1df", "#25745b"] },
          text: [String(maximum), String(minimum)],
        }
      : undefined,
    dataZoom: [
      { type: "inside", filterMode: "empty" },
      {
        type: "slider",
        filterMode: "empty",
        height: 14,
        bottom: 40,
        brushSelect: false,
        borderColor: "transparent",
        backgroundColor: "#f1f4f1",
        fillerColor: "#dbe6de",
        dataBackground: {
          lineStyle: { color: "#81a994" },
          areaStyle: { color: "#dcebe0" },
        },
        selectedDataBackground: {
          lineStyle: { color: "#5c8f77" },
          areaStyle: { color: "#b9d4c4" },
        },
        handleStyle: { color: "#5c8f77" },
      },
    ],
    series,
  };
}
