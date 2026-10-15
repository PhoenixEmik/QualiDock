import type * as echarts from "echarts";
import type { Overlay } from "./analytics";
import { qualityRegions, qualityUpperLimit } from "./qualityPlot.ts";
import { overlayColors } from "./fastqcTheme.ts";
export function overlayOptions(
  group: Overlay,
  quality: boolean,
): echarts.EChartsOption {
  const maximum = qualityUpperLimit(
    group.members.flatMap((s) => (s.fastqc ? [s.fastqc] : [])),
  );
  return {
    animation: false,
    aria: { enabled: true },
    grid: { left: 72, right: 24, top: 45, bottom: 130 },
    legend: {
      type: "scroll",
      bottom: 0,
      textStyle: { color: "#475467" },
      data: group.series.map((s) => s.name),
      formatter: (name: string) =>
        name.length > 65 ? name.slice(0, 62) + "…" : name,
    },
    tooltip: {
      trigger: "axis",
      renderMode: "richText",
      confine: true,
      position: ["5%", 10],
      formatter: (params: unknown) => {
        const points = (Array.isArray(params) ? params : []) as {
          seriesName: string;
          dataIndex: number;
        }[];
        return points
          .map((point) => {
            const series = group.series.find(
              (s) => s.name === point.seriesName,
            );
            return series
              ? `${series.entity.name} · ${series.column}\n${group.categories[point.dataIndex]}: ${series.raw[point.dataIndex] ?? "Unavailable"}${group.unit === "Sequences (%)" ? ` counts; ${series.values[point.dataIndex] ?? "Unavailable"}% (Total Sequences ${series.entity.fastqc?.total_sequences})` : ""}`
              : "";
          })
          .filter(Boolean)
          .join("\n\n");
      },
    },
    xAxis: {
      type: "category",
      data: group.categories,
      boundaryGap: false,
      name: "Original reported bins",
      nameLocation: "middle",
      nameGap: 30,
      axisLabel: { hideOverlap: true },
    },
    yAxis: {
      type: "value",
      min: 0,
      ...(quality ? { max: maximum } : {}),
      name: group.unit,
      nameLocation: "end",
      splitLine: { lineStyle: { color: "#D9DEE5", type: "dashed" } },
    },
    dataZoom: [
      { type: "inside", filterMode: "none" },
      { type: "slider", bottom: 55, height: 16, filterMode: "none" },
    ],
    series: [
      ...group.series.map((series): echarts.LineSeriesOption => ({
        name: series.name,
        type: "line",
        smooth: false,
        connectNulls: false,
        showSymbol: group.categories.length < 25,
        symbolSize: 5,
        data: series.values,
        lineStyle: {
          color:
            overlayColors[
              group.members.findIndex((m) => m.id === series.entity.id) %
                overlayColors.length
            ],
          width: 2,
          type: ["solid", "dashed", "dotted"][
            [...new Set(group.series.map((s) => s.column))].indexOf(
              series.column,
            ) % 3
          ] as "solid" | "dashed" | "dotted",
        },
        itemStyle: {
          color:
            overlayColors[
              group.members.findIndex((m) => m.id === series.entity.id) %
                overlayColors.length
            ],
        },
      })),
      ...(quality ? [qualityRegions(maximum)] : []),
    ],
  };
}
