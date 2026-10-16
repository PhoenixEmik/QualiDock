import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  ChevronRight,
  FileBarChart2,
  Search,
  Square,
} from "lucide-react";
import { api, date, modeLabel } from "./api";
import { Empty, State } from "./Feedback";
import { processingModes } from "./processing";
import type { Run, RunSummary, HistoryPage } from "./types";

const active = (run: Pick<Run, "state">) =>
  ["queued", "running"].includes(run.state);
interface Props {
  revision: number;
  showRun: (run: Pick<Run, "id">) => void;
  reselect: (run: Pick<Run, "id">) => Promise<void>;
  cancel: (id: string) => Promise<void>;
  cancellingId: string;
  browse: () => void;
  fail: (error: unknown) => void;
}
export default function ResultsList({
  revision,
  showRun,
  reselect,
  cancel,
  cancellingId,
  browse,
  fail,
}: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyAll, setHistoryAll] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [analysisMode, setAnalysisMode] = useState("all");
  const [analysisSort, setAnalysisSort] = useState("created-desc");
  const [renameId, setRenameId] = useState("");
  const [renameName, setRenameName] = useState("");
  const [jobFilter, setJobFilter] = useState("all");
  const [analysisSearch, setAnalysisSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [renamed, setRenamed] = useState(0);
  useEffect(() => {
    setHistoryOffset(0);
  }, [analysisSearch, jobFilter, analysisMode, analysisSort]);
  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    const query = new URLSearchParams({
      offset: String(historyOffset),
      limit: "25",
      search: analysisSearch,
      state: jobFilter,
      mode: analysisMode,
      order: analysisSort,
    });
    void api<HistoryPage>(`api/history?${query}`)
      .then((page) => {
        if (cancelled) return;
        setRuns(page.items);
        setHistoryTotal(page.total);
        setHistoryAll(page.overall_total);
        setHistoryOffset(page.offset);
      })
      .catch((err) => {
        if (!cancelled) fail(err);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    revision,
    renamed,
    historyOffset,
    analysisSearch,
    jobFilter,
    analysisMode,
    analysisSort,
    fail,
  ]);
  const filteredRuns = runs;
  const rename = async () => {
    setBusy(true);
    setMessage("");
    try {
      const updated = await api<Run>(`api/runs/${renameId}`, {
        method: "PATCH",
        body: JSON.stringify({ name: renameName }),
      });
      setRuns((old) =>
        old.map((run) =>
          run.id === updated.id
            ? { ...run, name: updated.name, updated_at: updated.updated_at }
            : run,
        ),
      );
      setRenamed((value) => value + 1);
      setRenameId("");
      setMessage("Analysis renamed.");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-label="Analysis jobs">
      {message && <p role="status">{message}</p>}
      {renameId && (
        <form
          className="rename-analysis"
          aria-label="Rename analysis"
          onSubmit={(e) => {
            e.preventDefault();
            void rename();
          }}
        >
          <label>
            Analysis display name{" "}
            <input
              autoFocus
              maxLength={120}
              value={renameName}
              onChange={(e) => setRenameName(e.target.value)}
            />
          </label>
          <button
            className="button small"
            type="submit"
            disabled={busy || !renameName.trim()}
          >
            Save name
          </button>
          <button
            className="button small"
            type="button"
            onClick={() => setRenameId("")}
          >
            Cancel rename
          </button>
        </form>
      )}
      {historyAll > 0 && (
        <div className="jobs-toolbar">
          <label>
            Workflow{" "}
            <select
              aria-label="Filter analysis workflow"
              value={analysisMode}
              onChange={(e) => setAnalysisMode(e.target.value)}
            >
              <option value="all">All workflows</option>
              <option value="fastqc">FastQC only</option>
              <option value="both">FastQC + MultiQC</option>
              <option value="multiqc">MultiQC only</option>
              {processingModes.map((mode) => (
                <option key={mode} value={mode}>
                  {modeLabel(mode)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Sort{" "}
            <select
              aria-label="Sort analyses"
              value={analysisSort}
              onChange={(e) => setAnalysisSort(e.target.value)}
            >
              <option value="created-desc">Newest created</option>
              <option value="created-asc">Oldest created</option>
              <option value="finished-desc">Newest completed</option>
              <option value="finished-asc">Oldest completed</option>
            </select>
          </label>
          <label>
            State{" "}
            <select
              aria-label="Filter exact analysis state"
              value={jobFilter}
              onChange={(e) => setJobFilter(e.target.value)}
            >
              {[
                "all",
                "active",
                "issues",
                "queued",
                "running",
                "completed",
                "failed",
                "partial",
                "cancelled",
                "interrupted",
              ].map((state) => (
                <option key={state} value={state}>
                  {state}
                </option>
              ))}
            </select>
          </label>
          <label className="search-box">
            <Search size={15} />
            <input
              aria-label="Search analyses"
              maxLength={120}
              placeholder="Search analyses…"
              value={analysisSearch}
              onChange={(event) => setAnalysisSearch(event.target.value)}
            />
          </label>
        </div>
      )}
      {filteredRuns.length > 0 ? (
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label="Analysis list"
        >
          <table className="jobs-table">
            <thead>
              <tr>
                <th>Analysis</th>
                <th>Status</th>
                <th>Workflow</th>
                <th>Files</th>
                <th>Created</th>
                <th>Finished</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map((run) => (
                <tr key={run.id}>
                  <td>
                    <button className="job-name" onClick={() => showRun(run)}>
                      <FileBarChart2 size={18} />
                      <span>
                        <strong>{run.name}</strong>
                        <small>{run.stage}</small>
                      </span>
                    </button>
                  </td>
                  <td>
                    <State value={run.state} />
                  </td>
                  <td>{modeLabel(run.mode)}</td>
                  <td>{run.input_count}</td>
                  <td className="subtle">{date(run.created_at)}</td>
                  <td className="subtle">
                    {run.finished_at ? date(run.finished_at) : "—"}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="text-button"
                        onClick={() => {
                          setRenameId(run.id);
                          setRenameName(run.name);
                        }}
                        aria-label={`Rename ${run.name}`}
                      >
                        Rename
                      </button>
                      {!active(run) && (
                        <button
                          className="text-button"
                          onClick={() => void reselect(run)}
                          aria-label={`Rerun ${run.name}`}
                        >
                          Rerun
                        </button>
                      )}
                      {active(run) && (
                        <button
                          className="text-button danger"
                          disabled={!!cancellingId}
                          onClick={() => void cancel(run.id)}
                          aria-label={`Cancel ${run.name}`}
                        >
                          <Square size={12} />
                          {cancellingId === run.id ? "Cancelling…" : "Cancel"}
                        </button>
                      )}
                      <button
                        className="icon-button"
                        aria-label={`Open ${run.name}`}
                        onClick={() => showRun(run)}
                      >
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          icon={Activity}
          title={
            historyLoading
              ? "Loading analyses…"
              : historyAll
                ? "No matching analyses"
                : "No analyses yet"
          }
          action={
            historyAll ? (
              <button
                className="button"
                onClick={() => {
                  setJobFilter("all");
                  setAnalysisSearch("");
                  setAnalysisMode("all");
                }}
              >
                Clear filters
              </button>
            ) : (
              <button className="button" onClick={browse}>
                Choose input files
                <ArrowRight size={14} />
              </button>
            )
          }
        >
          {historyAll
            ? "Try another status or analysis name."
            : "Start from the Workspace to select files and configure a QC run."}
        </Empty>
      )}
      {historyTotal > 0 && (
        <div className="analytics-actions" aria-label="Analysis history pages">
          <span>
            {historyOffset + 1}–{Math.min(historyOffset + 25, historyTotal)} of{" "}
            {historyTotal} analyses
          </span>
          <button
            className="button small"
            disabled={historyLoading || !historyOffset}
            onClick={() => setHistoryOffset((value) => Math.max(0, value - 25))}
          >
            Previous analyses
          </button>
          <button
            className="button small"
            disabled={historyLoading || historyOffset + 25 >= historyTotal}
            onClick={() => setHistoryOffset((value) => value + 25)}
          >
            Next analyses
          </button>
        </div>
      )}
    </section>
  );
}
