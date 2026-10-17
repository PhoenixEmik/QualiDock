import type { Run } from "./types";

export function htmlReports(reports: Run["reports"]) {
  return reports
    .filter((report) => report.path.toLowerCase().endsWith(".html"))
    .sort((a, b) => {
      const priority = (path: string) =>
        path === "multiqc/multiqc_report.html"
          ? 2
          : path.endsWith("/NanoPlot-report.html")
            ? 1
            : 0;
      return priority(b.path) - priority(a.path);
    });
}

export function previewPath(runId: string, path: string) {
  return `api/report-preview?${new URLSearchParams({ run_id: runId, path })}`;
}
