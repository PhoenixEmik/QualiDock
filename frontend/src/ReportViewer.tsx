import { useEffect, useState } from "react";
import { ArrowDownToLine, Maximize2, Minimize2, RefreshCw } from "lucide-react";
import { url } from "./api";
import { htmlReports, previewPath } from "./reports";
import type { Run } from "./types";

type PreviewState =
  "checking" | "loading" | "ready" | "error" | "unavailable" | "unsupported";

export default function ReportViewer({ run }: { run: Run }) {
  const reports = htmlReports(run.reports);
  const [selection, setSelection] = useState("");
  const selected =
    reports.find((report) => report.path === selection) || reports[0];
  const [expanded, setExpanded] = useState(false);
  return (
    <section
      className={`report-viewer ${expanded ? "report-viewer-expanded" : ""}`}
      aria-labelledby="report-viewer-title"
    >
      <div className="report-viewer-toolbar">
        <h2 id="report-viewer-title">Official report</h2>
        {selected && (
          <>
            <label className="sr-only" htmlFor="report-selection">
              Select HTML report
            </label>
            <select
              id="report-selection"
              value={selected.path}
              onChange={(event) => setSelection(event.target.value)}
            >
              {reports.map((report) => (
                <option key={report.path} value={report.path}>
                  {report.path === "multiqc/multiqc_report.html"
                    ? "MultiQC · Combined report"
                    : report.path}
                </option>
              ))}
            </select>
            <button
              className="button small"
              aria-pressed={expanded}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              {expanded ? "Compact view" : "Full-height view"}
            </button>
            <a
              className="button small"
              href={url(
                `api/runs/${run.id}/download?path=${encodeURIComponent(selected.path)}`,
              )}
              download
            >
              <ArrowDownToLine size={14} /> Download
            </a>
          </>
        )}
      </div>
      {selected ? (
        <Preview
          key={`${run.id}:${selected.path}`}
          runId={run.id}
          path={selected.path}
        />
      ) : (
        <p className="report-preview-message" role="status">
          {run.reports.length
            ? "No HTML report is available to preview. Other result formats can be downloaded below."
            : ["queued", "running"].includes(run.state)
              ? "HTML previews will be available when this analysis produces reports."
              : "No HTML report was saved for this analysis. Check the analysis log."}
        </p>
      )}
      <p className="report-preview-help">
        Isolated preview. MultiQC uses temporary in-frame settings that reset
        when the report reloads. Application cookies and browser storage remain
        inaccessible. External services, form-based controls (including MultiQC
        text filters), and in-report exports are blocked. Download the original
        HTML for these features or reports needing external assets.
      </p>
    </section>
  );
}

function Preview({ runId, path }: { runId: string; path: string }) {
  const [preview, setPreview] = useState<{
    state: PreviewState;
    message: string;
  }>({ state: "checking", message: "" });
  const { state, message } = preview;
  const [attempt, setAttempt] = useState(0);
  const source = url(previewPath(runId, path));
  useEffect(() => {
    const controller = new AbortController();
    setPreview({ state: "checking", message: "" });
    // A sandboxed frame cannot be inspected for HTTP errors. Check the same
    // authenticated resource first, without copying report HTML into React.
    void fetch(source, {
      method: "HEAD",
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then((response) => {
        if (controller.signal.aborted) return;
        if (response.ok) setPreview({ state: "loading", message: "" });
        else if (response.status === 404) {
          setPreview({
            state: "unavailable",
            message:
              "This saved report is no longer available. Check the analysis output directory.",
          });
        } else if (response.status === 415) {
          setPreview({
            state: "unsupported",
            message:
              "This report format cannot be previewed. Download the original file below.",
          });
        } else {
          setPreview({
            state: "error",
            message:
              response.status === 401 || response.status === 403
                ? "Report access was denied. Check your session and report permissions."
                : "The report could not be loaded. Retry or download the original file.",
          });
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setPreview({
            state: "error",
            message:
              "The report could not be reached. Retry or download the original file.",
          });
        }
      });
    const timeout = window.setTimeout(() => {
      controller.abort();
      setPreview((value) =>
        value.state === "checking" || value.state === "loading"
          ? {
              state: "error",
              message:
                "The preview timed out. Retry or download the original file.",
            }
          : value,
      );
    }, 30000);
    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [source, attempt]);
  const visible = state === "loading" || state === "ready";
  return (
    <div
      className="report-preview"
      aria-busy={state === "checking" || state === "loading"}
    >
      {(state === "checking" || state === "loading") && (
        <p className="report-preview-message" role="status">
          Loading report…
        </p>
      )}
      {message && (
        <div className="report-preview-message" role="status">
          <p>{message}</p>
          <button
            className="button small"
            onClick={() => setAttempt((value) => value + 1)}
          >
            <RefreshCw size={14} /> Retry preview
          </button>
        </div>
      )}
      {visible && (
        <iframe
          key={attempt}
          src={source}
          title={`Official QC report: ${path}`}
          sandbox="allow-scripts"
          referrerPolicy="no-referrer"
          onLoad={() => setPreview({ state: "ready", message: "" })}
          onError={() => {
            setPreview({
              state: "error",
              message:
                "The browser could not display this preview. Download the original file.",
            });
          }}
        />
      )}
    </div>
  );
}
