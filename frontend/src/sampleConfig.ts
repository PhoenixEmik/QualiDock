import type { SampleConfiguration, InputPairing } from "./types";
/** Editing metadata never edits a FASTQ or implies biological verification. */
export function assignPair(
  config: SampleConfiguration,
  key: string,
  r1: string,
  r2: string,
  lane: string | null,
  chunk: string | null,
): SampleConfiguration {
  if (!r1 || !r2 || r1 === r2)
    throw new Error("Choose two different FASTQ files.");
  for (const path of [r1, r2])
    if (!config.input_pairing.some((record) => record.path === path))
      throw new Error("Pair references an unselected file.");
  if (
    config.input_pairing.some(
      (record) =>
        record.paired &&
        record.pair_key !== key &&
        [r1, r2].includes(record.path),
    )
  )
    throw new Error(
      "A file already belongs to another pair. Remove that pair first.",
    );
  const input_pairing = config.input_pairing.map((record) => {
    if ([r1, r2].includes(record.path))
      return {
        ...record,
        read: record.path === r1 ? "R1" : "R2",
        mate: record.path === r1 ? r2 : r1,
        pair_key: key,
        paired: true,
        source: "manual" as const,
        assignment: "paired" as const,
        lane,
        chunk,
      };
    return record.pair_key === key
      ? {
          ...record,
          read: null,
          mate: null,
          pair_key: null,
          paired: false,
          source: "manual" as const,
          assignment: "unpaired" as const,
        }
      : record;
  });
  const group = config.sample_groups.find((group) => group.files.includes(r1))!;
  const sample_groups = config.sample_groups
    .map((g) =>
      g.id === group.id
        ? {
            ...g,
            source: "manual" as const,
            files: [...new Set([...g.files, r2])],
          }
        : g.files.includes(r2)
          ? {
              ...g,
              source: "manual" as const,
              files: g.files.filter((path) => path !== r2),
            }
          : g,
    )
    .filter((g) => g.files.length);
  return { ...config, input_pairing, sample_groups };
}
export function removePair(
  config: SampleConfiguration,
  key: string,
): SampleConfiguration {
  return {
    ...config,
    input_pairing: config.input_pairing.map((record) =>
      record.pair_key === key
        ? {
            ...record,
            paired: false,
            pair_key: null,
            mate: null,
            read: null,
            source: "manual" as const,
            assignment: "unpaired" as const,
          }
        : record,
    ),
  };
}
export function pairRecords(records: InputPairing[]) {
  const keys = [
    ...new Set(
      records.filter((r) => r.paired && r.pair_key).map((r) => r.pair_key!),
    ),
  ];
  return keys.map((key) => ({
    key,
    r1: records.find((r) => r.pair_key === key && r.read === "R1"),
    r2: records.find((r) => r.pair_key === key && r.read === "R2"),
  }));
}
export function moveToGroup(
  config: SampleConfiguration,
  path: string,
  groupId: string,
) {
  const record = config.input_pairing.find((r) => r.path === path);
  const moved = [path, ...(record?.paired && record.mate ? [record.mate] : [])];
  return {
    ...config,
    sample_groups: config.sample_groups
      .map((group) => ({
        ...group,
        source:
          group.id === groupId ||
          group.files.some((file) => moved.includes(file))
            ? ("manual" as const)
            : group.source,
        files:
          group.id === groupId
            ? [...new Set([...group.files, ...moved])]
            : group.files.filter((file) => !moved.includes(file)),
      }))
      .filter((group) => group.files.length),
  };
}
export function reconcileConfig(
  config: SampleConfiguration,
  paths: string[],
): SampleConfiguration {
  const allowed = new Set(paths);
  return {
    ...config,
    input_pairing: config.input_pairing
      .filter((record) => allowed.has(record.path))
      .map((record) =>
        record.paired && !allowed.has(record.mate || "")
          ? {
              ...record,
              paired: false,
              pair_key: null,
              mate: null,
              source: "manual" as const,
              assignment: "unpaired" as const,
            }
          : record,
      ),
    sample_groups: config.sample_groups
      .map((group) => ({
        ...group,
        files: group.files.filter((path) => allowed.has(path)),
      }))
      .filter((group) => group.files.length),
  };
}
