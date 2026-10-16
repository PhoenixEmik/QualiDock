// Operation metadata only: scientific results remain in existing QC/validation models.
export interface BatchStage {
  state:
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "skipped"
    | "not_evaluated";
  reused?: boolean;
  reason?: string | null;
  result?: string;
  validation_result?: string;
  task_id?: string;
  values?: {
    sample_id: string;
    sample_name: string;
    totals: { reads: number | null; bases: number | null };
    target_state: string;
    explanation: string;
  }[];
}
export interface BatchFile {
  file_id: string;
  filename: string;
  sample_id: string;
  sequencing_run_id: string;
  declared: {
    lane?: string | null;
    chunk?: string | null;
    read?: string | null;
  };
  source_snapshot: { size: number };
}
export interface BatchPlan {
  id: string;
  project_id: string;
  fingerprint: string;
  created_at: string;
  file_count: number;
  source_bytes: number;
  tools: Record<string, string>;
  units: {
    id: string;
    sequencing_run_id: string;
    display_name: string;
    files: BatchFile[];
    reuse: { analysis_id: string } | null;
    reuse_reason: string;
    warnings: string[];
  }[];
  options: {
    mode: string;
    threads: number;
    integrity: string;
    output_root: string;
  };
  skipped: { file_id?: string; entity_id?: string; reason: string }[];
  expected_outputs: string[];
  io_note: string;
}
export interface BatchAttempt {
  id: string;
  plan_id: string;
  state: string;
  created_at: string;
  finished_at: string | null;
  error: string | null;
  retry_of: string | null;
  release_state: string;
  units: {
    id: string;
    display_name: string;
    analysis_id: string | null;
    owned: boolean;
    file_ids: string[];
    stages: Record<string, BatchStage>;
    input_outcomes?: {
      id: string;
      name: string;
      state: string;
      error: string | null;
    }[];
    integrity_progress?: {
      state?: string;
      total_files?: number;
      current_file?: {
        name?: string;
        state?: string;
        records_scanned?: number;
      };
    };
  }[];
}
export const batchActive = (state: string) =>
  ["queued", "running"].includes(state);
export function stageLabel(stage: BatchStage): string {
  return `${stage.state.replaceAll("_", " ")}${stage.reused ? " · reused" : ""}${stage.result ? ` · ${stage.result}` : ""}${stage.validation_result ? ` · target ${stage.validation_result.replaceAll("_", " ")}` : ""}`;
}
export function selectCohortRows(
  ids: string[],
  values: string[],
  maximum = 100,
): string[] {
  const next = [...new Set([...ids, ...values])];
  if (next.length > maximum)
    throw new Error(
      `Select at most ${maximum} records, or narrow the selection.`,
    );
  return next.length === ids.length ? ids : next;
}
