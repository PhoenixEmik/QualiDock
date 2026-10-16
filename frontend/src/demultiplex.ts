export interface EvidenceTable {
  columns: string[];
  rows: Record<string, string>[];
  schema: string;
}
export interface DemultiplexEvidence {
  state: string;
  message?: string;
  source_tool?: string;
  run_id?: string | null;
  declared_run_id?: string | null;
  reported_tool_version?: string | null;
  declared_tool_version?: string | null;
  version_source?: string;
  reconciliation_state?: string;
  documents?: {
    name: string;
    sha256: string;
    bytes: number;
    artifact: string;
  }[];
  sample_sheet?:
    (EvidenceTable & { settings: Record<string, string[][]> }) | null;
  demultiplex?: EvidenceTable | null;
  quality?: EvidenceTable | null;
  index_hopping?: EvidenceTable | null;
  fastq_list?: EvidenceTable | null;
  discrepancies?: { code: string; message: string }[];
  lane_totals?: {
    lane: string;
    reported_pf_reads: number;
    undetermined_pf_reads: number | null;
    undetermined_percent_of_imported_rows: number | null;
    denominator: string;
  }[];
  file_mappings?: {
    sample_id_reported: string;
    lane: string;
    read: string;
    reported_filename: string;
    file_id: string | null;
    state: string;
    note: string;
  }[];
}
export async function evidenceDocuments(files: File[]) {
  const allowed = new Set([
    "SampleSheet.csv",
    "Demultiplex_Stats.csv",
    "Quality_Metrics.csv",
    "Index_Hopping_Counts.csv",
    "fastq_list.csv",
  ]);
  if (
    !files.length ||
    files.length > 5 ||
    new Set(files.map((file) => file.name)).size !== files.length ||
    files.some(
      (file) => !allowed.has(file.name) || file.size > 2 * 1024 * 1024,
    ) ||
    files.reduce((sum, file) => sum + file.size, 0) > 4 * 1024 * 1024
  )
    throw new Error(
      "Choose supported Illumina CSV filenames, at most 2 MiB/file and 4 MiB total, without duplicate filenames.",
    );
  return Promise.all(
    files.map(async (file) => {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 16384)
        binary += String.fromCharCode(
          ...bytes.subarray(offset, offset + 16384),
        );
      return { name: file.name, content_base64: btoa(binary) };
    }),
  );
}
