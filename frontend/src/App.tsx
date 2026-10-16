import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Check,
  Dna,
  FileBarChart2,
  Files,
  LoaderCircle,
  LogOut,
  Plus,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, AuthError, date, url } from "./api";
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
  ProcessingOptions,
  DatasetReference,
} from "./types";
import { Empty } from "./Feedback";
import FileExplorer from "./FileExplorer";
import AnalysisDetail from "./AnalysisDetail";
import ResultsList from "./ResultsList";
import NewAnalysisForm from "./NewAnalysisForm";
import ProcessingForm from "./ProcessingForm";
import { defaults, isProcessing, selectedReferences } from "./processing";
import { reconcileConfig } from "./sampleConfig";
import { resolveEntries, listingUrl, type ExplorerMode } from "./explorer";

const active = (run: Pick<Run, "state">) =>
  ["queued", "running"].includes(run.state);
const nav = [
  { id: "workspace" as const, label: "Workspace", icon: Files },
  { id: "new" as const, label: "Quality Control", icon: FileBarChart2 },
  { id: "processing" as const, label: "Read Processing", icon: Dna },
  { id: "analyses" as const, label: "Results", icon: Activity },
];

export default function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);
  const [token, setToken] = useState("");
  const [config, setConfig] = useState<Config | null>(null);
  const [view, setView] = useState<View>("workspace");
  const [currentRun, setCurrentRun] = useState<Run | null>(null);
  const [revision, setRevision] = useState(0);
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
  const [metrics, setMetrics] = useState<{
    samples: Sample[];
    multiqc?: MultiQCSummary;
  }>({ samples: [] });
  const { samples, multiqc } = metrics;
  const [multiqcDirectory, setMultiqcDirectory] = useState("");
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [detailTab, setDetailTab] = useState<DetailTab>("overview");
  const [logs, setLogs] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [name, setName] = useState("");
  const [sampleConfiguration, setSampleConfiguration] =
    useState<SampleConfiguration | null>(null);
  const [outputRoot, setOutputRoot] = useState("");
  const [inputDatasets, setInputDatasets] = useState<DatasetReference[]>([]);
  const [rerunOf, setRerunOf] = useState<string | null>(null);
  const [mode, setMode] = useState<Run["mode"]>("both");
  const [threads, setThreads] = useState(1);
  const [processingOptions, setProcessingOptions] = useState<ProcessingOptions>(
    defaults("fastp"),
  );
  const [cancellingId, setCancellingId] = useState("");
  const [updates, setUpdates] = useState<"connecting" | "live" | "polling">(
    "connecting",
  );
  const primaryView =
    view === "analysis" ? "analyses" : view === "new" ? "new" : view;
  const open = (next: View) => {
    setView(next);
    setError("");
  };
  const resetSession = useCallback(() => {
    setAuthenticated(false);
    setConfig(null);
    setCurrentRun(null);
    setMetrics({ samples: [] });
    setSelected(new Map());
    setInputDatasets([]);
    setSampleConfiguration(null);
    setRerunOf(null);
    setMultiqcDirectory("");
    setOutputRoot("");
    setName("");
    setListing(null);
    listingRef.current = null;
    setRunId("");
    setView("workspace");
  }, []);
  const fail = useCallback(
    (err: unknown) => {
      if (err instanceof AuthError) resetSession();
      setError(
        err instanceof Error ? err.message : "The request failed. Try again.",
      );
    },
    [resetSession],
  );
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
    let source: EventSource;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    let fallback: ReturnType<typeof setInterval> | undefined;
    let stopped = false;
    const connect = () => {
      if (stopped) return;
      source = new EventSource(url("api/events?format=invalidation"));
      source.addEventListener("revision", () =>
        setRevision((value) => value + 1),
      );
      source.onerror = () => {
        // An initial network failure permanently closes EventSource in some
        // browsers. Own the retry timer so polling can always recover to SSE.
        source.close();
        setUpdates("polling");
        if (!fallback)
          fallback = setInterval(() => setRevision((value) => value + 1), 5000);
        if (!reconnect)
          reconnect = setTimeout(() => {
            reconnect = undefined;
            connect();
          }, 5000);
      };
      source.onopen = () => {
        setUpdates("live");
        if (fallback) {
          clearInterval(fallback);
          fallback = undefined;
        }
      };
    };
    connect();
    return () => {
      stopped = true;
      source.close();
      if (fallback) clearInterval(fallback);
      if (reconnect) clearTimeout(reconnect);
    };
  }, [authenticated]);
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
          setMetrics({ samples: result.samples, multiqc: result.multiqc });
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
  const fastqPaths = useMemo(
    () =>
      [...selected.values()]
        .filter((entry) => entry.kind === "fastq")
        .map((entry) => entry.path),
    [selected],
  );
  const currentSampleConfiguration = useMemo(
    () =>
      sampleConfiguration
        ? reconcileConfig(sampleConfiguration, fastqPaths)
        : null,
    [sampleConfiguration, fastqPaths],
  );
  const prepareSamples = async () => {
    const paths = fastqPaths;
    if (!paths.length) {
      setSampleConfiguration(null);
      return true;
    }
    setBusy(true);
    try {
      setSampleConfiguration(
        await api<SampleConfiguration>("api/sample-configuration", {
          method: "POST",
          body: JSON.stringify({
            paths,
            input_datasets: selectedReferences(inputDatasets, new Set(paths)),
          }),
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
      [...selected.values()].every((entry) =>
        ["fastqc", "qcreport"].includes(entry.kind),
      )
    )
      setMode("multiqc");
    else if (mode === "multiqc" || isProcessing(mode)) setMode("both");
    open("new");
  };
  const showRun = (run: Pick<Run, "id">) => {
    setRunId(run.id);
    setCurrentRun("inputs" in run ? (run as Run) : null);
    setDetailLoading(true);
    setMetrics({ samples: [] });
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
      const payload = {
        name,
        mode,
        ...(isProcessing(mode)
          ? { processing_options: processingOptions }
          : {}),
        paths:
          mode === "multiqc" && multiqcDirectory.trim()
            ? [multiqcDirectory.trim()]
            : [...selected.values()]
                .filter((entry) =>
                  mode === "multiqc"
                    ? ["fastqc", "qcreport"].includes(entry.kind)
                    : entry.kind === "fastq",
                )
                .map((entry) => entry.path),
        threads,
        output_root: outputRoot || null,
        rerun_of: rerunOf,
        input_datasets: selectedReferences(
          inputDatasets,
          new Set(selected.keys()),
        ),
        ...(mode !== "multiqc" && currentSampleConfiguration
          ? {
              input_pairing: currentSampleConfiguration.input_pairing,
              sample_groups: currentSampleConfiguration.sample_groups,
            }
          : {}),
      };
      const run = await api<Run>("api/runs", {
        method: "POST",
        body: JSON.stringify(payload),
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
  const applyDraft = (draft: RerunConfiguration) => {
    setInputDatasets(draft.input_datasets || []);
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
    if (isProcessing(draft.mode))
      setProcessingOptions(draft.processing_options || defaults(draft.mode));
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
    open(isProcessing(draft.mode) ? "processing" : "new");
  };
  const reuse = async (run: Run, ids: string[]) => {
    setBusy(true);
    setError("");
    try {
      const draft = await api<RerunConfiguration>(`api/runs/${run.id}/reuse`, {
        method: "POST",
        body: JSON.stringify({ dataset_ids: ids }),
      });
      applyDraft(draft);
      setNotice(
        "Processed FASTQs selected. Choose QC or Read Processing; no files were copied.",
      );
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };
  const reselect = async (run: Pick<Run, "id">) => {
    setBusy(true);
    setError("");
    try {
      const draft = await api<RerunConfiguration>(
        `api/runs/${run.id}/configuration`,
      );
      applyDraft(draft);
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
              onClick={() => {
                if (item.id === "processing") {
                  setRerunOf(null);
                  if (!isProcessing(mode)) {
                    setMode("fastp");
                    setProcessingOptions(defaults("fastp"));
                  }
                  open("processing");
                } else if (item.id === "new") {
                  setMode("both");
                  newAnalysis();
                } else open(item.id);
              }}
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
            <small>
              fastp {config?.tool_details?.fastp?.version || "unavailable"} ·
              SeqKit {config?.tool_details?.seqkit?.version || "unavailable"}
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
                resetSession();
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
                    ? "Results"
                    : view === "processing"
                      ? "Read Processing"
                      : view === "new"
                        ? "New analysis"
                        : currentRun?.name || "Analysis"}
              </h1>
              <p>
                {view === "workspace"
                  ? "Browse FASTQ files, check sample pairs, and choose an operation."
                  : view === "analyses"
                    ? "Manage QC runs and open their logs, metrics, and reports."
                    : view === "processing"
                      ? "Trim, filter, subsample, or inspect selected FASTQs. Source files stay unchanged."
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
            <div className="workspace-files">
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
            </div>
          )}
          {view === "processing" && (
            <ProcessingForm
              config={config}
              selected={selected}
              busy={busy}
              mode={mode}
              setMode={setMode}
              options={processingOptions}
              setOptions={setProcessingOptions}
              name={name}
              setName={setName}
              threads={threads}
              setThreads={setThreads}
              outputRoot={outputRoot}
              setOutputRoot={setOutputRoot}
              samples={
                sampleConfiguration
                  ? reconcileConfig(
                      sampleConfiguration,
                      [...selected.values()]
                        .filter((entry) => entry.kind === "fastq")
                        .map((entry) => entry.path),
                    )
                  : null
              }
              setSamples={setSampleConfiguration}
              prepare={prepareSamples}
              browse={() => {
                open("workspace");
              }}
              submit={submit}
            />
          )}
          {view === "new" && (
            <NewAnalysisForm
              config={config}
              sampleConfiguration={
                sampleConfiguration
                  ? reconcileConfig(
                      sampleConfiguration,
                      [...selected.values()]
                        .filter((entry) => entry.kind === "fastq")
                        .map((entry) => entry.path),
                    )
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
            <ResultsList
              revision={revision}
              showRun={showRun}
              reselect={reselect}
              cancel={cancel}
              cancellingId={cancellingId}
              browse={() => open("workspace")}
              fail={fail}
            />
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
                reuse={reuse}
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
