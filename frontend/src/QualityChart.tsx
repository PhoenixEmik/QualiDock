import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { Sample } from "./types";
import { findModule } from "./qc";
import { chartOptions } from "./chartOptions";
import { comparisonChartOptions } from "./comparisonChart";

export default function QualityChart({
  sample,
  metric,
  mate,
  median = false,
  visibility,
}: {
  sample: Sample;
  metric: string;
  mate?: Sample;
  median?: boolean;
  visibility?: Record<string, boolean>;
}) {
  const element = useRef<HTMLDivElement>(null);
  const instance = useRef<echarts.ECharts | null>(null);
  useEffect(() => {
    const module = findModule(sample, metric);
    if (!element.current || !module) return;
    const chart = echarts.init(element.current, undefined, {
      renderer: "canvas",
    });
    instance.current = chart;
    chart.setOption(
      mate
        ? comparisonChartOptions(sample, mate, metric, median)
        : chartOptions(sample, metric),
    );
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => chart.resize());
    });
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      chart.dispose();
      instance.current = null;
    };
  }, [sample, metric, mate, median]);
  useEffect(() => {
    if (!visibility || !instance.current) return;
    const series = instance.current.getOption().series as { name: string }[];
    instance.current.setOption({
      legend: {
        selectedMode: false,
        selected: Object.fromEntries(
          series.map((series) => [
            series.name,
            visibility[series.name] !== false,
          ]),
        ),
      },
    });
  }, [visibility, sample, metric, mate, median]);
  return (
    <div
      ref={element}
      className="quality-chart"
      role="img"
      aria-label={`${metric} for ${sample.name}${mate ? ` and ${mate.name}` : ""}. Interactive chart; exact values are also available in Raw Data.`}
    />
  );
}
