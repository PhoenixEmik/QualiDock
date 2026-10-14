import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { Sample } from "./types";

export default function QualityChart({
  sample,
  metric,
}: {
  sample: Sample;
  metric: string;
}) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current) return;
    const chart = echarts.init(element.current, undefined, {
      renderer: "canvas",
    });
    const quality = sample.per_base_quality;
    const module = sample.modules.find((m) => m.name === metric);
    const isQuality = metric === "Per base sequence quality";
    const maxQuality = quality.reduce(
      (max, b) => Math.max(max, b.percentile_90 ?? 0, b.mean ?? 0),
      45,
    );
    const rows = module?.rows || [];
    const categories = isQuality
      ? quality.map((b) => b.base)
      : rows.map((r) => r[0]);
    const palette = ["#25745b", "#74a68d", "#ce954c", "#697fbd", "#ae6d7a"];
    const series: echarts.SeriesOption[] = isQuality
      ? [
          {
            name: "10th–90th percentile",
            type: "boxplot",
            itemStyle: { color: "#dcebe0", borderColor: "#81a994" },
            data: quality.map((b) => [
              b.percentile_10 ?? NaN,
              b.lower_quartile ?? NaN,
              b.median ?? NaN,
              b.upper_quartile ?? NaN,
              b.percentile_90 ?? NaN,
            ]),
            tooltip: {
              formatter: (p: unknown) => {
                const v = p as { dataIndex: number };
                const b = quality[v.dataIndex];
                return `Base ${b.base}\n90th percentile: ${b.percentile_90}\nUpper quartile: ${b.upper_quartile}\nMedian: ${b.median}\nLower quartile: ${b.lower_quartile}\n10th percentile: ${b.percentile_10}`;
              },
            },
          },
          {
            name: "Mean quality",
            type: "line",
            data: quality.map((b) => b.mean),
            symbol: "none",
            lineStyle: { color: "#25745b", width: 2.5 },
            itemStyle: { color: "#25745b" },
            markArea: {
              silent: true,
              itemStyle: { opacity: 0.3 },
              data: [
                [{ yAxis: 0, itemStyle: { color: "#f9dddd" } }, { yAxis: 20 }],
                [{ yAxis: 20, itemStyle: { color: "#f6ebcb" } }, { yAxis: 28 }],
                [
                  { yAxis: 28, itemStyle: { color: "#e4f0e5" } },
                  { yAxis: Math.ceil(maxQuality / 5) * 5 },
                ],
              ],
            },
          },
        ]
      : (module?.columns.slice(1) || []).map((name, index) => ({
          name,
          type: "line",
          showSymbol: false,
          data: rows.map((r) => {
            const raw = r[index + 1];
            if (raw === undefined || raw.trim() === "") return null;
            const n = Number(raw);
            return Number.isFinite(n) ? n : null;
          }),
          lineStyle: { width: 2, color: palette[index % palette.length] },
          itemStyle: { color: palette[index % palette.length] },
        }));
    chart.setOption({
      animationDuration: 400,
      textStyle: {
        fontFamily: "Inter, -apple-system, sans-serif",
        color: "#71807b",
      },
      grid: { left: 48, right: 24, top: 25, bottom: 80 },
      tooltip: {
        trigger: isQuality ? "item" : "axis",
        renderMode: "richText",
        confine: true,
      },
      legend: {
        bottom: 4,
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { fontSize: 11 },
      },
      xAxis: {
        type: "category",
        data: categories,
        name: isQuality
          ? "Position in read (bp)"
          : module?.columns[0] || "Position",
        nameLocation: "middle",
        nameGap: 32,
        axisLine: { lineStyle: { color: "#e3e8e5" } },
        axisTick: { show: false },
        axisLabel: { fontSize: 10, interval: "auto" },
      },
      yAxis: {
        type: "value",
        min: isQuality ? 0 : undefined,
        max: isQuality ? Math.ceil(maxQuality / 5) * 5 : undefined,
        name: isQuality ? "Phred score" : undefined,
        nameTextStyle: { padding: [0, 0, 10, 0] },
        splitLine: { lineStyle: { color: "#e8ece9", type: "dashed" } },
        axisLabel: { fontSize: 10 },
      },
      dataZoom: [
        { type: "inside" },
        {
          type: "slider",
          height: 12,
          bottom: 35,
          borderColor: "transparent",
          backgroundColor: "#f1f4f1",
          fillerColor: "#dbe6de",
          handleStyle: { color: "#5c8f77" },
        },
      ],
      series,
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [sample, metric]);
  return (
    <div
      ref={element}
      className="quality-chart"
      role="img"
      aria-label={`${metric} for ${sample.name}. Interactive chart; use scroll to zoom.`}
    />
  );
}
