import type { Run, Sample } from "./types";
import { inputFilename } from "./qc.ts";

/** A persisted exact report mapping takes precedence over historical unique names. */
export function sampleSource(run: Run, sample: Sample): string | undefined {
  const paths = run.sample_input_paths || run.inputs;
  const mapped = run.report_input_map?.[sample.id]?.path;
  if (mapped && paths.includes(mapped)) return mapped;
  const matches = paths.filter(
    (path) => path.split("/").pop() === inputFilename(sample),
  );
  return matches.length === 1 ? matches[0] : undefined;
}

export function sampleLabel(run: Run, sample: Sample, samples: Sample[]) {
  if (
    samples.filter((other) => inputFilename(other) === inputFilename(sample))
      .length < 2
  )
    return sample.name;
  const source = sampleSource(run, sample);
  const identity = run.report_input_map?.[sample.id]?.id || sample.id;
  return `${sample.name} · ${source?.split("/").slice(-2, -1)[0] || "report"} · ${identity.slice(-8)}`;
}
