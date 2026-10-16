import type { Run, Sample, MultiQCSummary, Module } from "./types";
import {
  inputFilename,
  moduleNames,
  moduleStatus,
  findModule,
  moduleKey,
  numeric,
} from "./qc.ts";
import { confirmedPairs } from "./pairing.ts";
import { alignBins } from "./comparison.ts";
import { exportModule } from "./rawExport.ts";

export interface AnalyticsSample {
  id: string;
  name: string;
  source: string;
  analysisId: string;
  tool: "FastQC" | "MultiQC";
  version: string | null;
  fastqc?: Sample;
  multiqcName?: string;
  read?: "R1" | "R2";
  pair?: string;
  groupId?: string;
  groupName?: string;
  lane?: string | null;
  chunk?: string | null;
}
/** Match only unique, exact FastQC input/report stems. Never merge lanes or infer pairs. */
export function analyticsSamples(
  run: Run,
  samples: Sample[],
  multiqc?: MultiQCSummary,
): AnalyticsSample[] {
  const pairs = confirmedPairs(run, samples);
  const entities: AnalyticsSample[] = samples.map((sample) => {
    const filename = inputFilename(sample);
    const inputs = (run.sample_input_paths || run.inputs).filter(
      (path) => path.split("/").pop() === filename,
    );
    const pair = pairs.find(
      (pair) => pair.r1.id === sample.id || pair.r2.id === sample.id,
    );
    const source = inputs.length === 1 ? inputs[0] : sample.id;
    const group =
      inputs.length === 1
        ? run.sample_groups?.find((group) => group.files.includes(inputs[0]))
        : undefined;
    const record =
      inputs.length === 1
        ? run.input_pairing?.find((record) => record.path === inputs[0])
        : undefined;
    return {
      id: sample.id,
      name: filename,
      source,
      groupId: group?.id,
      groupName: group?.display_name,
      lane: record?.lane,
      chunk: record?.chunk,
      analysisId: run.id,
      tool: "FastQC",
      version: sample.fastqc_version || null,
      fastqc: sample,
      read: pair ? (pair.r1.id === sample.id ? "R1" : "R2") : undefined,
      pair: pair?.id,
    };
  });
  for (const row of multiqc?.rows || []) {
    const matches = entities.filter(
      (entity) =>
        entity.fastqc &&
        [
          entity.name,
          entity.name.replace(/\.(fastq|fq)(\.gz|\.bz2)?$/i, ""),
        ].includes(row.sample),
    );
    if (matches.length === 1 && !matches[0].multiqcName)
      matches[0].multiqcName = row.sample;
    else
      entities.push({
        id: `multiqc:${row.sample}`,
        name: row.sample,
        multiqcName: row.sample,
        source: "MultiQC General Statistics; unique FASTQ mapping unavailable",
        analysisId: run.id,
        tool: "MultiQC",
        version: multiqc?.version || run.tools?.multiqc?.version || null,
      });
  }
  return entities;
}
/** Overview counts are independent of filtering/selection and never use the
 * derived overall Sample.status as evidence of a failed FastQC module.
 */
