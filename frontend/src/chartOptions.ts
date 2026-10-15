import type * as echarts from "echarts";
import type { Sample } from "./types";
import {
  chartData,
  findModule,
  rowTooltip,
  numeric,
  qualityData,
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
  const isQuality = metric === "Per base sequence quality";
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
        name: "10th–90th percentile",
        type: "boxplot",
        itemStyle: { color: "#dcebe0", borderColor: "#81a994" },
        data: reportedQuality.boxes.map((box) =>
          box.map((value) => value ?? NaN),
        ),
      },
      {
        name: "Mean quality",
        type: "line",
        data: reportedQuality.means,
        symbol: quality.length === 1 ? "circle" : "none",
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
  return {
    animation: false,
    textStyle: {
      fontFamily: "Inter, -apple-system, sans-serif",
      color: "#52665c",
    },
    grid: { left: 60, right: heatmap ? 85 : 24, top: 30, bottom: 100 },
    tooltip: {
      trigger: heatmap || isQuality ? "item" : "axis",
      renderMode: "richText",
      confine: true,
      formatter: (params: unknown) => {
        const p = (Array.isArray(params) ? params[0] : params) as {
          dataIndex: number;
        };
        const index = heatmap
          ? module.rows.filter((row) => numeric(row[2]) !== null)[p.dataIndex]
          : null;
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
          bottom: 0,
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
      axisLabel: { fontSize: 10 },
    },
    yAxis: {
      type: heatmap ? "category" : "value",
      data: heatmap ? data.tiles : undefined,
      min: isQuality ? 0 : undefined,
      max: isQuality ? Math.ceil(maxQuality / 5) * 5 : undefined,
      name: heatmap ? "Tile" : isQuality ? "Phred score" : undefined,
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
      { type: "inside" },
      {
        type: "slider",
        height: 12,
        bottom: 50,
        borderColor: "transparent",
        backgroundColor: "#f1f4f1",
        fillerColor: "#dbe6de",
        handleStyle: { color: "#5c8f77" },
      },
    ],
    series,
  };
}
