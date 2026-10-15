import { useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  CircleHelp,
  Clock3,
  FileArchive,
  FileBarChart2,
  FileText,
  HardDrive,
  LayoutDashboard,
  RefreshCw,
  ShieldCheck,
  Square,
  Terminal,
  X,
} from "lucide-react";
import { bytes, date, modeLabel, url } from "./api";
import { Empty, State } from "./Feedback";
import type { DetailTab, Run, Sample, MultiQCSummary } from "./types";
import QcModule from "./QcModule";
import { findModule, moduleNames } from "./qc";

const active = (run: Run) => ["running", "queued"].includes(run.state);
const detailTabs = [
  { id: "overview" as const, label: "Overview & logs" },
  { id: "metrics" as const, label: "QC metrics" },
  { id: "reports" as const, label: "Reports" },
];
interface Props {
  currentRun: Run;
  samples: Sample[];
  multiqc?: MultiQCSummary;
  aggregate: (id: string) => Promise<void>;
  multiqcAvailable: boolean;
  logs: string;
  tab: DetailTab;
  setTab: (value: DetailTab) => void;
  busy: boolean;
  logsLoading: boolean;
  metricsLoading: boolean;
  cancelling: boolean;
  cancel: (id: string) => Promise<void>;
  reselect: (run: Run) => Promise<void>;
}
export default function AnalysisDetail({
  currentRun,
  samples,
  multiqc,
  aggregate,
  multiqcAvailable,
  logs,
  tab,
  setTab,
  busy,
  logsLoading,
  metricsLoading,
  cancelling,
  cancel,
  reselect,
}: Props) {
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [sampleId, setSampleId] = useState("");
  const [metric, setMetric] = useState("Per base sequence quality");
  const currentSample =
    samples.find((sample) => sample.id === sampleId) || samples[0];
  return (
    <section className="analysis-detail" aria-label="Analysis details">
      <div className="analysis-detail-heading">
        <div>
          <State value={currentRun.state} />
          <span>
            {modeLabel(currentRun.mode)} · {currentRun.inputs.length} input
            inputs
          </span>
        </div>
        <div>
          {!active(currentRun) &&
            currentRun.reports.some(
              (report) =>
                report.path.startsWith("fastqc/") &&
                report.path.endsWith("_fastqc.zip"),
            ) && (
              <button
                className="button small"
                disabled={busy || !multiqcAvailable}
                title={
                  multiqcAvailable
                    ? "Aggregate these saved FastQC results without rerunning FastQC"
                    : "A compatible MultiQC installation is required"
                }
                onClick={() => void aggregate(currentRun.id)}
              >
                Generate MultiQC
              </button>
            )}
          {active(currentRun) ? (
            <button
              className="button small danger"
              disabled={cancelling}
              onClick={() => void cancel(currentRun.id)}
            >
              <Square size={13} />
              {cancelling ? "Cancelling…" : "Cancel analysis"}
            </button>
          ) : (
            <button
              className="button small"
              disabled={busy}
              onClick={() => void reselect(currentRun)}
            >
              <RefreshCw size={14} />
              Rerun
            </button>
          )}
        </div>
      </div>
      {currentRun.error && (
        <div className="error" role="alert">
          {currentRun.error}
        </div>
      )}
      <div
        className="detail-tabs"
        role="tablist"
        aria-label="Analysis sections"
      >
        {detailTabs.map((item, index) => (
          <button
            key={item.id}
            id={`detail-tab-${item.id}`}
            role="tab"
            aria-selected={tab === item.id}
            aria-controls={`detail-panel-${item.id}`}
            tabIndex={tab === item.id ? 0 : -1}
            className={tab === item.id ? "active" : ""}
            onClick={() => setTab(item.id)}
            onKeyDown={(event) => {
              let next: number | undefined;
              if (event.key === "ArrowRight")
                next = (index + 1) % detailTabs.length;
              else if (event.key === "ArrowLeft")
                next = (index + detailTabs.length - 1) % detailTabs.length;
              else if (event.key === "Home") next = 0;
              else if (event.key === "End") next = detailTabs.length - 1;
              if (next !== undefined) {
                event.preventDefault();
                setTab(detailTabs[next].id);
                document
                  .getElementById(`detail-tab-${detailTabs[next].id}`)
                  ?.focus();
              }
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        hidden={tab !== "overview"}
        id="detail-panel-overview"
        aria-labelledby="detail-tab-overview"
        tabIndex={0}
      >
        <dl className="job-information">
          <div>
            <dt>Stage</dt>
            <dd>{currentRun.stage}</dd>
          </div>
          <div>
            <dt>CPU threads</dt>
            <dd>{currentRun.threads}</dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>{date(currentRun.created_at)}</dd>
          </div>
          <div>
            <dt>Started</dt>
            <dd>
              {currentRun.started_at
                ? date(currentRun.started_at)
                : "Not started"}
            </dd>
          </div>
          <div>
            <dt>Finished</dt>
            <dd>
              {currentRun.finished_at ? date(currentRun.finished_at) : "—"}
            </dd>
          </div>
          <div>
            <dt>Run ID</dt>
            <dd className="mono">{currentRun.id}</dd>
          </div>
        </dl>
        {currentRun.tools && (
          <dl className="job-information">
            {Object.entries(currentRun.tools).map(([name, tool]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{tool.version || "Version unavailable"}</dd>
              </div>
            ))}
          </dl>
        )}
        {currentRun.executions?.map((execution, index) => (
          <p className="inline-note" key={index}>
            {execution.tool}:{" "}
            {execution.exit_code === null
              ? "Awaiting exit status"
              : `exit ${execution.exit_code}`}
          </p>
        ))}
        {currentRun.warnings?.map((warning, index) => (
          <p className="inline-note" key={index}>
            {warning}
          </p>
        ))}
        <details className="analysis-inputs">
          <summary>Input references ({currentRun.inputs.length})</summary>
          <ul>
            {currentRun.inputs.map((input) => (
              <li key={input} className="mono">
                {input}
              </li>
            ))}
          </ul>
        </details>
        <div className="log-heading">
          <Terminal size={14} />
          <strong>Analysis log</strong>
          <small>stdout + stderr</small>
        </div>
        <pre className="log-panel" tabIndex={0} aria-label="Analysis log">
          {logs ||
            (logsLoading
              ? "Loading log…"
              : active(currentRun)
                ? "Waiting for process output…"
                : "No process output recorded.")}
        </pre>
      </div>
      <div
        role="tabpanel"
        hidden={tab !== "metrics"}
        id="detail-panel-metrics"
        aria-labelledby="detail-tab-metrics"
        tabIndex={0}
      >
        {tab === "metrics" &&
          (samples.length ? (
            <>
              <p className="metric-summary">
                {samples.length} read files ·{" "}
                {samples.every((sample) => sample.total_sequences !== null)
                  ? `${samples.reduce((sum, sample) => sum + (sample.total_sequences || 0), 0).toLocaleString()} sequences`
                  : "Sequence totals unavailable"}{" "}
                ·{" "}
                {
                  samples.filter((sample) =>
                    ["warn", "fail"].includes(sample.status),
                  ).length
                }{" "}
                files with QC warnings or failures
              </p>
              <button
                className="button small inspector-toggle"
                aria-expanded={detailsOpen}
                aria-controls="sample-details"
                onClick={() => setDetailsOpen((value) => !value)}
              >
                {detailsOpen ? "Hide" : "Show"} sample details
              </button>
              <div
                className={`dashboard-layout ${detailsOpen ? "" : "details-collapsed"}`}
              >
                <section className="chart-section">
                  <div className="chart-heading">
                    <div>
                      <h2>{metric}</h2>
                      <span>{currentSample?.encoding}</span>
                    </div>
                    <select
                      aria-label="Select QC metric"
                      value={metric}
                      onChange={(e) => setMetric(e.target.value)}
                    >
                      {(currentSample ? moduleNames(currentSample) : []).map(
                        (m) => (
                          <option key={m} value={m}>
                            {m} ·{" "}
                            {currentSample &&
                            findModule(currentSample, m)?.available !== false
                              ? (
                                  findModule(currentSample, m)?.status ||
                                  "unavailable"
                                ).toUpperCase()
                              : "UNAVAILABLE"}
                          </option>
                        ),
                      )}
                    </select>
                  </div>
                  <div className="sample-selector">
                    <label htmlFor="sample">SAMPLE</label>
                    <select
                      id="sample"
                      value={currentSample?.id || ""}
                      onChange={(e) => setSampleId(e.target.value)}
                    >
                      {samples.map((sample) => (
                        <option key={sample.id} value={sample.id}>
                          {sample.name}
                        </option>
                      ))}
                    </select>
                    {currentSample && (
                      <State
                        value={
                          (findModule(currentSample, metric)?.available ===
                          false
                            ? "unavailable"
                            : findModule(currentSample, metric)?.status) ||
                          "unavailable"
                        }
                      />
                    )}
                  </div>
                  {currentSample && (
                    <QcModule sample={currentSample} metric={metric} />
                  )}
                  <div className="chart-note">
                    <CircleHelp size={13} />
                    {metric === "Per base sequence quality"
                      ? "Boxes show the 25th–75th percentiles. Whiskers show the 10th–90th percentiles. Scroll to zoom."
                      : metric === "Per tile sequence quality"
                        ? "Reported deviations from mean quality by tile and base bin. Scroll to zoom."
                        : "Parsed directly from the official FastQC output. Exact values are available in the table."}
                  </div>
                </section>
                <aside
                  id="sample-details"
                  className="sample-inspector"
                  hidden={!detailsOpen}
                >
                  <div className="summary-label">SAMPLE DETAILS</div>
                  <FileText size={27} strokeWidth={1.3} />
                  <h3>{currentSample?.name}</h3>
                  <dl>
                    <div>
                      <dt>Sequences</dt>
                      <dd>
                        {currentSample?.total_sequences?.toLocaleString() ??
                          "—"}
                      </dd>
                    </div>
                    <div>
                      <dt>Read length</dt>
                      <dd>{currentSample?.sequence_length || "—"} bp</dd>
                    </div>
                    <div>
                      <dt>GC content</dt>
                      <dd>{currentSample?.gc_percent ?? "—"}%</dd>
                    </div>
                    <div>
                      <dt>FastQC version</dt>
                      <dd>{currentSample?.fastqc_version}</dd>
                    </div>
                  </dl>
                  <div className="inspector-divider" />
                  <h4>Module checks</h4>
                  <div className="module-checks">
                    {currentSample?.modules.map((module) => (
                      <div key={module.name}>
                        <span>{module.name}</span>
                        <span
                          className={`module-status ${module.status}`}
                          title={module.status}
                        >
                          {module.status === "pass" ? (
                            <Check size={13} />
                          ) : module.status === "warn" ? (
                            "!"
                          ) : module.status === "fail" ? (
                            <X size={13} />
                          ) : (
                            "?"
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </aside>
              </div>
              <section className="sample-table-section">
                <div className="section-heading">
                  <div>
                    <h2>Sample summary</h2>
                    <span className="subtle">{samples.length} read files</span>
                  </div>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Sample</th>
                        <th>QC status</th>
                        <th>Sequences</th>
                        <th>Read length</th>
                        <th>GC content</th>
                        <th>Modules</th>
                      </tr>
                    </thead>
                    <tbody>
                      {samples.map((sample) => (
                        <tr
                          key={sample.id}
                          className={
                            sample.id === currentSample?.id
                              ? "row-selected"
                              : ""
                          }
                        >
                          <td>
                            <button
                              className="file-name"
                              onClick={() => setSampleId(sample.id)}
                            >
                              <FileText size={17} />
                              {sample.name}
                            </button>
                          </td>
                          <td>
                            <State value={sample.status} />
                          </td>
                          <td className="mono">
                            {sample.total_sequences?.toLocaleString() ?? "—"}
                          </td>
                          <td>{sample.sequence_length} bp</td>
                          <td>{sample.gc_percent ?? "—"}%</td>
                          <td>
                            <span className="check-count">
                              {
                                sample.modules.filter(
                                  (m) => m.status === "pass",
                                ).length
                              }
                              /{sample.modules.length} pass
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          ) : (
            <Empty
              icon={active(currentRun) ? Clock3 : LayoutDashboard}
              title={
                metricsLoading
                  ? "Loading QC metrics"
                  : active(currentRun)
                    ? "Waiting for QC results"
                    : "No normalized metrics available"
              }
              action={
                <button className="button" onClick={() => setTab("overview")}>
                  View analysis log
                  <ArrowRight size={14} />
                </button>
              }
            >
              {metricsLoading
                ? "Reading saved FastQC metrics."
                : active(currentRun)
                  ? "QC metrics appear after FastQC produces parsed results."
                  : currentRun.error || "Check the analysis log for details."}
            </Empty>
          ))}
      </div>
      <div
        role="tabpanel"
        hidden={tab !== "reports"}
        id="detail-panel-reports"
        aria-labelledby="detail-tab-reports"
        tabIndex={0}
      >
        <section className="reports-section">
          <div className="report-intro">
            <ShieldCheck size={18} />
            <span>
              Official HTML reports download as files. Native charts use parsed
              QC data.
            </span>
          </div>
          {multiqc && !multiqc.rows.length && (
            <p className="inline-note" role="status">
              {multiqc.message ||
                "MultiQC General Statistics are unavailable for this analysis."}
            </p>
          )}
          {multiqc && multiqc.rows.length > 0 && (
            <section className="sample-table-section">
              <h2>MultiQC sample summary</h2>
              <p className="inline-note">
                General statistics as stored by MultiQC, without display scaling
                or unit conversions.
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Sample</th>
                      {multiqc.columns.map((column) => (
                        <th
                          key={column.key}
                          title={`${column.namespace}: ${column.description} (${column.raw_key})`}
                        >
                          {column.title}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {multiqc.rows.map((row) => (
                      <tr key={row.sample}>
                        <td>{row.sample}</td>
                        {multiqc.columns.map((column) => (
                          <td className="mono" key={column.key}>
                            {row.values[column.key] ?? "—"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {currentRun.reports.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Report or data file</th>
                    <th>Type</th>
                    <th>Size</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {currentRun.reports.map((report) => (
                    <tr key={report.path}>
                      <td>
                        <div className="file-name">
                          {report.path.endsWith(".html") ? (
                            <FileBarChart2 size={19} />
                          ) : report.path.endsWith(".zip") ? (
                            <FileArchive size={19} />
                          ) : (
                            <FileText size={19} />
                          )}
                          <span>{report.path}</span>
                        </div>
                      </td>
                      <td>
                        <span className="filetype">
                          {report.path.split(".").pop()?.toUpperCase()}
                        </span>
                      </td>
                      <td className="mono">{bytes(report.size)}</td>
                      <td>
                        <a
                          className="button small"
                          href={url(
                            `api/runs/${currentRun.id}/download?path=${encodeURIComponent(report.path)}`,
                          )}
                          download
                        >
                          <ArrowDownToLine size={14} />
                          Download
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              icon={FileBarChart2}
              title={
                active(currentRun)
                  ? "Reports are being prepared"
                  : "No report files available"
              }
            >
              {active(currentRun)
                ? "Reports appear as this analysis finishes."
                : "No files were produced. Check the analysis log in Overview."}
            </Empty>
          )}
          <div className="persistence-note">
            <HardDrive size={17} />
            <div>
              <strong>Saved beyond this session</strong>
              <p>
                Each analysis has its own output directory. Restarting QualiDock
                restores the saved results.
              </p>
            </div>
            <span className="mono">{currentRun.id.slice(0, 12)}</span>
          </div>
        </section>
      </div>
    </section>
  );
}
