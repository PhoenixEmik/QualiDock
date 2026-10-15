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
import {
  fastqcColors,
  scientificColor,
  scientificLabel,
} from "./fastqcTheme.ts";
import {
  qualityRegions,
  qualityUpperLimit,
  renderQualityBox,
} from "./qualityPlot.ts";

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
  const percentage = [
    "perbasesequencecontent",
    "perbasencontent",
    "adaptercontent",
  ].includes(moduleKey(metric));
  const basePosition = isQuality || percentage || heatmap;
  const maxQuality = qualityUpperLimit([sample]);
  let series: echarts.SeriesOption[];
  if (isQuality) {
    series = [
      {
        name: "Quartiles · 10th–90th whiskers",
        type: "custom",
        renderItem: renderQualityBox,
        clip: true,
        // The category index is supplied to coord() directly; all data dimensions
        // are original quantiles. Zoom clips the glyph without rewriting bins.
        encode: { x: -1, y: [0, 1, 2, 3, 4] },
        itemStyle: {
          color: fastqcColors.quality.box,
          borderColor: fastqcColors.quality.whisker,
        },
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
        lineStyle: { color: fastqcColors.quality.mean, width: 2 },
        itemStyle: { color: fastqcColors.quality.mean },
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
          name: scientificLabel(metric, series.name),
          type:
            data.kind === "bar" && moduleKey(metric) !== "kmercontent"
              ? "line"
              : data.kind,
          showSymbol: module.rows.length === 1,
          connectNulls: false,
          data: series.data,
          lineStyle: {
            width: 2,
            color: scientificColor(metric, series.name, index),
          },
          itemStyle: { color: scientificColor(metric, series.name, index) },
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
  const legendNames = series.map((series) => series.name as string);
  if (isQuality) series.push(qualityRegions(maxQuality));
  return {
    animation: false,
    textStyle: {
      fontFamily: "Inter, -apple-system, sans-serif",
      color: fastqcColors.chrome.text,
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
          data: legendNames,
        },
    xAxis: {
      type: "category",
      data: isQuality ? quality.map((b) => b.base) : data.categories,
      name: basePosition
        ? "Position in read (bp)"
        : module.columns[heatmap ? 1 : 0],
      nameLocation: "middle",
      nameGap: 32,
      axisTick: { show: false },
      axisLabel: { fontSize: 11, hideOverlap: true },
      axisLine: { lineStyle: { color: fastqcColors.chrome.axis } },
    },
    yAxis: {
      type: heatmap ? "category" : "value",
      data: heatmap ? data.tiles : undefined,
      min: isQuality || percentage ? 0 : undefined,
      max: isQuality ? maxQuality : percentage ? 100 : undefined,
      name: isQuality ? "Phred score" : units[moduleKey(metric)],
      nameTextStyle: { fontSize: 10 },
      splitLine: {
        lineStyle: { color: fastqcColors.chrome.grid, type: "dashed" },
      },
      axisLabel: { fontSize: 11 },
    },
    visualMap: heatmap
      ? {
          min: Math.min(minimum, -1),
          max: 0,
          calculable: true,
          orient: "vertical",
          right: 0,
          top: "middle",
          inRange: { color: fastqcColors.tile },
          outOfRange: { color: fastqcColors.tile.at(-1) },
          text: ["≥ 0", String(Math.min(minimum, -1))],
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
        backgroundColor: fastqcColors.chrome.zoomBackground,
        fillerColor: fastqcColors.chrome.zoomFill,
        dataBackground: {
          lineStyle: { color: fastqcColors.chrome.zoomLine },
          areaStyle: { color: fastqcColors.chrome.zoomArea },
        },
        selectedDataBackground: {
          lineStyle: { color: fastqcColors.chrome.zoomLine },
          areaStyle: { color: fastqcColors.chrome.zoomArea },
        },
        handleStyle: { color: fastqcColors.chrome.zoomLine },
      },
    ],
    series,
  };
}
