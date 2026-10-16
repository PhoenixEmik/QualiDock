import type { ToolInfo } from "./types";
export interface ScreeningDatabase {
  id: string;
  name: string;
  version: string;
  source: string;
  reference_taxids: string[];
  available?: boolean;
  error?: string;
  bytes?: number;
}
export interface ScreeningFile {
  id: string;
  path: string;
  name: string;
  state: string;
  coverage: string;
  records_processed: number | null;
  classified_records: number | null;
  unclassified_records: number | null;
  known_input_records: number | null;
  denominator_source: string | null;
  screened_fraction: number | null;
  error: string | null;
  report_artifact: string | null;
  metrics_artifact: string | null;
}
export interface ScreeningRecord {
  task_id: string;
  state: string;
  tool: ToolInfo;
  database: ScreeningDatabase;
  database_files: { name: string; sha256: string; bytes: number }[];
  assay: string;
  expected_taxids: string[];
  total_files: number;
  files: ScreeningFile[];
  current_file_id: string | null;
  phase: string;
  error: string | null;
  artifact: string;
  finished_at: string | null;
}
export interface ScreeningConfig {
  tool: ToolInfo;
  databases: ScreeningDatabase[];
  error: string | null;
  max_threads: number;
}
export interface ScreeningMetrics {
  source_analysis_id: string;
  source_task_id: string;
  file_id: string;
  columns: string[];
  rows: {
    reported_percent: string;
    clade_reads: number;
    direct_reads: number;
    rank: string;
    taxid: string;
    name: string;
    raw: string[];
  }[];
  records_processed: number | null;
  denominator: string;
  source_tool: string;
  source_version: string;
  database: ScreeningDatabase;
  database_files: { name: string; sha256: string; bytes: number }[];
  coverage: string;
  screened_fraction: number | null;
  expected_taxids: string[];
}
export function taxonomyIds(value: string) {
  if (!value.trim()) return [];
  const ids = value.trim().split(/[\s,]+/);
  if (ids.length > 20 || ids.some((id) => !/^\d{1,20}$/.test(id)))
    throw new Error(
      "Enter at most 20 explicit decimal taxonomy IDs, separated by commas or spaces.",
    );
  return [...new Set(ids)];
}
