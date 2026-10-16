import type { Run, ProcessingOptions, DatasetReference } from "./types.ts";
export const isProcessing = (mode: string) =>
  mode === "fastp" || mode.startsWith("seqkit-");
export const processingModes = [
  "fastp",
  "seqkit-stats",
  "seqkit-sample",
  "seqkit-filter",
  "seqkit-extract",
] as const;
export function defaults(mode: string): ProcessingOptions {
  return mode === "fastp"
    ? {
        adapter_trimming: true,
        quality_filtering: true,
        qualified_quality: 15,
        unqualified_percent: 40,
        min_length: 15,
        gzip: true,
        compare_qc: true,
        multiqc: false,
      }
    : {
        gzip: true,
        fraction: 0.1,
        seed: 11,
        min_length: 15,
        max_length: null,
        identifiers: [],
      };
}
export function retention(
  before: number | undefined,
  after: number | undefined,
) {
  if (
    before === undefined ||
    after === undefined ||
    !Number.isFinite(before) ||
    !Number.isFinite(after) ||
    before <= 0 ||
    after < 0 ||
    after > before
  )
    return null;
  return {
    retained: (after / before) * 100,
    removed: ((before - after) / before) * 100,
  };
}
export const downloadDataset = (run: Pick<Run, "id">, path: string) =>
  `api/runs/${run.id}/download?path=${encodeURIComponent(path)}`;

/** Match the backend artifact publication boundary; metadata can arrive mid-run. */
export const publishedDatasets = (
  run: Pick<Run, "state" | "derived_datasets">,
) =>
  ["completed", "partial"].includes(run.state)
    ? run.derived_datasets || []
    : [];

export const selectedReferences = (
  references: DatasetReference[],
  paths: Set<string>,
) =>
  references
    .filter((ref) => !!ref.path && paths.has(ref.path))
    .map(({ run_id, dataset_id }) => ({ run_id, dataset_id }));
