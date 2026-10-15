import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { Sample } from "./types";
import { findModule } from "./qc";
import { chartOptions } from "./chartOptions";

export default function QualityChart({
  sample,
  metric,
}: {
  sample: Sample;
  metric: string;
}) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const module = findModule(sample, metric);
    if (!element.current || !module) return;
    const chart = echarts.init(element.current, undefined, {
      renderer: "canvas",
    });
    chart.setOption(chartOptions(sample, metric));
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
      aria-label={`${metric} for ${sample.name}. Interactive chart; exact values are also available in the data table.`}
    />
  );
}
