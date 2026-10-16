import type * as echarts from "echarts";
import { overlayColors } from "./fastqcTheme.ts";
import type { NativePlotView } from "./AnalyticsChart";
export interface CohortContext {
  project_id: string;
  project_name: string;
  sample_id: string | null;
  sample_name: string;
  sequencing_run_id: string;
  run_name: string;
  platform: string;
  assay: string;
  library_type: string;
  input_stage?: string;
  stage_source?: string;
  sequenced_at: string | null;
  lane?: string | null;
  chunk?: string | null;
  read?: string | null;
}
export interface CohortSource {
  analysis_id: string;
  file_id: string;
  filename: string;
  report_id: string | null;
  tools?: Record<string, string | null>;
  metrics_sha256?: string | null;
  source_sha256?: string | null;
  integrity_task_id?: string | null;
}
export interface CohortPoint {
  id: string;
  file_id: string | null;
  filename?: string | null;
  context: CohortContext;
  metric: string;
  unit: string;
  value: number | null;
  raw_value: string | null;
  numerator?: number | null;
  denominator?: number | null;
  definition?: Record<string, unknown> | null;
  reason: string | null;
  group_id?: string;
  rule_result?: string | null;
  sources: CohortSource[];
  references?: CohortSource[];
  file_count?: number;
  context_note?: string | null;
  definition_note?: string;
}
export interface CohortResult {
  metric: { id: string; name: string; unit: string; description: string };
  group_by: "file" | "run";
  fingerprint: string;
  points: CohortPoint[];
  excluded: CohortPoint[];
  groups: {
    id: string;
    count: number;
    label: string;
    definition: Record<string, unknown>;
  }[];
  selected_group: string | null;
  total: number;
  excluded_total: number;
  offset: number;
  limit: number;
  facets: Record<string, string[]>;
  adapter_categories: string[];
  position_bins: string[];
  selector_limits: Record<string, boolean>;
  rule: { minimum_percent: string; meaning: string } | null;
  scope_note: string;
  unknown_stage_runs: {
    id: string;
    revision: number;
    project_id: string;
    name: string;
  }[];
  unknown_stage_run_total: number;
}
export const cohortMetrics = [
  ["q30_percent", "Q30 bases (%)"],
  ["q20_percent", "Q20 bases (%)"],
  ["reads", "Read records"],
  ["bases", "Sequenced bases"],
  ["length_min", "Minimum read length"],
  ["length_max", "Maximum read length"],
  ["gc_percent", "GC (FastQC reported)"],
  ["deduplicated_percent", "Estimated deduplicated fraction"],
  ["adapter_bin_percent", "Adapter content at reported bin"],
] as const;
export function pointLabel(point: CohortPoint): string {
  const c = point.context;
  return [
    c.run_name,
    c.sample_id ? c.sample_name : "Selected files",
    c.lane,
    c.chunk,
    c.read,
    point.filename,
  ]
    .filter(Boolean)
    .join(" · ");
}
/** Compact axis labels keep read/lane/chunk visible; full identity stays in tooltips/tables. */
export function compactPointLabel(point: CohortPoint): string {
  const shorten = (text: string, limit = 22) =>
    text.length > limit ? `${text.slice(0, 11)}…${text.slice(-10)}` : text;
  if (!point.file_id)
    return `${shorten(point.context.run_name)}\n${point.file_count ?? "?"} selected read files`;
  const filename = (point.filename ?? point.file_id).replace(
    /\.(fastq|fq)(\.gz)?$/i,
    "",
  );
  return [
    shorten(filename),
    [point.context.read, point.context.lane, point.context.chunk]
      .filter(Boolean)
      .join(" · "),
    shorten(point.context.run_name),
  ]
    .filter(Boolean)
    .join("\n");
}
export function cohortPlot(
  result: CohortResult,
  hidden: ReadonlySet<string> = new Set(),
): NativePlotView {
  const points = result.points.filter(
    (point) => !hidden.has(point.id) && point.value !== null,
  );
  const runs = [
    ...new Set(points.map((point) => point.context.sequencing_run_id)),
  ];
  const labels = new Map(
    runs.map((run) => [
      run,
      `${points.find((point) => point.context.sequencing_run_id === run)!.context.run_name} · ${run.slice(-8)}`,
    ]),
  );
  const series = runs.map((run, index) => {
    const members = points.filter(
      (point) => point.context.sequencing_run_id === run,
    );
    const shortLabel = labels.get(run)!;
    const label =
      [...labels.values()].filter((value) => value === shortLabel).length > 1
        ? `${members[0].context.run_name} · ${run}`
        : shortLabel;
    return {
      name: run,
      label,
      type: "bar" as const,
      color: overlayColors[index % overlayColors.length],
      data: points.map((point) =>
        point.context.sequencing_run_id === run ? point.value : null,
      ),
      barMaxWidth: 36,
      // Sparse run series never share a category; reuse its full bar slot even
      // for cohorts with many runs instead of allocating hundreds of empty slots.
      barGap: "-100%",
    };
  });
  const description = `Cross-run ${result.metric.name}; exact source values and denominators available in the provenance table and CSV/TSV`;
  const options: echarts.EChartsOption = {
    animation: false,
    aria: { enabled: true, label: { description } },
    grid: { left: 80, right: 24, top: 30, bottom: 150 },
    legend: {
      type: "scroll",
      bottom: 0,
      textStyle: { color: "#475467" },
      formatter: (name: string) =>
        series.find((entry) => entry.name === name)?.label ?? name,
    },
    xAxis: {
      type: "category",
      data: points.map(pointLabel),
      axisLabel: {
        color: "#475467",
        rotate: 0,
        hideOverlap: true,
        lineHeight: 15,
        margin: 12,
        formatter: (_value: string, index: number) =>
          compactPointLabel(points[index]),
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      ...(result.metric.unit === "%" ? { max: 100 } : {}),
      name: result.metric.unit,
      nameGap: 45,
      nameLocation: "middle",
      axisLabel: { color: "#475467" },
      splitLine: { lineStyle: { color: "#E2E5E9" } },
    },
    tooltip: {
      trigger: "axis",
      renderMode: "richText",
      confine: true,
      formatter: (params: unknown) => {
        const entries = params as { dataIndex: number; value: unknown }[];
        const entry = entries.find(
          (item) => item.value !== null && item.value !== undefined,
        );
        const point = entry ? points[entry.dataIndex] : undefined;
        if (!point) return "";
        return `${pointLabel(point)}\n${result.metric.name}: ${point.value} ${point.unit}\nRaw: ${point.raw_value ?? "unavailable"}${point.numerator !== null && point.numerator !== undefined ? `\n${point.numerator} / ${point.denominator} quality bases` : ""}\n${point.context.input_stage ?? "unknown"} · ${point.sources.map((s) => s.analysis_id.slice(-8)).join(", ")}${point.rule_result === "review" ? "\nReview: below user-declared reference" : ""}`;
      },
    },
    dataZoom: [
      {
        type: "inside",
        start: 0,
        end: points.length > 16 ? 1600 / points.length : 100,
      },
      {
        type: "slider",
        bottom: 35,
        height: 20,
        start: 0,
        end: points.length > 16 ? 1600 / points.length : 100,
      },
    ],
    series: series.map(({ label: _label, ...entry }) => entry),
  };
  return {
    options,
    description,
    summary: `${points.length} ${result.group_by === "run" ? "selected-run scopes" : "read files"} · ${result.metric.unit}`,
    series: series.map(({ name, label }) => ({ name, label })),
  };
}
