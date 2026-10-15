import type { CustomSeriesRenderItem, LineSeriesOption } from "echarts";
import type { Sample } from "./types";
import { fastqcColors } from "./fastqcTheme.ts";

export function qualityUpperLimit(samples: Sample[]) {
  const max = samples.reduce(
    (limit, sample) =>
      sample.per_base_quality.reduce(
        (value, bin) =>
          Math.max(
            value,
            ...[
              bin.mean,
              bin.median,
              bin.lower_quartile,
              bin.upper_quartile,
              bin.percentile_10,
              bin.percentile_90,
            ].filter(
              (number): number is number =>
                number !== null && Number.isFinite(number),
            ),
          ),
        limit,
      ),
    45,
  );
  return Math.ceil(max / 5) * 5;
}

/** A separate, silent layer keeps regions visible when statistical series are hidden.
 * These visual regions are not the module's configurable PASS/WARN/FAIL rules.
 */
export function qualityRegions(max: number): LineSeriesOption {
  return {
    name: "Quality regions",
    type: "line",
    data: [],
    silent: true,
    z: -10,
    tooltip: { show: false },
    markArea: {
      silent: true,
      label: { show: false },
      emphasis: { disabled: true },
      data: [
        [
          { yAxis: 0, itemStyle: { color: fastqcColors.quality.poor } },
          { yAxis: 20 },
        ],
        [
          { yAxis: 20, itemStyle: { color: fastqcColors.quality.reasonable } },
          { yAxis: 28 },
        ],
        [
          { yAxis: 28, itemStyle: { color: fastqcColors.quality.good } },
          { yAxis: max },
        ],
      ],
    },
  };
}

/** Draw only the five reported quantiles, in the existing p10/q1/median/q3/p90 order.
 * A median is an independent horizontal segment inside each box, never a curve.
 */
export const renderQualityBox: CustomSeriesRenderItem = (params, api) => {
  const values = [0, 1, 2, 3, 4].map((i) => api.value(i));
  if (
    !values.every(
      (value): value is number =>
        typeof value === "number" && Number.isFinite(value),
    )
  )
    return;
  const points = values.map((value) => api.coord([params.dataIndex, value]));
  if (points.some((point) => point.some((value) => !Number.isFinite(value))))
    return;
  const x = points[0][0];
  const region = params.coordSys as unknown as {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  if (x < region.x || x > region.x + region.width) return;
  const size = api.size?.([1, 0]);
  const width = Math.max(
    1,
    Math.min(48, Math.abs(Array.isArray(size) ? size[0] : 1) * 0.8),
  );
  const left = x - width / 2,
    right = x + width / 2;
  const [low, q1, median, q3, high] = points.map((point) => point[1]);
  const line = (
    x1: number,
    y1: number,
    x2: number,
    y2: number,
    stroke = fastqcColors.quality.whisker,
  ) => ({
    type: "line" as const,
    shape: { x1, y1, x2, y2 },
    style: { stroke, lineWidth: 1.2 },
  });
  return {
    type: "group",
    children: [
      line(x, low, x, q1),
      line(left, low, right, low),
      line(x, q3, x, high),
      line(left, high, right, high),
      {
        type: "rect",
        shape: { x: left, y: q3, width, height: q1 - q3 },
        style: {
          fill: fastqcColors.quality.box,
          stroke: fastqcColors.quality.whisker,
          lineWidth: 1,
        },
      },
      line(left, median, right, median, fastqcColors.quality.median),
    ],
  };
};
