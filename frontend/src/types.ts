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
export interface Entry {
  name: string;
  path: string;
  kind: "directory" | "fastq" | "fastqc" | "file";
  size: number | null;
  modified: number;
  read: string | null;
  pair_key: string | null;
  paired: boolean;
  mate: string | null;
}
export interface Listing {
  path: string;
  parent: string | null;
  entries: Entry[];
  total: number;
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
  columns: {
    key: string;
    title: string;
    description: string;
    namespace: string;
    unit: string;
    raw_key: string;
  }[];
  rows: { sample: string; values: Record<string, string | number> }[];
}
export interface Config {
  roots: string[];
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
