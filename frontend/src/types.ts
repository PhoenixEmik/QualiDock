import type { ScreeningRecord } from "./screening";
import type { ReleaseExport, ReviewEvent } from "./release";
export type View = "workspace" | "new" | "analyses" | "analysis";
export type DetailTab = "overview" | "metrics" | "reports";
export type RunState =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "partial"
  | "cancelled"
  | "interrupted";
export type RunSummary = Pick<
  Run,
  | "id"
  | "name"
  | "mode"
  | "state"
  | "stage"
  | "created_at"
  | "updated_at"
  | "started_at"
  | "finished_at"
  | "threads"
  | "sample_count"
  | "error"
> & { input_count: number };
export interface HistoryPage {
  items: RunSummary[];
  offset: number;
  limit: number;
  total: number;
  overall_total: number;
  revision: number;
}
export interface Run {
  id: string;
  name: string;
  mode: "both" | "fastqc" | "multiqc";
  state: RunState;
  stage: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  threads: number;
  inputs: string[];
  input_pairing?: InputPairing[];
  sample_groups?: SampleGroup[];
  sample_input_paths?: string[];
  output_root?: string;
  output_directory?: string;
  rerun_of?: string | null;
  pairing_note?: string | null;
  import_summary?: {
    supported_reports?: number;
    unsupported_files: number;
    exclusions: { filename: string; reason: string }[];
  };
  report_inputs?: {
    path: string;
    kind?: string;
    tool?: string;
    version?: string | null;
    schema?: string;
    snapshot_sha256?: string;
    snapshot_artifact?: string;
  }[];
  integrity?: IntegrityResult;
  screening?: ScreeningRecord;
  release_export?: ReleaseExport;
  release_reviews?: ReviewEvent[];
  report_input_map?: Record<
    string,
    { path?: string; source_report?: string; id: string; multiqc_name?: string }
  >;
  input_outcomes?: {
    id: string;
    path: string;
    name: string;
    state: string;
    error: string | null;
    report: string;
    html: string;
    exit_code: number | null;
    finished_at: string | null;
  }[];
  progress: number;
  error: string | null;
  reports: { path: string; size: number }[];
  sample_count: number;
  tools?: Record<string, ToolInfo>;
  warnings?: string[];
  executions?: {
    tool: string;
    argv: string[];
    exit_code: number | null;
    started_at: string;
    finished_at: string | null;
  }[];
}
export interface IntegrityResult {
  task_id: string;
  state: string;
  result: string;
  mode: "full" | "quick";
  version: string;
  total_files: number;
  configured_pairs: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  artifact: string;
  current_file?: {
    path: string;
    records_scanned: number;
    state: string;
  } | null;
  files: {
    id: string;
    path: string;
    state: string;
    coverage: string;
    records_scanned: number;
    bases_scanned: number;
    gzip_crc: string;
    sha256: string | null;
    q20_bases: number | null;
    q30_bases: number | null;
    quality_bases: number | null;
    encoding_source?: string | null;
    source_snapshot?: {
      size: number;
      mtime_ns: number;
      device: number;
      inode: number;
    };
    error: string | null;
  }[];
  pairs: {
    id: string;
    r1: string;
    r2: string;
    state: string;
    error: string | null;
    method: string;
  }[];
}
export type MetadataSource = "auto" | "confirmed" | "manual";
export interface SampleGroup {
  id: string;
  display_name: string;
  files: string[];
  source: MetadataSource;
}
export interface SampleConfiguration {
  input_pairing: InputPairing[];
  sample_groups: SampleGroup[];
  pairing_note?: string | null;
  import_summary?: {
    supported_reports?: number;
    unsupported_files: number;
    exclusions: { filename: string; reason: string }[];
  };
  report_inputs?: {
    path: string;
    kind?: string;
    tool?: string;
    version?: string | null;
    schema?: string;
    snapshot_sha256?: string;
    snapshot_artifact?: string;
  }[];
}
export interface OutputLocation {
  path: string;
  default: boolean;
  available: boolean;
  free_bytes: number | null;
  error: string | null;
}
export interface RerunConfiguration extends SampleConfiguration {
  name: string;
  mode: Run["mode"];
  paths: string[];
  entries: Entry[];
  threads: number;
  output_root: string;
  rerun_of: string;
}
export interface InputPairing {
  path: string;
  name: string;
  read: string | null;
  pair_key: string | null;
  paired: boolean;
  mate: string | null;
  source?: MetadataSource;
  ambiguous?: boolean;
  assignment?: "paired" | "single" | "unpaired";
  lane?: string | null;
  chunk?: string | null;
}
export interface Entry {
  name: string;
  path: string;
  kind: "directory" | "fastq" | "fastqc" | "qcreport" | "file";
  size: number | null;
  modified: number;
  read: string | null;
  pair_key: string | null;
  paired: boolean;
  mate: string | null;
  sample_key?: string | null;
  sample_name?: string;
  lane?: string | null;
  chunk?: string | null;
  ambiguous?: boolean;
}
export interface Listing {
  path: string;
  parent: string | null;
  entries: Entry[];
  total: number;
  sample_groups?: Record<string, { paths: string[]; total: number }>;
  snapshot?: string;
  next_offset?: number | null;
}
export interface ToolInfo {
  name: string;
  executable: string;
  available: boolean;
  compatible: boolean;
  version: string | null;
  error: string | null;
}
export interface MultiQCSummary {
  tool?: string;
  version?: string | null;
  status?: "available" | "empty" | "missing" | "unsupported" | "invalid";
  message?: string | null;
  columns: {
    key: string;
    title: string;
    description: string;
    namespace: string;
    unit: string;
    raw_key: string;
    raw_unit?: string;
    section?: string;
    hidden?: boolean;
  }[];
  rows: { sample: string; values: Record<string, string | number> }[];
}
export interface Config {
  roots: string[];
  default_output?: string;
  output_locations?: OutputLocation[];
  cpus: number;
  memory_mb: number;
  max_threads: number;
  tools: { fastqc: boolean; multiqc: boolean };
  prefix: string;
  tool_details?: Record<string, ToolInfo>;
}
export interface Module {
  name: string;
  status: string;
  columns: string[];
  rows: string[][];
  metadata?: string[][];
  comments?: string[];
  summary_status?: string;
  available?: boolean;
}
export interface BaseQuality {
  base: string;
  mean: number | null;
  median: number | null;
  lower_quartile: number | null;
  upper_quartile: number | null;
  percentile_10: number | null;
  percentile_90: number | null;
}
export interface Sample {
  id: string;
  name: string;
  fastqc_version: string;
  total_sequences: number | null;
  gc_percent: number | null;
  sequence_length: string;
  encoding: string;
  status: string;
  modules: Module[];
  per_base_quality: BaseQuality[];
}
