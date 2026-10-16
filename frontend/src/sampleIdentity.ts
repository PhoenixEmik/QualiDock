import type { Run, Sample } from "./types";
import { inputFilename } from "./qc.ts";

/** A persisted exact report mapping takes precedence over historical unique names. */
export function sampleSource(run: Run, sample: Sample): string | undefined {
  const paths = run.sample_input_paths || run.inputs;
  const mapped = run.report_input_map?.[sample.id]?.path;
  const derived = run.output_directory
    ? (run.derived_datasets || []).map(
        (row) => `${run.output_directory}/${row.path}`,
      )
    : [];
  if (mapped && [...paths, ...derived].includes(mapped)) return mapped;
  const matches = paths.filter(
    (path) => path.split("/").pop() === inputFilename(sample),
  );
  return matches.length === 1 ? matches[0] : undefined;
}

export function sampleLabel(run: Run, sample: Sample, samples: Sample[]) {
  const stage = run.report_input_map?.[sample.id]?.processing_stage;
  if (stage) {
    const source = sampleSource(run, sample);
    const derived = run.derived_datasets?.find(
      (row) => `${run.output_directory}/${row.path}` === source,
    );
    const read =
      derived?.read ||
      run.input_pairing?.find((record) => record.path === source)?.read;
    return `${stage === "raw" ? "Raw" : "Processed"} · ${derived?.source.split("/").pop() || sample.name}${read ? ` · ${read}` : ""} · ${sample.id.split("/").slice(1, 2).join("")}`;
  }
  if (
    samples.filter((other) => inputFilename(other) === inputFilename(sample))
      .length < 2
  )
    return sample.name;
  const source = sampleSource(run, sample);
  const identity = run.report_input_map?.[sample.id]?.id || sample.id;
  return `${sample.name} · ${source?.split("/").slice(-2, -1)[0] || "report"} · ${identity.slice(-8)}`;
}
