import type { Entry, Listing } from "./types";

export type ExplorerMode = "samples" | "files";
export interface ExplorerRow {
  id: string;
  name: string;
  files: Entry[];
  sample: boolean;
  pairing: string;
  description: string;
}

export const isInput = (entry: Entry) =>
  entry.kind === "fastq" || entry.kind === "fastqc";

/** Group only the pairing keys supplied by FastAPI; never guess new mates. */
export function explorerRows(
  entries: Entry[],
  mode: ExplorerMode,
): ExplorerRow[] {
  const rows: ExplorerRow[] = [];
  const groups = new Map<string, ExplorerRow>();
  for (const entry of entries) {
    const sample = mode === "samples" && entry.kind === "fastq";
    const id =
      sample && entry.pair_key ? `sample:${entry.pair_key}` : entry.path;
    const existing = groups.get(id);
    if (existing) {
      existing.files.push(entry);
      continue;
    }
    const row: ExplorerRow = {
      id,
      files: [entry],
      sample,
      name: sample
        ? entry.pair_key?.split("/").pop() ||
          entry.name.replace(/\.(fastq|fq)(\.gz)?$/i, "")
        : entry.name,
      pairing: "",
      description: "",
    };
    rows.push(row);
    groups.set(id, row);
  }
  for (const row of rows) {
    const fastqs = row.files.filter((entry) => entry.kind === "fastq");
    if (!fastqs.length) continue;
    if (fastqs.every((entry) => entry.paired && entry.mate)) {
      row.pairing = "Paired-end";
      row.description =
        row.sample && fastqs.length === 1
          ? "Mate detected on another file page"
          : "R1 + R2 detected";
    } else if (fastqs.some((entry) => entry.read)) {
      const reads = fastqs.map((entry) => entry.read);
      const ambiguous =
        new Set(reads).size < reads.length ||
        (reads.includes("R1") && reads.includes("R2"));
      row.pairing = ambiguous ? "Ambiguous naming" : "Incomplete pair";
      row.description = ambiguous
        ? "Review individual files before running"
        : `${reads[0]} present · ${reads[0] === "R1" ? "R2" : "R1"} missing`;
    } else {
      row.pairing = "Single / unassigned";
      row.description = "Single-end read or unrecognized naming convention";
    }
  }
  return rows;
}

export function matchesRow(row: ExplorerRow, search: string) {
  const query = search.trim().toLocaleLowerCase();
  return (
    row.name.toLocaleLowerCase().includes(query) ||
    row.files.some((entry) => entry.name.toLocaleLowerCase().includes(query))
  );
}

/** Sample selection includes confirmed mates even when a directory page splits them. */
export function rowInputPaths(row: ExplorerRow): string[] {
  return [
    ...new Set(
      row.files
        .filter(isInput)
        .flatMap((entry) =>
          row.sample && entry.paired && entry.mate
            ? [entry.path, entry.mate]
            : [entry.path],
        ),
    ),
  ];
}

export function selectionState(
  paths: string[],
  selected: ReadonlyMap<string, Entry>,
) {
  const count = paths.filter((path) => selected.has(path)).length;
  return {
    all: paths.length > 0 && count === paths.length,
    some: count > 0 && count < paths.length,
  };
}

/** Resolve actual file metadata through the existing, paginated directory API. */
export async function resolveEntries(
  paths: string[],
  known: Entry[],
  list: (
    directory: string,
    offset: number,
    snapshot?: string,
  ) => Promise<Listing>,
): Promise<Entry[]> {
  const requested = [...new Set(paths)];
  const found = new Map(known.map((entry) => [entry.path, entry]));
  const missing = requested.filter((path) => !found.has(path));
  const directories = new Set(
    missing.map((path) => path.slice(0, path.lastIndexOf("/")) || "/"),
  );
  for (const directory of directories) {
    const needed = missing.filter(
      (path) => (path.slice(0, path.lastIndexOf("/")) || "/") === directory,
    );
    let offset = 0;
    let snapshot: string | undefined;
    while (needed.some((path) => !found.has(path))) {
      const page = await list(directory, offset, snapshot);
      if (snapshot && snapshot !== page.snapshot)
        throw new Error(
          "Directory listing changed. Refresh and retry the selection.",
        );
      snapshot = page.snapshot;
      for (const entry of page.entries) found.set(entry.path, entry);
      if (page.next_offset === null) break;
      const next = page.next_offset ?? offset + page.entries.length;
      if (next <= offset || next >= page.total) break;
      offset = next;
    }
  }
  return requested.map((path) => {
    const entry = found.get(path);
    if (!entry || !isInput(entry))
      throw new Error(
        "An input file is no longer available. Refresh the directory and check the selection.",
      );
    return entry;
  });
}

export function listingUrl(
  directory: string,
  offset = 0,
  snapshot?: string,
  refresh = false,
) {
  const query = new URLSearchParams({
    path: directory,
    offset: String(offset),
  });
  if (snapshot) query.set("snapshot", snapshot);
  if (refresh) query.set("refresh", "true");
  return `api/files?${query}`;
}
