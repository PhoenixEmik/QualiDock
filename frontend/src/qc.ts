import type { Module, Sample } from "./types";

export const supportedModules = [
  "Basic Statistics",
  "Per base sequence quality",
  "Per sequence quality scores",
  "Per base sequence content",
  "Per sequence GC content",
  "Per base N content",
  "Sequence Length Distribution",
  "Sequence Duplication Levels",
  "Overrepresented sequences",
  "Adapter Content",
  "Per tile sequence quality",
  "Kmer Content",
];
const key = (name: string) => name.toLowerCase().replace(/[\s_-]/g, "");
export const findModule = (sample: Sample, name: string) =>
  sample.modules.find((m) => key(m.name) === key(name));
export const moduleNames = (sample: Sample) => [
  ...supportedModules,
  ...sample.modules
    .map((m) => m.name)
    .filter((name) => !supportedModules.some((m) => key(m) === key(name))),
];
export function numeric(raw: string | undefined): number | null {
  if (raw === undefined || !raw.trim()) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}
export const tableOnly = (module: Module) =>
  ["basicstatistics", "overrepresentedsequences"].includes(key(module.name)) ||
  !supportedModules.some((name) => key(name) === key(module.name));
/** Chart points always refer to reported bins. Never expand bins or calculate statistics. */
export function chartData(module: Module) {
  if (key(module.name) === "pertilesequencequality") {
    const bases = [...new Set(module.rows.map((row) => row[1]))];
    const tiles = [...new Set(module.rows.map((row) => row[0]))];
    return {
      kind: "heatmap" as const,
      categories: bases,
      tiles,
      series: [
        {
          name: module.columns[2],
          data: module.rows.map((row) => [
            bases.indexOf(row[1]),
            tiles.indexOf(row[0]),
            numeric(row[2]),
          ]),
        },
      ],
    };
  }
  const kmer = key(module.name) === "kmercontent";
  const indexes = kmer
    ? [module.columns.findIndex((name) => name === "Obs/Exp Max")].filter(
        (index) => index > 0,
      )
    : module.columns.slice(1).map((_, index) => index + 1);
  const bar =
    kmer ||
    ["persequencequalityscores", "sequencelengthdistribution"].includes(
      key(module.name),
    );
  return {
    kind: bar ? ("bar" as const) : ("line" as const),
    categories: module.rows.map((row) => row[0]),
    tiles: [],
    series: indexes.map((index) => ({
      name: module.columns[index],
      data: module.rows.map((row) => numeric(row[index])),
    })),
  };
}
export function rowTooltip(module: Module, index: number): string {
  const row = module.rows[index];
  return row
    ? module.columns
        .map((column, i) => `${column}: ${row[i] ?? "Unavailable"}`)
        .join("\n")
    : "";
}

export function qualityData(sample: Sample) {
  return {
    boxes: sample.per_base_quality.map((b) => [
      b.percentile_10,
      b.lower_quartile,
      b.median,
      b.upper_quartile,
      b.percentile_90,
    ]),
    means: sample.per_base_quality.map((b) => b.mean),
    categories: sample.per_base_quality.map((b) => b.base),
  };
}
