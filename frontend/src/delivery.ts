import type { DemultiplexEvidence } from "./demultiplex";
/** Delivery quantities are source counts, independent of FastQC module verdicts. */
export type QuantityMetric = "reads" | "read_pairs" | "bases";
export interface QuantityTarget {
  sample_id: string;
  metric: QuantityMetric;
  minimum: number;
}
export interface DeliveryFile {
  screening_snapshot_matches?: boolean;
  file_id: string;
  path: string;
  filename: string;
  input_reference: string;
  sample_id: string;
  sample_name: string;
  lane: string | null;
  chunk: string | null;
  read: string;
  pair_source: string | null;
  input_available: boolean;
  availability_error: string | null;
  qc_snapshot_matches: boolean | null;
  size_bytes: number | null;
  size_source: string;
  sequence_length: string | null;
  reads: number | null;
  bases: number | null;
  q20_bases: number | null;
  q30_bases: number | null;
  quality_bases: number | null;
  counts_source: string;
  sha256: string | null;
  checksum_status: string;
  integrity_state: string;
  report_id: string | null;
}
export interface ReconciliationEntry {
  expected_row?: number;
  identity?: Record<string, string>;
  file_id?: string;
  file_ids?: string[];
  metric?: string;
  message?: string;
  expected?: string | number;
  observed?: string | number;
}
export interface DeliveryData {
  demultiplex?: DemultiplexEvidence | null;
  analysis_id: string;
  name: string;
  source_kind: string;
  files: DeliveryFile[];
  notices: { code: string; message: string; file_id?: string }[];
  reconciliation: {
    status: string;
    message?: string;
    missing: ReconciliationEntry[];
    extra: string[];
    ambiguous: ReconciliationEntry[];
    duplicates: ReconciliationEntry[];
    mismatches: ReconciliationEntry[];
    unavailable: ReconciliationEntry[];
    matched: ReconciliationEntry[];
  };
  expected_manifest: {
    updated_at: string;
    format: string;
    files: unknown[];
  } | null;
  targets: QuantityTarget[];
  assay: string;
  input_stage: string;
  processing_notes: string;
  delivery_revision: number;
  yields: {
    sample_id: string;
    sample_name: string;
    file_ids: string[];
    totals: Record<
      | "reads"
      | "read_pairs"
      | "bases"
      | "q20_bases"
      | "q30_bases"
      | "quality_bases"
      | "q20_percent"
      | "q30_percent",
      number | null
    >;
    target: QuantityTarget | null;
    target_state: string;
    observed: number | null;
    denominator: string;
    provenance: string[];
    explanation: string;
  }[];
}
export interface TargetDraft {
  metric: QuantityMetric;
  minimum: string;
}
export function configuredTargets(
  drafts: Record<string, TargetDraft>,
): QuantityTarget[] {
  return Object.entries(drafts).flatMap(([sample_id, draft]) => {
    if (!draft.minimum.trim()) return [];
    if (
      !/^\d+$/.test(draft.minimum) ||
      !Number.isSafeInteger(Number(draft.minimum))
    )
      throw new Error(
        "Quantity targets require nonnegative whole numbers without scaling (for example, 30000000).",
      );
    return [
      { sample_id, metric: draft.metric, minimum: Number(draft.minimum) },
    ];
  });
}
export const quantity = (value: number | null) =>
  value === null
    ? "Not evaluated"
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
