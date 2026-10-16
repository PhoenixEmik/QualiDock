import type { Run, Sample, InputPairing } from "./types";
import { inputFilename } from "./qc.ts";

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
  const byName = new Map<string, Sample[]>();
  for (const sample of samples) {
    const name = inputFilename(sample);
    byName.set(name, [...(byName.get(name) || []), sample]);
  }
  const groups = new Map<string, InputPairing[]>();
  const records = run.input_pairing || [];
  const names = new Map<string, number>();
  for (const input of records)
    names.set(input.name, (names.get(input.name) || 0) + 1);
  for (const input of records) {
    if (
      input.paired &&
      input.pair_key &&
      input.mate &&
      (run.sample_input_paths || run.inputs).includes(input.path) &&
      input.name === input.path.split("/").pop() &&
      names.get(input.name) === 1
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
    const left = byName.get(r1.name),
      right = byName.get(r2.name);
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
