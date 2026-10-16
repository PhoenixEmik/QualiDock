export interface ReleasePolicy {
  version: string;
  assay: string;
  required_checks: string[];
  fastqc_rules: { module: string; allowed_statuses: string[] }[];
}
export interface ReviewEvent {
  id: string;
  action: string;
  reason: string;
  rule_id: string | null;
  reviewer_label: string;
  actor: { uid: number; unix_user: string };
  created_at: string;
  sample_ids: string[];
  fingerprint: string;
}
export interface ReleaseCheck {
  id: string;
  name: string;
  state: string;
  mandatory: boolean;
  explanation: string;
  waiver?: ReviewEvent;
  evidence?: unknown;
  source_statuses?: unknown;
}
export interface ReleaseEvaluation {
  fingerprint: string;
  sample_ids: string[];
  policy: { definition: ReleasePolicy; revision: number } | null;
  readiness: string;
  review_state: string;
  checks: ReleaseCheck[];
  decision: ReviewEvent | null;
  active_waivers: ReviewEvent[];
  history: ReviewEvent[];
}
export interface ReleaseExport {
  task_id: string;
  state: string;
  release_status: string;
  sample_ids: string[];
  artifact: string | null;
  sha256: string | null;
  bytes?: number;
  error: string | null;
  requested_at: string;
  finished_at: string | null;
}
export function policyDefinition(
  version: string,
  assay: string,
  checks: string[],
  modules: Record<string, string>,
): ReleasePolicy {
  if (!version.trim() || !assay.trim())
    throw new Error(
      "Supply an explicit policy version and assay/project label.",
    );
  return {
    version: version.trim(),
    assay: assay.trim(),
    required_checks: [...new Set(["integrity", ...checks])],
    fastqc_rules: Object.entries(modules)
      .filter(([, allowed]) => allowed)
      .map(([module, allowed]) => ({
        module,
        allowed_statuses: allowed.split(","),
      })),
  };
}
