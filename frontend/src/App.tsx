import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  SampleConfiguration,
  RerunConfiguration,
  RunSummary,
  HistoryPage,
} from "./types";
import { Empty, State } from "./Feedback";
import FileExplorer from "./FileExplorer";
import AnalysisDetail from "./AnalysisDetail";
import NewAnalysisForm from "./NewAnalysisForm";
import { reconcileConfig } from "./sampleConfig";
import { resolveEntries, listingUrl, type ExplorerMode } from "./explorer";

const active = (run: Pick<Run, "state">) =>
  ["queued", "running"].includes(run.state);
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
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [currentRun, setCurrentRun] = useState<Run | null>(null);
  const [revision, setRevision] = useState(0);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyAll, setHistoryAll] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [listing, setListing] = useState<Listing | null>(null);
  const listingRef = useRef<Listing | null>(null);
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
  const [sampleConfiguration, setSampleConfiguration] =
    useState<SampleConfiguration | null>(null);
  const [outputRoot, setOutputRoot] = useState("");
  const [rerunOf, setRerunOf] = useState<string | null>(null);
  const [analysisMode, setAnalysisMode] = useState("all");
  const [analysisSort, setAnalysisSort] = useState("created-desc");
  const [renameId, setRenameId] = useState("");
  const [renameName, setRenameName] = useState("");
  const [mode, setMode] = useState<Run["mode"]>("both");
  const [threads, setThreads] = useState(1);
  const [jobFilter, setJobFilter] = useState("all");
  const [analysisSearch, setAnalysisSearch] = useState("");
  const [cancellingId, setCancellingId] = useState("");
  const [updates, setUpdates] = useState<"connecting" | "live" | "polling">(
    "connecting",
  );
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
      setCurrentRun(null);
      setSamples([]);
      setSelected(new Map());
      setListing(null);
      listingRef.current = null;
      setRunId("");
      setView("workspace");
    }
    setError(
      err instanceof Error ? err.message : "The request failed. Try again.",
    );
  }, []);
  const browse = useCallback(
    async (next: string, offset = 0, refresh = false) => {
      setBusy(true);
      setError("");
      try {
        const previous = listingRef.current;
        const snapshot =
          offset && previous?.path === next ? previous.snapshot : undefined;
        const result = await api<Listing>(
          listingUrl(next, offset, snapshot, refresh),
        );
        const combined =
          offset &&
          previous?.path === result.path &&
          previous.snapshot === result.snapshot
            ? {
                ...result,
                entries: [...previous.entries, ...result.entries],
                sample_groups: {
                  ...previous.sample_groups,
                  ...result.sample_groups,
                },
              }
            : result;
        listingRef.current = combined;
        setListing(combined);
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
    const settings = await api<Config>("api/config");
    setConfig(settings);
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
    const source = new EventSource(url("api/events?format=invalidation"));
    source.addEventListener("revision", () =>
      setRevision((value) => value + 1),
    );
    let fallback: ReturnType<typeof setInterval> | undefined;
    source.onerror = () => {
      setUpdates("polling");
      if (!fallback)
        fallback = setInterval(() => setRevision((value) => value + 1), 5000);
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
    setHistoryOffset(0);
  }, [analysisSearch, jobFilter, analysisMode, analysisSort]);
  useEffect(() => {
    if (!authenticated || view !== "analyses") return;
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
    authenticated,
    view,
    revision,
    historyOffset,
    analysisSearch,
    jobFilter,
    analysisMode,
    analysisSort,
    fail,
  ]);
  useEffect(() => {
    if (!authenticated || !runId || view !== "analysis") return;
    let cancelled = false;
    setDetailLoading(true);
    void api<Run>(`api/runs/${runId}`)
      .then((run) => {
        if (!cancelled) setCurrentRun(run);
      })
      .catch((err) => {
        if (!cancelled) fail(err);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authenticated, runId, view, revision, fail]);
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
        (folder, offset, snapshot) =>
          api<Listing>(listingUrl(folder, offset, snapshot)),
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
  const prepareSamples = async () => {
    const paths = [...selected.values()]
      .filter((entry) => entry.kind === "fastq")
      .map((entry) => entry.path);
    if (!paths.length) {
      setSampleConfiguration(null);
      return true;
    }
    setBusy(true);
    try {
      setSampleConfiguration(
        await api<SampleConfiguration>("api/sample-configuration", {
          method: "POST",
          body: JSON.stringify({ paths }),
        }),
      );
      return true;
    } catch (err) {
      fail(err);
      return false;
    } finally {
      setBusy(false);
    }
  };
  const newAnalysis = async () => {
    setRerunOf(null);
    setSampleConfiguration(null);
    if (!(await prepareSamples())) return;
    if (
      selected.size &&
      [...selected.values()].every((entry) => entry.kind === "fastqc")
    )
      setMode("multiqc");
    else if (mode === "multiqc") setMode("both");
    open("new");
  };
  const showRun = (run: Pick<Run, "id">) => {
    setRunId(run.id);
    setCurrentRun("inputs" in run ? (run as Run) : null);
    setDetailLoading(true);
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
          output_root: outputRoot || null,
          rerun_of: rerunOf,
          ...(mode !== "multiqc" && sampleConfiguration
            ? {
                input_pairing: reconcileConfig(sampleConfiguration, [
                  ...selected.keys(),
                ]).input_pairing,
                sample_groups: reconcileConfig(sampleConfiguration, [
                  ...selected.keys(),
                ]).sample_groups,
              }
            : {}),
        }),
      });
      setRevision((value) => value + 1);
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
      setRevision((value) => value + 1);
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
      if (runId === id) setCurrentRun(result);
      setRevision((value) => value + 1);
      setNotice("Analysis cancelled. Available outputs have been kept.");
    } catch (err) {
      fail(err);
    } finally {
      setCancellingId("");
    }
  };
  const reselect = async (run: Pick<Run, "id">) => {
    setBusy(true);
    setError("");
    try {
      const draft = await api<RerunConfiguration>(
        `api/runs/${run.id}/configuration`,
      );
      setSelected(
        new Map(
          draft.entries
            .filter(
              (entry) =>
                !(draft.mode === "multiqc" && entry.kind === "directory"),
            )
            .map((entry) => [entry.path, entry]),
        ),
      );
      setName(draft.name);
      setMode(draft.mode);
      setMultiqcDirectory(
        draft.mode === "multiqc" &&
          draft.entries.length === 1 &&
          draft.entries[0].kind === "directory"
          ? draft.paths[0]
          : "",
      );
      setThreads(draft.threads);
      setOutputRoot(draft.output_root);
      setRerunOf(draft.rerun_of);
      setSampleConfiguration(
        draft.input_pairing && draft.sample_groups
          ? {
              input_pairing: draft.input_pairing,
              sample_groups: draft.sample_groups,
            }
          : null,
      );
      open("new");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };
  const filteredRuns = runs;
  const rename = async () => {
    setBusy(true);
    setError("");
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
      setRevision((value) => value + 1);
      setRenameId("");
      setNotice("Analysis renamed.");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };
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
                listingRef.current = null;
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
              sampleConfiguration={
                sampleConfiguration
                  ? reconcileConfig(sampleConfiguration, [...selected.keys()])
                  : null
              }
              setSampleConfiguration={setSampleConfiguration}
              prepareSamples={prepareSamples}
              outputRoot={outputRoot}
              setOutputRoot={setOutputRoot}
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
                  {historyAll
                    ? "Try another status or analysis name."
                    : "Start from the Workspace to select files and configure a QC run."}
                </Empty>
              )}
              {historyTotal > 0 && (
                <div
                  className="analytics-actions"
                  aria-label="Analysis history pages"
                >
                  <span>
                    {historyOffset + 1}–
                    {Math.min(historyOffset + 25, historyTotal)} of{" "}
                    {historyTotal} analyses
                  </span>
                  <button
                    className="button small"
                    disabled={historyLoading || !historyOffset}
                    onClick={() =>
                      setHistoryOffset((value) => Math.max(0, value - 25))
                    }
                  >
                    Previous analyses
                  </button>
                  <button
                    className="button small"
                    disabled={
                      historyLoading || historyOffset + 25 >= historyTotal
                    }
                    onClick={() => setHistoryOffset((value) => value + 25)}
                  >
                    Next analyses
                  </button>
                </div>
              )}
            </section>
          )}
          {view === "analysis" &&
            (currentRun ? (
              <AnalysisDetail
                key={currentRun.id}
                currentRun={currentRun}
                refresh={() => setRevision((value) => value + 1)}
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
                title={
                  detailLoading ? "Loading analysis…" : "Analysis not available"
                }
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
