import type { DatasetReference } from "./types.ts";
export interface FastqPreview {
  files: {
    path: string;
    status: string;
    error: string | null;
    records: {
      ordinal: number;
      identifier: string;
      length: number;
      sequence: string;
      quality: string;
    }[];
  }[];
  paired: boolean;
  pairs: { ordinal: number; status: string }[];
}
export function inspectorRequest(
  paths: string[],
  references: DatasetReference[],
  count: number,
  paired: boolean,
) {
  if (
    !paths.length ||
    paths.length > 2 ||
    new Set(paths).size !== paths.length ||
    !Number.isInteger(count) ||
    count < 1 ||
    count > 20 ||
    (paired && paths.length !== 2)
  ) {
    throw new Error("Select one or two FASTQs and 1–20 records.");
  }
  return {
    paths,
    count,
    paired,
    input_datasets: references
      .filter((ref) => ref.path && paths.includes(ref.path))
      .map(({ run_id, dataset_id }) => ({ run_id, dataset_id })),
  };
}
