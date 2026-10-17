import type { CoverageMetrics } from "./types";
import type { NativePlotView } from "./AnalyticsChart";
import { overlayColors } from "./fastqcTheme.ts";

/** Coordinates are reported CDF points, with no tail filling or normalization. */
export function coverageView(data: CoverageMetrics): NativePlotView {
  const points = data.distribution.rows
    .map(([depth, fraction]) => ({
      value: [Number(depth), Number(fraction)],
      raw: [depth, fraction],
    }))
    .sort((a, b) => a.value[0] - b.value[0]);
  const name = "Reported global CDF";
  return {
    description:
      "mosdepth cumulative coverage: exact reported fractions of reported reference bases at or above each depth. Raw values and original files are available below.",
    summary: `${data.reported_reference_bases} reported reference bases · original CDF`,
    series: [{ name, label: name }],
    options: {
      animation: false,
      grid: { left: 65, right: 24, top: 35, bottom: 110 },
      legend: { data: [name], bottom: 0 },
      tooltip: {
        trigger: "axis",
        renderMode: "richText",
        confine: true,
        position: ["5%", 10],
        formatter: (params: unknown) => {
          const raw = (params as { data: { raw: string[] } }[])?.[0]?.data?.raw;
          return raw
            ? `Depth ≥ ${raw[0]}×\nReported fraction: ${raw[1]}\nDenominator: ${data.reported_reference_bases} reported reference bases`
            : "Unavailable";
        },
      },
      xAxis: {
        type: "value",
        min: 0,
        minInterval: 1,
        name: "Depth (×)",
        nameLocation: "middle",
        nameGap: 30,
      },
      yAxis: { type: "value", min: 0, max: 1, name: "Fraction ≥ depth" },
      dataZoom: [
        { type: "inside", filterMode: "none" },
        { type: "slider", bottom: 45, height: 18, filterMode: "none" },
      ],
      series: [
        {
          name,
          type: "line",
          step: "end",
          showSymbol: true,
          connectNulls: false,
          data: points,
          lineStyle: { color: overlayColors[0], width: 2 },
          itemStyle: { color: overlayColors[0] },
        },
      ],
    },
  };
}
