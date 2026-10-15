import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  Dna,
  FileBarChart2,
  Files,
  LoaderCircle,
  LogOut,
  Plus,
  Search,
  ShieldCheck,
  Square,
  X,
} from "lucide-react";
import { api, AuthError, date, modeLabel, url } from "./api";
import type {
  Config,
  DetailTab,
  Entry,
  Listing,
  Run,
  Sample,
  MultiQCSummary,
  View,
} from "./types";
import { Empty, State } from "./Feedback";
import FileExplorer from "./FileExplorer";
import AnalysisDetail from "./AnalysisDetail";
import NewAnalysisForm from "./NewAnalysisForm";
import { resolveEntries, type ExplorerMode } from "./explorer";

const active = (run: Run) => ["queued", "running"].includes(run.state);
const nav = [
  { id: "workspace" as const, label: "Workspace", icon: Files },
  { id: "analyses" as const, label: "Analyses", icon: Activity },
];
const filters = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "completed", label: "Completed" },
  { id: "issues", label: "Needs attention" },
  { id: "cancelled", label: "Cancelled" },
];

export default function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);
  const [token, setToken] = useState("");
  const [config, setConfig] = useState<Config | null>(null);
  const [view, setView] = useState<View>("workspace");
  const [runs, setRuns] = useState<Run[]>([]);
  const [listing, setListing] = useState<Listing | null>(null);
  const [path, setPath] = useState("");
  const [selected, setSelected] = useState<Map<string, Entry>>(new Map());
  const [search, setSearch] = useState("");
  const [explorerMode, setExplorerMode] = useState<ExplorerMode>("samples");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState("");
  const [multiqc, setMultiqc] = useState<MultiQCSummary>();
  const [multiqcDirectory, setMultiqcDirectory] = useState("");
  const [samples, setSamples] = useState<Sample[]>([]);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [detailTab, setDetailTab] = useState<DetailTab>("overview");
  const [logs, setLogs] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [name, setName] = useState("");
  const [mode, setMode] = useState<Run["mode"]>("both");
  const [threads, setThreads] = useState(1);
  const [jobFilter, setJobFilter] = useState("all");
  const [analysisSearch, setAnalysisSearch] = useState("");
  const [cancellingId, setCancellingId] = useState("");
  const [updates, setUpdates] = useState<"connecting" | "live" | "polling">(
    "connecting",
  );
  const currentRun = runs.find((run) => run.id === runId);
  const primaryView =
    view === "analysis" ? "analyses" : view === "new" ? "workspace" : view;
  const open = (next: View) => {
    setView(next);
    setError("");
  };
  const fail = useCallback((err: unknown) => {
    if (err instanceof AuthError) {
      setAuthenticated(false);
      setConfig(null);
      setRuns([]);
      setSamples([]);
      setSelected(new Map());
      setListing(null);
      setRunId("");
      setView("workspace");
    }
    setError(
      err instanceof Error ? err.message : "The request failed. Try again.",
    );
  }, []);
  const browse = useCallback(
    async (next: string, offset = 0) => {
      setBusy(true);
      setError("");
      try {
        const result = await api<Listing>(
          `api/files?path=${encodeURIComponent(next)}&offset=${offset}`,
        );
        setListing((previous) =>
          offset && previous?.path === result.path
            ? { ...result, entries: [...previous.entries, ...result.entries] }
            : result,
        );
        setPath(result.path);
        if (!offset) setSearch("");
      } catch (err) {
        fail(err);
      } finally {
        setBusy(false);
      }
    },
    [fail],
  );
  const load = useCallback(async () => {
    const [settings, analyses] = await Promise.all([
      api<Config>("api/config"),
      api<Run[]>("api/runs"),
    ]);
    setConfig(settings);
    setRuns(analyses);
    setAuthenticated(true);
    await browse(settings.roots[0]);
  }, [browse]);
  useEffect(() => {
    let cancelled = false;
    async function initialize() {
      const hash = new URLSearchParams(window.location.hash.slice(1));
      const credential = hash.get("token");
      if (credential)
        history.replaceState(
          null,
          "",
          window.location.pathname + window.location.search,
        );
      try {
        if (credential)
          await api("api/session", {
            method: "POST",
            body: JSON.stringify({ token: credential }),
          });
        if (!cancelled) await load();
      } catch (err) {
        if (!(err instanceof AuthError) && !cancelled) fail(err);
      } finally {
        if (!cancelled) setChecking(false);
      }
    }
    void initialize();
    return () => {
      cancelled = true;
    };
  }, [load, fail]);
  useEffect(() => {
    if (!authenticated) return;
    setUpdates("connecting");
    const source = new EventSource(url("api/events"));
    source.addEventListener("runs", (event) =>
      setRuns(JSON.parse((event as MessageEvent).data) as Run[]),
    );
    let fallback: ReturnType<typeof setInterval> | undefined;
    source.onerror = () => {
      setUpdates("polling");
      if (!fallback)
        fallback = setInterval(
          () => void api<Run[]>("api/runs").then(setRuns).catch(fail),
          5000,
        );
    };
    source.onopen = () => {
      setUpdates("live");
      if (fallback) {
        clearInterval(fallback);
        fallback = undefined;
      }
    };
    return () => {
      source.close();
      if (fallback) clearInterval(fallback);
    };
  }, [authenticated, fail]);
  useEffect(() => {
    if (!authenticated || !runId || view !== "analysis") return;
    let cancelled = false;
    setMetricsLoading(true);
    void api<{ samples: Sample[]; multiqc?: MultiQCSummary }>(
      `api/runs/${runId}/metrics`,
    )
      .then((result) => {
        if (!cancelled) {
          setSamples(result.samples);
          setMultiqc(result.multiqc);
        }
      })
      .catch((err) => {
        if (!cancelled) fail(err);
      })
      .finally(() => {
        if (!cancelled) setMetricsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authenticated, runId, view, currentRun?.updated_at, fail]);
  useEffect(() => {
    if (
      !authenticated ||
      !currentRun ||
      view !== "analysis" ||
      detailTab !== "overview"
    )
      return;
    let cancelled = false;
    let cursor = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setLogs("");
    setLogsLoading(true);
    const run = currentRun;
    const fetchLog = async () => {
      try {
        let more = true;
        while (more && !cancelled) {
          const result = await api<{
            text: string;
            offset: number;
            size: number;
          }>(`api/runs/${run.id}/logs?offset=${cursor}`);
          if (cancelled) return;
          more = result.offset > cursor && result.offset < result.size;
          cursor = result.offset;
          setLogs((previous) => (previous + result.text).slice(-250000));
        }
        if (!cancelled && active(run))
          timer = setTimeout(() => void fetchLog(), 1500);
      } catch (err) {
        if (!cancelled) fail(err);
      } finally {
        if (!cancelled) setLogsLoading(false);
      }
    };
    void fetchLog();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [authenticated, runId, view, detailTab, currentRun?.state, fail]);
  useEffect(() => {
    if (notice) {
      const timeout = setTimeout(() => setNotice(""), 5000);
      return () => clearTimeout(timeout);
    }
  }, [notice]);
  useEffect(() => {
    if (authenticated) document.getElementById("page-title")?.focus();
  }, [authenticated, view, runId]);
  const pairCount = useMemo(
    () =>
      new Set(
        [...selected.values()]
          .filter(
            (entry) => entry.paired && entry.mate && selected.has(entry.mate),
          )
          .map((entry) => entry.pair_key),
      ).size,
    [selected],
  );
  const toggle = (entry: Entry) =>
    setSelected((previous) => {
      const next = new Map(previous);
      if (next.has(entry.path)) next.delete(entry.path);
      else next.set(entry.path, entry);
      return next;
    });
  const select = async (paths: string[], checked: boolean) => {
    setError("");
    if (!checked) {
      setSelected((previous) => {
        const next = new Map(previous);
        paths.forEach((path) => next.delete(path));
        return next;
      });
      return;
    }
    if (new Set([...selected.keys(), ...paths]).size > 500) {
      setError("Select up to 500 input files per analysis.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const entries = await resolveEntries(
        paths,
        [...selected.values(), ...(listing?.entries || [])],
        (folder, offset) =>
          api<Listing>(
            `api/files?path=${encodeURIComponent(folder)}&offset=${offset}`,
          ),
      );
      setSelected((previous) => {
        const next = new Map(previous);
        entries.forEach((entry) => next.set(entry.path, entry));
        return next;
      });
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };
  const newAnalysis = () => {
    if (
      selected.size &&
      [...selected.values()].every((entry) => entry.kind === "fastqc")
    )
      setMode("multiqc");
    else if (mode === "multiqc") setMode("both");
    open("new");
  };
  const showRun = (run: Run) => {
    setRunId(run.id);
    setSamples([]);
    setMultiqc(undefined);
    setLogs("");
    setLogsLoading(true);
    setMetricsLoading(true);
    setDetailTab("overview");
    open("analysis");
  };
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const run = await api<Run>("api/runs", {
        method: "POST",
        body: JSON.stringify({
          name,
          mode,
          paths:
            mode === "multiqc" && multiqcDirectory.trim()
              ? [multiqcDirectory.trim()]
              : [...selected.values()]
                  .filter((entry) =>
                    mode === "multiqc"
                      ? entry.kind === "fastqc"
                      : entry.kind === "fastq",
                  )
                  .map((entry) => entry.path),
          threads,
        }),
      });
      setRuns((previous) =>
        previous.some((entry) => entry.id === run.id)
          ? previous
          : [run, ...previous],
      );
      showRun(run);
      setNotice("Analysis queued. You can continue browsing files.");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };
  const aggregate = async (id: string) => {
    setBusy(true);
    setError("");
    try {
      const run = await api<Run>(`api/runs/${id}/multiqc`, { method: "POST" });
      setRuns((previous) => [
        run,
        ...previous.filter((item) => item.id !== run.id),
      ]);
      showRun(run);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };
  const cancel = async (id: string) => {
    setCancellingId(id);
    try {
      const result = await api<Run>(`api/runs/${id}/cancel`, {
        method: "POST",
      });
      setRuns((previous) =>
        previous.map((run) => (run.id === id ? result : run)),
      );
      setNotice("Analysis cancelled. Available outputs have been kept.");
    } catch (err) {
      fail(err);
    } finally {
      setCancellingId("");
    }
  };
  const reselect = async (run: Run) => {
    setBusy(true);
    setError("");
    try {
      const entries = await resolveEntries(run.inputs, [], (folder, offset) =>
        api<Listing>(
          `api/files?path=${encodeURIComponent(folder)}&offset=${offset}`,
        ),
      );
      setSelected(new Map(entries.map((entry) => [entry.path, entry])));
      setName(`${run.name} · rerun`);
      setMode(run.mode);
      setThreads(Math.min(run.threads, config?.max_threads || 1));
      open("new");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };
  const filteredRuns = runs.filter((run) => {
    const matchesState =
      jobFilter === "all" ||
      (jobFilter === "active" && active(run)) ||
      (jobFilter === "completed" && run.state === "completed") ||
      (jobFilter === "issues" &&
        ["partial", "failed", "interrupted"].includes(run.state)) ||
      (jobFilter === "cancelled" && run.state === "cancelled");
    return (
      matchesState &&
      `${run.name} ${run.id}`
        .toLocaleLowerCase()
        .includes(analysisSearch.trim().toLocaleLowerCase())
    );
  });
  if (checking)
    return (
      <div className="auth-screen">
        <Dna size={38} />
        <h1>QualiDock</h1>
        <LoaderCircle className="spin" size={22} />
      </div>
    );
  if (!authenticated)
    return (
      <div className="auth-screen">
        <div className="auth-panel">
          <div className="brand auth-brand">
            <span className="brand-mark">
              <Dna size={25} />
            </span>
            <span>
              QualiDock<small>SEQUENCING QC WORKSPACE</small>
            </span>
          </div>
          <div className="auth-art">
            <Dna strokeWidth={0.6} size={135} />
          </div>
          <div className="eyebrow">YOUR LAB. YOUR WORKSPACE.</div>
          <h1>Connect to your session</h1>
          <p>
            Enter the session token from your server or open the connection link
            in Open OnDemand.
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                await api("api/session", {
                  method: "POST",
                  body: JSON.stringify({ token }),
                });
                await load();
                setToken("");
              } catch (err) {
                fail(err);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label htmlFor="token">Session token</label>
            <input
              id="token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste your session token"
              required
            />
            <button className="button primary" disabled={busy}>
              {busy ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                <ArrowRight size={16} />
              )}
              Open workspace
            </button>
          </form>
          {error && (
            <div role="alert" className="error">
              {error}
            </div>
          )}
          <div className="auth-footer">
            <ShieldCheck size={15} /> Files stay on your server. No uploads
            required.
          </div>
        </div>
        <span className="auth-version">QualiDock / v0.1 development</span>
      </div>
    );

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <Dna size={25} />
          </span>
          <span>
            QualiDock<small>SEQUENCING QC</small>
          </span>
        </div>
        <nav aria-label="Main navigation">
          {nav.map((item) => (
            <button
              key={item.id}
              aria-label={item.label}
              aria-current={primaryView === item.id ? "page" : undefined}
              className={`nav-item ${primaryView === item.id ? "selected" : ""}`}
              onClick={() => open(item.id)}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <footer className="sidebar-bottom">
          <section className="session-info" aria-label="Session resources">
            <strong>Session resources</strong>
            <span>
              {config?.cpus} CPU ·{" "}
              {((config?.memory_mb || 0) / 1024).toFixed(1)} GB memory
            </span>
            <small
              title={Object.values(config?.tool_details || {})
                .map((tool) => tool.error)
                .filter(Boolean)
                .join("\n")}
            >
              FastQC{" "}
              {config?.tool_details?.fastqc.version ||
                (config?.tools.fastqc ? "available" : "unavailable")}
              <br />
              MultiQC{" "}
              {config?.tool_details?.multiqc.version ||
                (config?.tools.multiqc ? "available" : "unavailable")}
            </small>
            <small className="connection-status">
              {updates === "live"
                ? "Live updates connected"
                : updates === "polling"
                  ? "Updates polling every 5s"
                  : "Connecting to updates…"}
            </small>
          </section>
          <button
            className="sign-out"
            onClick={async () => {
              try {
                await api("api/session", { method: "DELETE" });
                setAuthenticated(false);
                setConfig(null);
                setSelected(new Map());
                setSamples([]);
                setRuns([]);
                setRunId("");
                setListing(null);
                setView("workspace");
              } catch (err) {
                fail(err);
              }
            }}
          >
            <LogOut size={15} />
            Sign out
          </button>
        </footer>
      </aside>
      <div className="main-shell">
        <main id="main-content" tabIndex={-1}>
          <header className="page-heading">
            <div>
              {view === "new" ? (
                <button
                  className="back-link text-button"
                  onClick={() => open("workspace")}
                >
                  <ArrowLeft size={14} />
                  Workspace
                </button>
              ) : view === "analysis" ? (
                <button
                  className="back-link text-button"
                  onClick={() => open("analyses")}
                >
                  <ArrowLeft size={14} />
                  Analyses
                </button>
              ) : null}
              <h1 id="page-title" tabIndex={-1}>
                {view === "workspace"
                  ? "Workspace"
                  : view === "analyses"
                    ? "Analyses"
                    : view === "new"
                      ? "New analysis"
                      : currentRun?.name || "Analysis"}
              </h1>
              <p>
                {view === "workspace"
                  ? "Browse FASTQ files, check sample pairs, and start a QC analysis."
                  : view === "analyses"
                    ? "Manage QC runs and open their logs, metrics, and reports."
                    : view === "new"
                      ? "Configure FastQC and MultiQC using your selected server files."
                      : currentRun
                        ? `Created ${date(currentRun.created_at)}`
                        : "Choose an analysis to inspect its results."}
              </p>
            </div>
            {view === "workspace" && (
              <button
                className="button primary"
                onClick={newAnalysis}
                disabled={busy}
              >
                <Plus size={16} />
                New analysis
              </button>
            )}
          </header>
          {error && (
            <div className="error error-banner" role="alert">
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={15} />
              </button>
            </div>
          )}
          {view === "workspace" && (
            <>
              <FileExplorer
                listing={listing}
                roots={config?.roots || []}
                path={path}
                search={search}
                selected={selected}
                mode={explorerMode}
                busy={busy}
                setPath={setPath}
                setSearch={setSearch}
                setMode={setExplorerMode}
                browse={browse}
                select={select}
              />
              {selected.size > 0 && (
                <div className="selection-bar" aria-label="Selected inputs">
                  <strong aria-live="polite">
                    {selected.size} files selected
                  </strong>
                  <span>{pairCount} complete read pairs</span>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => setSelected(new Map())}
                  >
                    Clear selection
                  </button>
                  <button
                    className="button primary small"
                    disabled={busy}
                    onClick={newAnalysis}
                  >
                    Configure analysis
                    <ArrowRight size={14} />
                  </button>
                </div>
              )}
            </>
          )}
          {view === "new" && (
            <NewAnalysisForm
              config={config}
              multiqcDirectory={multiqcDirectory}
              setMultiqcDirectory={setMultiqcDirectory}
              selected={selected}
              busy={busy}
              name={name}
              mode={mode}
              threads={threads}
              pairCount={pairCount}
              setName={setName}
              setMode={setMode}
              setThreads={setThreads}
              toggle={toggle}
              submit={submit}
            />
          )}
          {view === "analyses" && (
            <section aria-label="Analysis jobs">
              {runs.length > 0 && (
                <div className="jobs-toolbar">
                  <div
                    className="filter-tabs"
                    role="group"
                    aria-label="Filter analysis states"
                  >
                    {filters.map((filter) => (
                      <button
                        key={filter.id}
                        className={jobFilter === filter.id ? "active" : ""}
                        aria-pressed={jobFilter === filter.id}
                        onClick={() => setJobFilter(filter.id)}
                      >
                        {filter.label}
                      </button>
                    ))}
                  </div>
                  <label className="search-box">
                    <Search size={15} />
                    <input
                      aria-label="Search analyses"
                      placeholder="Search analyses…"
                      value={analysisSearch}
                      onChange={(event) =>
                        setAnalysisSearch(event.target.value)
                      }
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
                        <th>
                          <span className="sr-only">Actions</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRuns.map((run) => (
                        <tr key={run.id}>
                          <td>
                            <button
                              className="job-name"
                              onClick={() => showRun(run)}
                            >
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
                          <td>{run.inputs.length}</td>
                          <td className="subtle">{date(run.created_at)}</td>
                          <td>
                            <div className="row-actions">
                              {active(run) && (
                                <button
                                  className="text-button danger"
                                  disabled={!!cancellingId}
                                  onClick={() => void cancel(run.id)}
                                  aria-label={`Cancel ${run.name}`}
                                >
                                  <Square size={12} />
                                  {cancellingId === run.id
                                    ? "Cancelling…"
                                    : "Cancel"}
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
                    runs.length ? "No matching analyses" : "No analyses yet"
                  }
                  action={
                    runs.length ? (
                      <button
                        className="button"
                        onClick={() => {
                          setJobFilter("all");
                          setAnalysisSearch("");
                        }}
                      >
                        Clear filters
                      </button>
                    ) : (
                      <button
                        className="button"
                        onClick={() => open("workspace")}
                      >
                        Choose input files
                        <ArrowRight size={14} />
                      </button>
                    )
                  }
                >
                  {runs.length
                    ? "Try another status or analysis name."
                    : "Start from the Workspace to select files and configure a QC run."}
                </Empty>
              )}
            </section>
          )}
          {view === "analysis" &&
            (currentRun ? (
              <AnalysisDetail
                key={currentRun.id}
                currentRun={currentRun}
                samples={samples}
                multiqc={multiqc}
                aggregate={aggregate}
                multiqcAvailable={!!config?.tools.multiqc}
                logs={logs}
                logsLoading={logsLoading}
                metricsLoading={metricsLoading}
                tab={detailTab}
                setTab={setDetailTab}
                busy={busy}
                cancelling={cancellingId === currentRun.id}
                cancel={cancel}
                reselect={reselect}
              />
            ) : (
              <Empty
                icon={Activity}
                title="Analysis not available"
                action={
                  <button className="button" onClick={() => open("analyses")}>
                    Back to analyses
                  </button>
                }
              >
                Refresh the analysis list and select an available run.
              </Empty>
            ))}
        </main>
      </div>
      {notice && (
        <div className="toast" role="status">
          <Check size={16} />
          {notice}
          <button
            aria-label="Dismiss notification"
            onClick={() => setNotice("")}
          >
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
