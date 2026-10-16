import type { Run, Sample, InputPairing } from "./types";
import { sampleSource } from "./sampleIdentity.ts";

export interface SamplePair {
  id: string;
  name: string;
  r1: Sample;
  r2: Sample;
  inputs: [InputPairing, InputPairing];
}

/** Only mutual, unique relationships persisted by the server are evidence of pairing.
 * Lane/chunk/directory keys are preserved; filenames alone never establish a pair.
 */
export function confirmedPairs(run: Run, samples: Sample[]): SamplePair[] {
  const byPath = new Map<string, Sample[]>();
  for (const sample of samples) {
    const path = sampleSource(run, sample);
    if (path) byPath.set(path, [...(byPath.get(path) || []), sample]);
  }
  const groups = new Map<string, InputPairing[]>();
  const records = [...(run.input_pairing || [])];
  const derivedPaths = new Set<string>();
  if (run.output_directory)
    for (const unit of run.processing?.units || []) {
      const outputs = (run.derived_datasets || []).filter(
        (row) => row.unit_id === unit.id && row.paired,
      );
      if (
        outputs.length !== 2 ||
        !outputs.some((row) => row.read === "R1") ||
        !outputs.some((row) => row.read === "R2")
      )
        continue;
      for (const row of outputs) {
        const path = `${run.output_directory}/${row.path}`;
        derivedPaths.add(path);
        records.push({
          path,
          name: row.path.split("/").pop()!,
          read: row.read,
          pair_key: `processed:${unit.id}`,
          paired: true,
          mate: `${run.output_directory}/${outputs.find((other) => other.id !== row.id)!.path}`,
          lane: unit.lane,
          chunk: unit.chunk,
          source: "auto",
        });
      }
    }
  for (const input of records) {
    if (
      input.paired &&
      input.pair_key &&
      input.mate &&
      ((run.sample_input_paths || run.inputs).includes(input.path) ||
        derivedPaths.has(input.path)) &&
      input.name === input.path.split("/").pop()
    )
      groups.set(input.pair_key, [
        ...(groups.get(input.pair_key) || []),
        input,
      ]);
  }
  const result: SamplePair[] = [];
  for (const [id, records] of groups) {
    if (records.length !== 2) continue;
    const r1 = records.find((record) => record.read === "R1");
    const r2 = records.find((record) => record.read === "R2");
    if (
      !r1 ||
      !r2 ||
      r1.path === r2.path ||
      r1.mate !== r2.path ||
      r2.mate !== r1.path
    )
      continue;
    const left = byPath.get(r1.path),
      right = byPath.get(r2.path);
    if (left?.length !== 1 || right?.length !== 1 || left[0].id === right[0].id)
      continue;
    result.push({
      id,
      name: [
        run.sample_groups?.find((group) => group.files.includes(r1.path))
          ?.display_name ||
          id.split("/").pop() ||
          id,
        r1.lane,
        r1.chunk && `Chunk ${r1.chunk}`,
        r1.source === "manual" ? "manual" : null,
      ]
        .filter(Boolean)
        .join(" · "),
      r1: left[0],
      r2: right[0],
      inputs: [r1, r2],
    });
  }
  return result;
}
