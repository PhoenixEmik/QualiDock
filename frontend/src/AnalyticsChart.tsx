import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import type { Overlay } from "./analytics";
import { overlayOptions } from "./multiSampleChart";

export function saveFile(content: BlobPart, filename: string, type: string) {
  const href = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}
export interface NativePlotView {
  options: echarts.EChartsOption;
  description: string;
  summary: string;
  series: { name: string; label: string }[];
}
export default function AnalyticsChart({
  group,
  quality,
}: {
  group: Overlay;
  quality: boolean;
}) {
  const view = useMemo(
    () => ({
      options: overlayOptions(group, quality),
      description: `Multi-sample ${group.unit}; exact source values available as CSV or TSV`,
      summary: `${group.members.length} read files · ${group.unit}`,
      series: group.series.map((series) => ({
        name: series.name,
        label: `${series.entity.name} · ${series.column}`,
      })),
    }),
    [group, quality],
  );
  return <NativePlot view={view} />;
}

/** Shared existing ECharts lifecycle/exports; no alternate charting framework. */
export function NativePlot({ view }: { view: NativePlotView }) {
  const element = useRef<HTMLDivElement>(null),
    instance = useRef<echarts.ECharts | null>(null);
  const [error, setError] = useState("");
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!element.current) return;
    const chart = echarts.init(element.current, undefined, {
      renderer: "canvas",
    });
    instance.current = chart;
    setHidden(new Set());
    chart.setOption(view.options);
    chart.on("legendselectchanged", (event: unknown) => {
      const selected = (event as { selected: Record<string, boolean> })
        .selected;
      setHidden(
        new Set(Object.keys(selected).filter((name) => !selected[name])),
      );
    });
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
  }, [view]);
  const download = (type: "png" | "svg") => {
    const chart = instance.current;
    if (!chart) return;
    try {
      setError("");
      if (type === "png") {
        const a = document.createElement("a");
        a.href = chart.getDataURL({
          type: "png",
          pixelRatio: 2,
          backgroundColor: "#fff",
        });
        a.download = "qualidock-comparison.png";
        a.click();
      } else {
        const svg = echarts.init(null, undefined, {
          renderer: "svg",
          ssr: true,
          width: chart.getWidth(),
          height: chart.getHeight(),
        });
        try {
          svg.setOption({ ...chart.getOption(), backgroundColor: "#fff" });
          saveFile(
            svg.renderToSVGString(),
            "qualidock-comparison.svg",
            "image/svg+xml",
          );
        } finally {
          svg.dispose();
        }
      }
    } catch {
      setError(
        "Chart export failed. Source CSV and TSV exports remain available.",
      );
    }
  };
  return (
    <section className="analytics-plot">
      <div className="analytics-actions">
        <span>{view.summary}</span>
        <button
          className="button small"
          onClick={() =>
            instance.current?.dispatchAction({
              type: "dataZoom",
              start: 0,
              end: 100,
            })
          }
        >
          Reset zoom
        </button>
        <button className="button small" onClick={() => download("png")}>
          Export PNG
        </button>
        <button className="button small" onClick={() => download("svg")}>
          Export SVG
        </button>
      </div>
      <details className="analytics-series">
        <summary>Series visibility ({view.series.length})</summary>
        <div className="analytics-actions">
          {view.series.map((series) => (
            <label key={series.name}>
              <input
                type="checkbox"
                checked={!hidden.has(series.name)}
                aria-label={`Show ${series.name}`}
                onChange={(event) => {
                  const next = new Set(hidden);
                  if (event.target.checked) next.delete(series.name);
                  else next.add(series.name);
                  setHidden(next);
                  instance.current?.dispatchAction({
                    type: event.target.checked
                      ? "legendSelect"
                      : "legendUnSelect",
                    name: series.name,
                  });
                }}
              />
              {series.label}
            </label>
          ))}
        </div>
      </details>
      <div
        ref={element}
        className="quality-chart"
        role="img"
        aria-label={view.description}
      />
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
