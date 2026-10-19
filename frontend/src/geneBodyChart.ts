import type { NativePlotView } from "./AnalyticsChart";
import { overlayColors } from "./fastqcTheme.ts";

/** Plot only the exact original 1–100 table, never the normalized R curve. */
export function geneBodyView(rows: string[][], sample: string): NativePlotView {
  const name = "RSeQC reported coverage";
  return {
    description: `Gene-body coverage for ${sample}, 5′ to 3′. Exact original values in the table.`,
    summary: "100 reported gene-body percentiles · 5′ → 3′ · no application normalization",
    series: [{ name, label: name }],
    options: {
      animation: false,
      legend: { show: false, data: [name] },
      grid: { left: 80, right: 30, top: 45, bottom: 115 },
      tooltip: { trigger: "axis", confine: true, renderMode: "richText", formatter: ((items: {data?: {raw: string[]}}[]) => {
        const raw = items[0]?.data?.raw;
        return raw ? `Gene-body percentile: ${raw[0]}\nRSeQC reported coverage: ${raw[1]}\nDirection: 5′ → 3′` : "Unavailable";
      }) as never },
      xAxis: { type: "value", min: 1, max: 100, minInterval: 1, name: "Gene-body percentile · 5′ (1) → 3′ (100)", nameLocation: "middle", nameGap: 32 },
      yAxis: { type: "value", min: 0, name: "RSeQC reported coverage" },
      dataZoom: [{ type: "inside", filterMode: "none" }, { type: "slider", bottom: 45, height: 18, filterMode: "none" }],
      series: [{ name, type: "line", smooth: false, connectNulls: false, showSymbol: false,
        lineStyle: {color: overlayColors[0], width: 2}, itemStyle: {color: overlayColors[0]},
        data: rows.map(raw => ({value: [Number(raw[0]), Number(raw[1])], raw})) }],
    },
  };
}