export function overviewCounts(run: Run, samples: Sample[]) {
  return {
    readFiles: samples.length,
    readPairs: run.input_pairing?.length
      ? confirmedPairs(run, samples).length
      : null,
    withFailures: samples.some((sample) => sample.modules.length > 0)
      ? samples.filter((sample) =>
          sample.modules.some((module) => module.status === "fail"),
        ).length
      : null,
  };
}
export type StatColumn = MultiQCSummary["columns"][number];
export function rawUnit(column: StatColumn) {
  if (column.raw_unit !== undefined) return column.raw_unit;
  // Historical summaries stored the display suffix. Apply only verified raw units.
  if (column.namespace.toLowerCase() !== "fastqc") return "";
  return (
    (
      {
        total_sequences: "reads",
        percent_duplicates: "%",
        percent_gc: "%",
        percent_fails: "%",
        avg_sequence_length: "bp",
        median_sequence_length: "bp",
      } as Record<string, string>
    )[column.raw_key] || ""
  );
}
export type Sort = { key: string; direction: 1 | -1 };
export function sortStats(
  rows: MultiQCSummary["rows"],
  search: string,
  sorts: Sort[],
) {
  return rows
    .filter((row) => row.sample.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      for (const sort of sorts) {
        const x = sort.key === "sample" ? a.sample : a.values[sort.key],
          y = sort.key === "sample" ? b.sample : b.values[sort.key];
        // Missing values always last, including descending order. Zero is a value.
        if (x === undefined || y === undefined) {
          if (x !== y) return x === undefined ? 1 : -1;
          continue;
        }
        const delta =
          typeof x === "number" && typeof y === "number"
            ? x - y
            : String(x).localeCompare(String(y), undefined, { numeric: true });
        if (delta) return delta * sort.direction;
      }
      return a.sample.localeCompare(b.sample);
    });
}
export function statsExport(
  rows: MultiQCSummary["rows"],
  columns: StatColumn[],
  delimiter: "," | "\t",
) {
  return exportModule(
    {
      name: "General Statistics",
      status: "",
      columns: [
        "Sample",
        ...columns.map(
          (c) =>
            `${c.namespace ? c.namespace + " · " : ""}${c.title} [${c.raw_key}]${rawUnit(c) ? " (" + rawUnit(c) + ")" : ""}`,
        ),
      ],
      rows: rows.map((row) => [
        row.sample,
        ...columns.map((c) =>
          row.values[c.key] === undefined ? "" : String(row.values[c.key]),
        ),
      ]),
    },
    delimiter,
  );
}
export const statusValues = ["pass", "warn", "fail", "unavailable"] as const;
export type QcStatus = (typeof statusValues)[number];
export function statusMatrix(samples: AnalyticsSample[]) {
  const names = new Map<string, string>();
  for (const entity of samples)
    if (entity.fastqc)
      for (const name of moduleNames(entity.fastqc))
        if (!names.has(moduleKey(name))) names.set(moduleKey(name), name);
  const modules = [...names.values()];
  return {
    modules,
    rows: samples
      .filter((s) => s.fastqc)
      .map((entity) => {
        const statuses = modules.map((name) => {
          const status = moduleStatus(entity.fastqc!, name);
          return statusValues.includes(status as QcStatus)
            ? (status as QcStatus)
            : "unavailable";
        });
        return {
          entity,
          statuses,
          failures: statuses.filter((s) => s === "fail").length,
          warnings: statuses.filter((s) => s === "warn").length,
        };
      }),
  };
}
export const comparisonMetrics = [
  "Per base sequence quality",
  "Per sequence quality scores",
  "Per sequence GC content",
  "Sequence Duplication Levels",
  "Adapter Content",
  "Sequence Length Distribution",
];
export interface OverlaySeries {
  name: string;
  entity: AnalyticsSample;
  column: string;
  values: (number | null)[];
  raw: (string | undefined)[];
}
export interface Overlay {
  categories: string[];
  series: OverlaySeries[];
  members: AnalyticsSample[];
  unit: string;
}
export interface ComparisonData {
  groups: Overlay[];
  notes: string[];
  unavailable: string[];
}
function comparisonColumns(module: Module, key: string): string[] {
  if (key === "perbasesequencequality")
    return module.columns.includes("Mean") ? ["Mean"] : [];
  if (
    [
      "persequencequalityscores",
      "persequencegccontent",
      "sequencelengthdistribution",
    ].includes(key)
  )
    return module.columns.includes("Count") ? ["Count"] : [];
  if (key === "sequenceduplicationlevels")
    return module.columns
      .slice(1)
      .filter((column) => /^Percentage of (deduplicated|total)$/.test(column));
  return module.columns.slice(1); // Adapter names are reported categories, never inferred.
}
export function multiComparison(
  entities: AnalyticsSample[],
  metric: string,
  normalized = false,
): ComparisonData {
  const key = moduleKey(metric),
    quality = key === "perbasesequencequality";
  if (!comparisonMetrics.some((m) => moduleKey(m) === key))
    return {
      groups: [],
      notes: [
        "This module has no supported multi-sample adapter. Inspect Sample Details or the official report.",
      ],
      unavailable: [],
    };
  const groups: {
    members: AnalyticsSample[];
    modules: Module[];
    categories: string[];
  }[] = [];
  const unavailable: string[] = [],
    notes: string[] = [];
  for (const entity of entities) {
    const module = entity.fastqc && findModule(entity.fastqc, metric);
    if (!module || module.available === false || !module.rows.length) {
      unavailable.push(entity.name);
      continue;
    }
    const labels = module.rows.map((row) => row[0]);
    if (
      new Set(labels).size !== labels.length ||
      new Set(module.columns).size !== module.columns.length
    ) {
      unavailable.push(`${entity.name} (ambiguous repeated axis/columns)`);
      continue;
    }
    if (!comparisonColumns(module, key).length) {
      unavailable.push(`${entity.name} (supported metric columns unavailable)`);
      continue;
    }
    const numericColumns = comparisonColumns(module, key).map((column) =>
      module.columns.indexOf(column),
    );
    if (
      !module.rows.some((row) =>
        numericColumns.some((column) => numeric(row[column]) !== null),
      )
    ) {
      unavailable.push(`${entity.name} (no numeric values reported)`);
      continue;
    }
    if (normalized) {
      const count = module.columns.indexOf("Count");
      const denominator = entity.fastqc?.total_sequences;
      const values = module.rows.map((row) => numeric(row[count]));
      if (
        key !== "persequencequalityscores" ||
        !denominator ||
        !Number.isSafeInteger(denominator) ||
        denominator <= 0 ||
        values.some((v) => v === null || !Number.isSafeInteger(v) || v < 0) ||
        values.reduce<number>((s, v) => s + (v || 0), 0) !== denominator
      ) {
        unavailable.push(
          `${entity.name} (normalization requires complete counts summing to reported Total Sequences)`,
        );
        continue;
      }
    }
    let target: (typeof groups)[number] | undefined;
    for (const group of groups) {
      const compatible =
        group.modules[0].columns[0] === module.columns[0] &&
        (quality
          ? !!entity.fastqc?.encoding &&
            group.members[0].fastqc?.encoding === entity.fastqc.encoding
          : group.modules[0].columns.join("\t") === module.columns.join("\t"));
      const bins = compatible
        ? alignBins(
            group.categories,
            labels,
            key !== "sequenceduplicationlevels",
          )
        : null;
      if (bins) {
        target = group;
        group.categories = bins;
        break;
      }
    }
    if (target) {
      target.members.push(entity);
      target.modules.push(module);
    } else
      groups.push({ members: [entity], modules: [module], categories: labels });
  }
  if (groups.length > 1)
    notes.push(
      "Incompatible bins, encodings, axes or adapter categories are displayed on separate charts. No interpolation or resampling.",
    );
  notes.push(
    normalized
      ? "Percentage = reported Count / reported Total Sequences × 100. Only complete distributions with matching totals qualify; exports retain original counts."
      : "Reported values are unscaled. Different read totals and experimental protocols can affect distributions. Missing or unmatched bins remain gaps.",
  );
  return {
    notes,
    unavailable,
    groups: groups.map((group) => {
      const series: OverlaySeries[] = [];
      group.modules.forEach((module, index) => {
        const entity = group.members[index],
          rows = new Map(module.rows.map((row) => [row[0], row]));
        const columns = comparisonColumns(module, key);
        for (const column of columns) {
          const c = module.columns.indexOf(column),
            raw = group.categories.map((label) => rows.get(label)?.[c]);
          series.push({
            name: `${entity.name} · ${column} · ${entity.id}`,
            entity,
            column,
            raw,
            values: raw.map((v) => {
              const value = numeric(v);
              return value === null
                ? null
                : normalized
                  ? (value / entity.fastqc!.total_sequences!) * 100
                  : value;
            }),
          });
        }
      });
      return {
        categories: group.categories,
        series,
        members: group.members,
        unit: quality
          ? "Mean Phred score"
          : normalized
            ? "Sequences (%)"
            : key === "adaptercontent"
              ? "Adapter content (%)"
              : key === "sequenceduplicationlevels"
                ? "Reported sequences (%)"
                : "Sequence count",
      };
    }),
  };
}
export function sourceExport(
  entities: AnalyticsSample[],
  metric: string,
  delimiter: "," | "\t",
) {
  // Long format retains each report's own original headers, bins, precision and missing cells.
  const rows: string[][] = [];
  for (const entity of entities) {
    const module = entity.fastqc && findModule(entity.fastqc, metric);
    if (!module || module.available === false) continue;
    for (let i = 0; i < module.rows.length; i++)
      for (
        let c = 0;
        c < Math.max(module.columns.length, module.rows[i].length);
        c++
      )
        rows.push([
          entity.analysisId,
          entity.id,
          entity.name,
          entity.source,
          entity.tool,
          entity.version || "",
          module.name,
          String(i + 1),
          module.columns[c] || "Unlabelled field",
          module.rows[i][c] ?? "",
        ]);
  }
  return exportModule(
    {
      name: metric,
      status: "",
      columns: [
        "Analysis",
        "Report identity",
        "FASTQ filename",
        "Input / report source",
        "Tool",
        "Version",
        "Module",
        "Row",
        "Original column",
        "Reported value",
      ],
      rows,
    },
    delimiter,
  );
}
export function toggleSelection(selected: Set<string>, id: string) {
  const next = new Set(selected);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}
