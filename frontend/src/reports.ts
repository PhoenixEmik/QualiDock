import type { Run } from "./types";

export function htmlReports(reports: Run["reports"]) {
  return reports
    .filter((report) => report.path.toLowerCase().endsWith(".html"))
    .sort((a, b) => {
      const combined = (path: string) => path === "multiqc/multiqc_report.html";
      return Number(combined(b.path)) - Number(combined(a.path));
    });
}

export function previewPath(runId: string, path: string) {
  return `api/report-preview?${new URLSearchParams({ run_id: runId, path })}`;
}
