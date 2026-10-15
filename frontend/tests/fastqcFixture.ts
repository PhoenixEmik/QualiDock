import { readFileSync } from "node:fs";
import type { Module, Sample } from "../src/types.ts";

// Independent reader of the committed, genuine FastQC 0.13.0 text fixtures.
export function fixture(read: "R1" | "R2"): Sample {
  const folder = new URL(
    `../../backend/tests/fixtures/fastqc-0.13.0/coverage_${read}_fastqc/`,
    import.meta.url,
  );
  const raw = readFileSync(new URL("fastqc_data.txt", folder), "utf8");
  const summary = new Map(
    readFileSync(new URL("summary.txt", folder), "utf8")
      .trim()
      .split("\n")
      .map((line) => {
        const [status, name] = line.split("\t");
        return [name, status.toLowerCase()];
      }),
  );
  const modules: Module[] = raw
    .split(">>")
    .filter(
      (block) => !block.startsWith("END_MODULE") && !block.startsWith("##"),
    )
    .map((block) => {
      const lines = block.trim().split("\n");
      const [name, status] = lines.shift()!.split("\t");
      return {
        name,
        status,
        summary_status: summary.get(name),
        available: true,
        columns: lines
          .find(
            (line) =>
              line.startsWith("#") && !line.startsWith("#Total Deduplicated"),
          )!
          .slice(1)
          .split("\t"),
        rows: lines
          .filter((line) => !line.startsWith("#"))
          .map((line) => line.split("\t")),
        metadata: lines
          .filter((line) => line.startsWith("#Total Deduplicated"))
          .map((line) => line.slice(1).split("\t")),
      };
    });
  const stats = Object.fromEntries(
    modules.find((module) => module.name === "Basic Statistics")!.rows,
  );
  const quality = modules.find(
    (module) => module.name === "Per base sequence quality",
  )!;
  return {
    id: `fastqc/coverage_${read}_fastqc.zip`,
    name: stats.Filename,
    fastqc_version: "0.13.0",
    total_sequences: Number(stats["Total Sequences"]),
    gc_percent: Number(stats["%GC"]),
    sequence_length: stats["Sequence length"],
    encoding: stats.Encoding,
    status: modules.some((module) => module.status === "fail")
      ? "fail"
      : modules.some((module) => module.status === "warn")
        ? "warn"
        : "pass",
    modules,
    per_base_quality: quality.rows.map((row) => ({
      base: row[0],
      mean: Number(row[1]),
      median: Number(row[2]),
      lower_quartile: Number(row[3]),
      upper_quartile: Number(row[4]),
      percentile_10: Number(row[5]),
      percentile_90: Number(row[6]),
    })),
  };
}
