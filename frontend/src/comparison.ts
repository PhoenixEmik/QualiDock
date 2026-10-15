import type { Module, Sample } from "./types";
import { findModule, moduleKey, numeric, rowTooltip } from "./qc.ts";

const comparable = new Set([
  "perbasesequencequality",
  "persequencequalityscores",
  "perbasesequencecontent",
  "persequencegccontent",
  "perbasencontent",
  "adaptercontent",
  "sequencelengthdistribution",
  "sequenceduplicationlevels",
]);
const positional = new Set([
  "perbasesequencequality",
  "perbasesequencecontent",
  "perbasencontent",
  "adaptercontent",
  "sequencelengthdistribution",
  "persequencegccontent",
  "persequencequalityscores",
]);

export interface ComparedSeries {
  name: string;
  read: "R1" | "R2";
  column: string;
  data: (number | null)[];
}
export interface Comparison {
  mode: "overlay" | "separate";
  reason: string;
  categories: string[];
  series: ComparedSeries[];
  rows: [Map<string, number>, Map<string, number>];
  modules: [Module | undefined, Module | undefined];
}

/** Exact interval compatibility, without expanding a single reported bin. */
export function alignBins(
  left: string[],
  right: string[],
  intervals: boolean,
): string[] | null {
  if (
    new Set(left).size !== left.length ||
    new Set(right).size !== right.length
  )
    return null;
  if (
    left.length === right.length &&
    left.every((value, i) => value === right[i])
  )
    return [...left];
  if (!intervals) return null;
  const labels = [...new Set([...left, ...right])];
  const bins = labels.map((label) => {
    const match = /^(\d+)(?:-(\d+))?$/.exec(label);
    if (!match) return null;
    const start = Number(match[1]),
      end = Number(match[2] ?? match[1]);
    return Number.isSafeInteger(start) &&
      Number.isSafeInteger(end) &&
      end >= start
      ? { label, start, end }
      : null;
  });
  if (bins.some((bin) => bin === null)) return null;
  const ordered = bins
    .filter((bin) => bin !== null)
    .sort((a, b) => a.start - b.start || a.end - b.end);
  if (ordered.some((bin, i) => i > 0 && bin.start <= ordered[i - 1].end))
    return null;
  return ordered.map((bin) => bin.label);
}

export function compareModules(
  r1: Sample,
  r2: Sample,
  metric: string,
  median = false,
): Comparison {
  const modules: Comparison["modules"] = [
    findModule(r1, metric),
    findModule(r2, metric),
  ];
  const rows: Comparison["rows"] = modules.map(
    (module) => new Map(module?.rows.map((row, i) => [row[0], i]) || []),
  ) as Comparison["rows"];
  const separate = (reason: string): Comparison => ({
    mode: "separate",
    reason,
    categories: [],
    series: [],
    rows,
    modules,
  });
  if (
    modules.some(
      (module) => !module || module.available === false || !module.rows.length,
    )
  )
    return separate(
      "One or both reads have no reported values for this module. Available results are shown individually.",
    );
  const [left, right] = modules as [Module, Module];
  const key = moduleKey(metric);
  if (!comparable.has(key))
    return separate(
      key === "pertilesequencequality"
        ? "Tile identifiers do not establish equivalent physical tiles between reads. Inspect each read on its own axes."
        : "This module has no shared quantitative comparison here. Inspect the original results for each read below.",
    );
  if (
    key === "perbasesequencequality" &&
    (!r1.encoding || !r2.encoding || r1.encoding !== r2.encoding)
  )
    return separate(
      "Quality encodings differ. Each read is shown separately without assuming equivalent score scales.",
    );
  if (left.columns[0] !== right.columns[0])
    return separate(
      "The reported axis definitions differ. Each read retains its original axes.",
    );
  if (
    new Set(left.columns).size !== left.columns.length ||
    new Set(right.columns).size !== right.columns.length
  )
    return separate(
      "Repeated column names cannot be aligned unambiguously. Inspect each read separately.",
    );
  const categories = alignBins(
    left.rows.map((row) => row[0]),
    right.rows.map((row) => row[0]),
    positional.has(key),
  );
  if (!categories)
    return separate(
      "Position bins or categories differ or overlap with different boundaries. Each read retains its original bins; no values are interpolated.",
    );
  const columns =
    key === "perbasesequencequality"
      ? ["Mean", ...(median ? ["Median"] : [])]
      : left.columns
          .slice(1)
          .filter((column) => right.columns.slice(1).includes(column));
  if (
    !columns.length ||
    columns.some(
      (column) =>
        !left.columns.includes(column) || !right.columns.includes(column),
    )
  )
    return separate(
      "The reported metric columns are incompatible. Each read is shown with its own original columns.",
    );
  const unmatched = [
    ...new Set([...left.columns.slice(1), ...right.columns.slice(1)]),
  ].filter((column) => !columns.includes(column));
  const sameBins =
    left.rows.length === right.rows.length &&
    left.rows.every((row, i) => row[0] === right.rows[i][0]);
  const notes = [
    "Only exact reported bins are aligned. Missing values remain gaps.",
  ];
  if (!sameBins)
    notes.push(
      "Read lengths or bin sets differ; unmatched bins have data only for the read that reported them.",
    );
  if (unmatched.length && key !== "perbasesequencequality")
    notes.push(
      `Shared columns only. Other columns (${unmatched.join(", ")}) remain in Raw Data.`,
    );
  if (
    [
      "persequencegccontent",
      "persequencequalityscores",
      "sequencelengthdistribution",
    ].includes(key)
  )
    notes.push(
      "Counts are unscaled; different read totals are not normalized.",
    );
  const series: ComparedSeries[] = [];
  modules.forEach((module, readIndex) => {
    for (const column of columns) {
      const read = readIndex === 0 ? "R1" : "R2";
      const index = module!.columns.indexOf(column);
      series.push({
        name: `${read} · ${column}`,
        read,
        column,
        data: categories.map((label) => {
          const row = rows[readIndex].get(label);
          return row === undefined ? null : numeric(module!.rows[row][index]);
        }),
      });
    }
  });
  return {
    mode: "overlay",
    reason: notes.join(" "),
    categories,
    series,
    rows,
    modules,
  };
}

export function comparisonTooltip(
  comparison: Comparison,
  index: number,
  names: [string, string],
) {
  const label = comparison.categories[index];
  return comparison.modules
    .map((module, readIndex) => {
      const row = comparison.rows[readIndex].get(label);
      return `${readIndex === 0 ? "R1" : "R2"} · ${names[readIndex]}\n${module && row !== undefined ? rowTooltip(module, row) : `${label}: Unavailable (not reported)`}`;
    })
    .join("\n\n");
}
