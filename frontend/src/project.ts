// Domain declarations reference existing analyses; scientific QC types stay in types.ts.
export type EntityKind = "project" | "sample" | "sequencing_run";
export interface DeclaredFields {
  display_name: string;
  declared_identifier?: string;
  notes?: string;
  status?: "active" | "archived";
  assay?: string;
  library_type?: string;
  expected_yield?: {
    metric: "reads" | "read_pairs" | "bases";
    minimum: number;
  } | null;
  platform?: string;
  sequenced_at?: string;
  input_stage?: "unknown" | "raw_fastq" | "upstream_processed";
}
export interface ProjectEntity {
  id: string;
  kind: EntityKind;
  project_id: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
  declared: DeclaredFields;
  counts?: Record<string, number>;
  qc_readiness?: string;
  release_readiness?: string;
}
export interface CatalogPage<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}
export interface AnalysisLink {
  id: string;
  project_id: string;
  analysis_id: string;
  created_at: string;
  analysis: {
    id: string;
    name: string;
    mode: string;
    state: string;
    created_at: string;
  } | null;
}
export interface ProjectFile {
  file_id: string;
  filename: string;
  report_id: string | null;
  read: string | null;
  lane: string | null;
  chunk: string | null;
  input_available: boolean;
}
export interface FileAssignment {
  file_id: string;
  sample_id: string;
  sequencing_run_id: string;
  lane?: string | null;
  chunk?: string | null;
  library_identifier?: string | null;
  read?: string | null;
  source: "user_confirmed" | "user_assigned";
}
export interface ProjectAssociation {
  current_report_id?: string | null;
  analysis_id?: string;
  id: string;
  file_id: string;
  project_id: string;
  analysis_link_id: string;
  sample_id: string;
  sequencing_run_id: string;
  revision: number;
  created_at: string;
  declared: Pick<
    FileAssignment,
    "lane" | "chunk" | "library_identifier" | "read" | "source"
  >;
  observed: { filename: string; report_id: string | null };
}
export interface ProjectEvidence {
  id: string;
  analysis_link_id: string;
  created_at: string;
  sha256: string;
  summary: {
    analysis_id: string;
    qc_state: string;
    readiness: string;
    review_state: string;
    decision_id: string | null;
    association_count: number;
  };
}
export const entityLabel = (entity: ProjectEntity) =>
  `${entity.declared.display_name}${entity.declared.declared_identifier ? ` · ${entity.declared.declared_identifier}` : ""} · ${entity.id.slice(-8)}`;
export function declaredMinimum(
  metric: string,
  minimum: string,
): DeclaredFields["expected_yield"] {
  if (!minimum.trim()) return null;
  if (!/^[0-9]+$/.test(minimum) || !Number.isSafeInteger(Number(minimum)))
    throw new Error(
      "Expected yield must be a nonnegative whole number within the safe integer range.",
    );
  if (!["reads", "read_pairs", "bases"].includes(metric))
    throw new Error("Choose explicit expected-yield units.");
  return {
    metric: metric as "reads" | "read_pairs" | "bases",
    minimum: Number(minimum),
  };
}
export function assignmentsFor(
  files: ProjectFile[],
  sampleId: string,
  runId: string,
): FileAssignment[] {
  if (!sampleId || !runId)
    throw new Error("Choose explicit sample and sequencing-run IDs.");
  if (new Set(files.map((file) => file.file_id)).size !== files.length)
    throw new Error("A file may be assigned only once.");
  return files.map((file) => ({
    file_id: file.file_id,
    sample_id: sampleId,
    sequencing_run_id: runId,
    lane: file.lane,
    chunk: file.chunk,
    read: file.read,
    source: "user_confirmed",
  }));
}
