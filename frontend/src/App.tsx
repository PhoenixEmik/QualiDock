import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Bell,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Dna,
  ExternalLink,
  FileArchive,
  FileBarChart2,
  FileText,
  Files,
  Folder,
  FolderOpen,
  HardDrive,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Play,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings2,
  ShieldCheck,
  Square,
  Terminal,
  X,
} from "lucide-react";
import { api, AuthError, bytes, date, modeLabel, url } from "./api";
import type { Config, Entry, Listing, Run, Sample, View } from "./types";
import QualityChart from "./QualityChart";

const active = (run: Run) => ["queued", "running"].includes(run.state);
const nav = [
  { id: "workspace" as View, label: "Workspace", icon: Files },
  { id: "new" as View, label: "New analysis", icon: Plus },
  { id: "jobs" as View, label: "Analysis jobs", icon: Activity },
  { id: "dashboard" as View, label: "QC dashboard", icon: LayoutDashboard },
  { id: "reports" as View, label: "Reports", icon: FileBarChart2 },
];
function State({ value }: { value: string }) {
  return (
    <span className={`state ${value}`}>
      <span />
      {value}
    </span>
  );
}
function Empty({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: typeof Files;
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={32} strokeWidth={1.3} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);
  const [token, setToken] = useState("");
  const [config, setConfig] = useState<Config | null>(null);
  const [view, setView] = useState<View>("workspace");
  const [tabs, setTabs] = useState<View[]>(["workspace"]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [listing, setListing] = useState<Listing | null>(null);
  const [path, setPath] = useState("");
  const [selected, setSelected] = useState<Map<string, Entry>>(new Map());
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState("");
  const [samples, setSamples] = useState<Sample[]>([]);
  const [sampleId, setSampleId] = useState("");
  const [metric, setMetric] = useState("Per base sequence quality");
  const [logs, setLogs] = useState("");
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"both" | "fastqc" | "multiqc">("both");
  const [threads, setThreads] = useState(1);
  const [jobFilter, setJobFilter] = useState("all");
  const [help, setHelp] = useState(false);
  const [resources, setResources] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const currentRun = runs.find((r) => r.id === runId);
  const currentSample = samples.find((s) => s.id === sampleId) || samples[0];
  const running = runs.filter(active);
  const open = (next: View) => {
    setView(next);
    setTabs((previous) =>
      previous.includes(next) ? previous : [...previous, next],
    );
    setSearch("");
    setError("");
  };
  const fail = useCallback((err: unknown) => {
    if (err instanceof AuthError) {
      setAuthenticated(false);
      setConfig(null);
    }
    setError(
      err instanceof Error ? err.message : "The request failed. Try again.",
    );
  }, []);

  const browse = useCallback(
    async (next: string, offset = 0) => {
      setBusy(true);
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
        setSearch("");
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
    setRunId((previous) => previous || analyses[0]?.id || "");
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
    const source = new EventSource(url("api/events"));
    source.addEventListener("runs", (event) => {
      const next = JSON.parse((event as MessageEvent).data) as Run[];
      setRuns(next);
      setRunId((previous) => previous || next[0]?.id || "");
    });
    let fallback: ReturnType<typeof setInterval> | undefined;
    source.onerror = () => {
      if (!fallback)
        fallback = setInterval(() => {
          void api<Run[]>("api/runs").then(setRuns).catch(fail);
        }, 5000);
    };
    source.onopen = () => {
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
    if (!authenticated || !runId) return;
    let cancelled = false;
    void api<{ samples: Sample[] }>(`api/runs/${runId}/metrics`)
      .then((result) => {
        if (!cancelled) {
          setSamples(result.samples);
          setSampleId((previous) =>
            result.samples.some((s) => s.id === previous)
              ? previous
              : result.samples[0]?.id || "",
          );
        }
      })
      .catch(fail);
    return () => {
      cancelled = true;
    };
  }, [authenticated, runId, currentRun?.updated_at, fail]);
  useEffect(() => {
    if (!authenticated || !runId || view !== "jobs") return;
    let cancelled = false;
    let cursor = 0;
    setLogs("");
    const fetchLog = async () => {
      try {
        const result = await api<{
          text: string;
          offset: number;
          size: number;
        }>(`api/runs/${runId}/logs?offset=${cursor}`);
        if (!cancelled) {
          cursor = result.offset;
          setLogs((previous) => (previous + result.text).slice(-250000));
        }
      } catch (err) {
        if (!cancelled) fail(err);
      }
    };
    void fetchLog();
    const timer = setInterval(() => void fetchLog(), 1500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [authenticated, runId, view, fail]);
  useEffect(() => {
    if (notice) {
      const timeout = setTimeout(() => setNotice(""), 5000);
      return () => clearTimeout(timeout);
    }
  }, [notice]);

  const toggle = (entry: Entry) =>
    setSelected((previous) => {
      const next = new Map(previous);
      if (next.has(entry.path)) next.delete(entry.path);
      else next.set(entry.path, entry);
      return next;
    });
  const pairCount = useMemo(
    () =>
      new Set(
        [...selected.values()]
          .filter((e) => e.paired && e.mate && selected.has(e.mate))
          .map((e) => e.pair_key),
      ).size,
    [selected],
  );
  const filtered =
    listing?.entries.filter((e) =>
      e.name.toLowerCase().includes(search.toLowerCase()),
    ) || [];
  const suitable = (entry: Entry) =>
    mode === "multiqc" ? entry.kind === "fastqc" : entry.kind === "fastq";
  const configuredPaths = [...selected.values()].filter(suitable);
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const run = await api<Run>("api/runs", {
        method: "POST",
        body: JSON.stringify({
          name,
          mode,
          paths: configuredPaths.map((e) => e.path),
          threads,
        }),
      });
      setRuns((previous) => [run, ...previous]);
      setRunId(run.id);
      setSamples([]);
      open("jobs");
      setNotice("Analysis queued. You can continue browsing your workspace.");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };
  const cancel = async (id: string) => {
    try {
      const result = await api<Run>(`api/runs/${id}/cancel`, {
        method: "POST",
      });
      setRuns((previous) => previous.map((r) => (r.id === id ? result : r)));
      setNotice("Analysis cancelled. Available outputs have been kept.");
    } catch (err) {
      fail(err);
    }
  };
  const reselect = async (run: Run) => {
    setBusy(true);
    try {
      const entries: Entry[] = [];
      for (const input of run.inputs) {
        const folder = input.slice(0, input.lastIndexOf("/"));
        const result = await api<Listing>(
          `api/files?path=${encodeURIComponent(folder)}`,
        );
        const entry = result.entries.find((e) => e.path === input);
        if (!entry)
          throw new Error(
            "An original input is no longer available. Select files in the workspace.",
          );
        entries.push(entry);
      }
      setSelected(new Map(entries.map((e) => [e.path, e])));
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
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <Dna size={25} />
          </span>
          <span>
            QualiDock<small>SEQUENCING QC</small>
          </span>
        </div>
        <div className="workspace-switch">
          <span className="workspace-avatar">Q</span>
          <span>
            My workspace<small>Personal session</small>
          </span>
          <ChevronDown size={14} />
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {nav.map((item) => (
            <button
              key={item.id}
              aria-label={item.label}
              className={view === item.id ? "nav-item selected" : "nav-item"}
              onClick={() => open(item.id)}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
              {item.id === "jobs" && running.length > 0 && (
                <span className="nav-count">{running.length}</span>
              )}
              {view === item.id && <span className="nav-active" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-divider" />
        <div className="nav-caption">CONNECTED STORAGE</div>
        <div className="root-links">
          {config?.roots.map((root, index) => (
            <button
              key={root}
              title={root}
              onClick={() => {
                open("workspace");
                void browse(root);
              }}
            >
              <HardDrive size={15} />
              <span>
                {root.split("/").filter(Boolean).pop() || root}
                <small>Root {index + 1}</small>
              </span>
            </button>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="session-info">
            <span className="live-dot" />
            <span>
              Session connected
              <small>
                {config?.cpus} CPU ·{" "}
                {((config?.memory_mb || 0) / 1024).toFixed(1)} GB memory
              </small>
            </span>
            <Server size={16} />
          </div>
          <button className="sidebar-link" onClick={() => setHelp(true)}>
            <BookOpen size={16} />
            Getting started
            <ExternalLink size={13} />
          </button>
          <div className="user-row">
            <span className="user-avatar">ME</span>
            <span>
              Local researcher<small>Single-user workspace</small>
            </span>
            <button
              aria-label="Sign out"
              title="Sign out"
              onClick={async () => {
                try {
                  await api("api/session", { method: "DELETE" });
                  setAuthenticated(false);
                  setConfig(null);
                  setSelected(new Map());
                  setSamples([]);
                } catch (err) {
                  fail(err);
                }
              }}
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            My workspace
            <ChevronRight size={13} />
            <strong>{nav.find((n) => n.id === view)?.label}</strong>
          </div>
          <div className="top-actions">
            <span className="private-label">
              <ShieldCheck size={13} />
              Private session
            </span>
            <button
              aria-label="Session resources"
              title="Session resources"
              onClick={() => setResources(true)}
            >
              <Settings2 size={17} />
            </button>
            <button
              aria-label="Notifications"
              title="Recent activity"
              className="notification-button"
              onClick={() => setNotifications(true)}
            >
              <Bell size={17} />
              {running.length > 0 && <i />}
            </button>
            <span className="top-avatar">ME</span>
          </div>
        </header>
        <div className="tabbar" role="tablist" aria-label="Workspace tabs">
          {tabs.map((tab) => {
            const item = nav.find((n) => n.id === tab)!;
            return (
              <div
                key={tab}
                className={`workspace-tab ${view === tab ? "active" : ""}`}
              >
                <button
                  role="tab"
                  aria-selected={view === tab}
                  onClick={() => open(tab)}
                >
                  <item.icon size={14} />
                  {item.label}
                </button>
                {tab !== "workspace" && (
                  <button
                    className="close-tab"
                    aria-label={`Close ${item.label}`}
                    onClick={() => {
                      setTabs((previous) => previous.filter((t) => t !== tab));
                      if (view === tab) setView("workspace");
                    }}
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            );
          })}
          <button
            className="add-tab"
            aria-label="Open new analysis tab"
            onClick={() => open("new")}
          >
            <Plus size={16} />
          </button>
          <span className="tabbar-end">
            LOCAL EXECUTOR
            <button
              aria-label="About local execution"
              onClick={() => setHelp(true)}
            >
              <CircleHelp size={13} />
            </button>
          </span>
        </div>
        <main>
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
              <div className="page-heading">
                <div>
                  <div className="eyebrow">SEQUENCING WORKSPACE</div>
                  <h1>
                    Your next analysis starts here
                    <span className="heading-dot">.</span>
                  </h1>
                  <p>
                    Browse your files, check read pairs, and get a clear view of
                    sequence quality.
                  </p>
                </div>
                <button className="button primary" onClick={() => open("new")}>
                  <Plus size={16} />
                  New analysis
                </button>
              </div>
              <div className="workspace-overview">
                <div>
                  <span className="overview-label">ANALYSES</span>
                  <strong>
                    {runs.length.toString().padStart(2, "0")}
                    <small>total runs</small>
                  </strong>
                  <span>
                    {runs.filter((r) => r.state === "completed").length}{" "}
                    completed successfully
                  </span>
                </div>
                <div>
                  <span className="overview-label">ACTIVE JOBS</span>
                  <strong>
                    {running.length.toString().padStart(2, "0")}
                    <small>in progress</small>
                  </strong>
                  <span>
                    {running.length
                      ? "Processing on this host"
                      : "Ready when you are"}
                  </span>
                </div>
                <div>
                  <span className="overview-label">WORKSPACE STORAGE</span>
                  <strong>
                    {config?.roots.length.toString().padStart(2, "0")}
                    <small>connected roots</small>
                  </strong>
                  <span>
                    <ShieldCheck size={12} />
                    Original files stay unchanged
                  </span>
                </div>
                <div className="overview-art" aria-hidden="true">
                  <Dna size={98} strokeWidth={0.8} />
                  <span>
                    FROM READS
                    <br />
                    TO INSIGHT
                  </span>
                </div>
              </div>
              <section className="file-section">
                <div className="section-heading">
                  <div>
                    <FolderOpen size={19} />
                    <h2>File explorer</h2>
                    <span className="subtle">{listing?.total || 0} items</span>
                  </div>
                  <div>
                    <label className="search-box">
                      <Search size={15} />
                      <input
                        aria-label="Search files"
                        placeholder="Find a file…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                    <button
                      className="icon-button"
                      aria-label="Refresh files"
                      onClick={() => void browse(path)}
                      disabled={busy}
                    >
                      <RefreshCw size={16} className={busy ? "spin" : ""} />
                    </button>
                  </div>
                </div>
                <div className="pathbar">
                  <button
                    className="icon-button"
                    disabled={!listing?.parent || busy}
                    aria-label="Parent directory"
                    onClick={() =>
                      listing?.parent && void browse(listing.parent)
                    }
                  >
                    <ArrowLeft size={15} />
                  </button>
                  <HardDrive size={14} />
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void browse(path);
                    }}
                  >
                    <input
                      aria-label="Directory path"
                      value={path}
                      onChange={(e) => setPath(e.target.value)}
                    />
                  </form>
                  <span>READ ONLY</span>
                </div>
                <div className="table-scroll">
                  <table className="file-table">
                    <thead>
                      <tr>
                        <th className="check-cell">
                          <input
                            type="checkbox"
                            aria-label="Select all visible input files"
                            checked={
                              filtered.filter(
                                (e) =>
                                  e.kind === "fastq" || e.kind === "fastqc",
                              ).length > 0 &&
                              filtered
                                .filter(
                                  (e) =>
                                    e.kind === "fastq" || e.kind === "fastqc",
                                )
                                .every((e) => selected.has(e.path))
                            }
                            onChange={(e) =>
                              setSelected((previous) => {
                                const next = new Map(previous);
                                filtered
                                  .filter(
                                    (file) =>
                                      file.kind === "fastq" ||
                                      file.kind === "fastqc",
                                  )
                                  .forEach((file) =>
                                    e.target.checked
                                      ? next.set(file.path, file)
                                      : next.delete(file.path),
                                  );
                                return next;
                              })
                            }
                          />
                        </th>
                        <th>Name</th>
                        <th>File type</th>
                        <th>Read pairing</th>
                        <th>Size</th>
                        <th>Modified</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((entry) => (
                        <tr
                          key={entry.path}
                          className={
                            selected.has(entry.path) ? "row-selected" : ""
                          }
                        >
                          <td className="check-cell">
                            {(entry.kind === "fastq" ||
                              entry.kind === "fastqc") && (
                              <input
                                type="checkbox"
                                aria-label={`Select ${entry.name}`}
                                checked={selected.has(entry.path)}
                                onChange={() => toggle(entry)}
                              />
                            )}
                          </td>
                          <td>
                            <button
                              className={`file-name ${entry.kind}`}
                              onClick={() =>
                                entry.kind === "directory"
                                  ? void browse(entry.path)
                                  : entry.kind === "fastq" ||
                                      entry.kind === "fastqc"
                                    ? toggle(entry)
                                    : setNotice(
                                        "This file type is not an analysis input.",
                                      )
                              }
                              title={entry.path}
                            >
                              {entry.kind === "directory" ? (
                                <Folder size={19} fill="#edf1e7" />
                              ) : entry.kind === "fastq" ? (
                                <FileText size={18} />
                              ) : (
                                <FileArchive size={18} />
                              )}
                              <span>{entry.name}</span>
                            </button>
                          </td>
                          <td>
                            <span className={`filetype ${entry.kind}`}>
                              {entry.kind === "directory"
                                ? "Folder"
                                : entry.kind === "fastq"
                                  ? entry.name.endsWith(".gz")
                                    ? "FASTQ.GZ"
                                    : "FASTQ"
                                  : entry.kind === "fastqc"
                                    ? "FastQC report"
                                    : "File"}
                            </span>
                          </td>
                          <td>
                            {entry.paired ? (
                              <span className="pair-label">
                                <span>{entry.read}</span>Paired-end
                              </span>
                            ) : entry.read ? (
                              <span className="orphan-label">
                                {entry.read} · mate missing
                              </span>
                            ) : entry.kind === "fastq" ? (
                              <span className="subtle">Single-end</span>
                            ) : (
                              <span className="subtle">—</span>
                            )}
                          </td>
                          <td className="mono">{bytes(entry.size)}</td>
                          <td className="subtle">
                            {date(
                              new Date(entry.modified * 1000).toISOString(),
                            )}
                          </td>
                          <td>
                            {entry.kind === "directory" && (
                              <ChevronRight size={14} className="subtle" />
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!filtered.length && (
                  <Empty
                    icon={FolderOpen}
                    title={
                      search ? "No matching files" : "This directory is empty"
                    }
                  >
                    {search
                      ? "Try a different filename."
                      : "Choose another connected root or enter a directory path above."}
                  </Empty>
                )}
                <div className="file-footer">
                  <span>
                    <ShieldCheck size={13} />
                    Files are accessed directly on the server
                  </span>
                  {listing && listing.entries.length < listing.total ? (
                    <button
                      onClick={() =>
                        void browse(listing.path, listing.entries.length)
                      }
                    >
                      Load more files
                    </button>
                  ) : (
                    <span>
                      {filtered.filter((e) => e.kind === "fastq").length} FASTQ
                      files detected
                    </span>
                  )}
                </div>
              </section>
              {selected.size > 0 && (
                <div className="selection-bar">
                  <span className="selection-check">
                    <Check size={15} />
                  </span>
                  <strong>{selected.size} files selected</strong>
                  <span>{pairCount} complete read pairs</span>
                  <button
                    className="text-button"
                    onClick={() => setSelected(new Map())}
                  >
                    Clear selection
                  </button>
                  <button
                    className="button primary small"
                    onClick={() => {
                      if (
                        [...selected.values()].every((e) => e.kind === "fastqc")
                      )
                        setMode("multiqc");
                      open("new");
                    }}
                  >
                    Configure analysis
                    <ArrowRight size={14} />
                  </button>
                </div>
              )}
              <section className="recent-section">
                <div className="section-heading">
                  <div>
                    <h2>Recent analyses</h2>
                    <span className="subtle">Your workspace history</span>
                  </div>
                  <button className="text-button" onClick={() => open("jobs")}>
                    View all jobs
                    <ArrowRight size={13} />
                  </button>
                </div>
                {runs.length ? (
                  <div className="recent-list">
                    {runs.slice(0, 3).map((run) => (
                      <button
                        key={run.id}
                        onClick={() => {
                          setRunId(run.id);
                          open(active(run) ? "jobs" : "dashboard");
                        }}
                      >
                        <span className="run-icon">
                          <FileBarChart2 size={19} />
                        </span>
                        <span className="recent-title">
                          <strong>{run.name}</strong>
                          <small>
                            {modeLabel(run.mode)} · {run.inputs.length} files
                          </small>
                        </span>
                        <span className="subtle">{date(run.created_at)}</span>
                        <State value={run.state} />
                        <ChevronRight size={15} />
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="first-analysis">
                    <Activity size={22} />
                    <div>
                      <strong>A fresh workspace</strong>
                      <p>
                        Select FASTQ files above to create your first analysis.
                        Finished reports will appear here.
                      </p>
                    </div>
                    <span className="step-label">
                      01 SELECT → 02 ANALYZE → 03 EXPLORE
                    </span>
                  </div>
                )}
              </section>
            </>
          )}
          {view === "new" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">ANALYSIS SETUP</div>
                  <h1>
                    New analysis<span className="heading-dot">.</span>
                  </h1>
                  <p>Configure a QC run using files already on your server.</p>
                </div>
                <button className="button" onClick={() => open("workspace")}>
                  <FolderOpen size={15} />
                  Choose files
                </button>
              </div>
              <div className="setup-layout">
                <div className="setup-main">
                  <section className="form-section">
                    <div className="form-heading">
                      <span>01</span>
                      <h2>Analysis details</h2>
                    </div>
                    <label className="field-label" htmlFor="analysis-name">
                      Analysis name
                    </label>
                    <input
                      id="analysis-name"
                      className="wide-input"
                      placeholder="e.g. RNA-seq · pilot cohort"
                      maxLength={120}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                    <div className="field-label">QC workflow</div>
                    <div className="mode-options">
                      {(["both", "fastqc", "multiqc"] as const).map((value) => (
                        <button
                          key={value}
                          className={`mode-option ${mode === value ? "chosen" : ""}`}
                          onClick={() => setMode(value)}
                        >
                          <span className="radio-dot" />
                          <strong>{modeLabel(value)}</strong>
                          <small>
                            {value === "both"
                              ? "Individual read QC and a combined report"
                              : value === "fastqc"
                                ? "Individual read quality assessment"
                                : "Combine existing FastQC report files"}
                          </small>
                          {mode === value && <Check size={15} />}
                        </button>
                      ))}
                    </div>
                  </section>
                  <section className="form-section">
                    <div className="form-heading">
                      <span>02</span>
                      <h2>Input files</h2>
                      <small>{configuredPaths.length} selected</small>
                    </div>
                    {selected.size ? (
                      <>
                        <div className="selected-files">
                          {[...selected.values()].map((entry) => (
                            <div
                              key={entry.path}
                              className={suitable(entry) ? "" : "incompatible"}
                            >
                              <FileText size={17} />
                              <div>
                                <strong>{entry.name}</strong>
                                <small title={entry.path}>{entry.path}</small>
                              </div>
                              <span className="subtle">
                                {bytes(entry.size)}
                              </span>
                              <button
                                aria-label={`Remove ${entry.name}`}
                                onClick={() => toggle(entry)}
                              >
                                <X size={14} />
                              </button>
                            </div>
                          ))}
                        </div>
                        {configuredPaths.length < selected.size && (
                          <p className="inline-note">
                            {selected.size - configuredPaths.length}{" "}
                            incompatible files will be excluded from this
                            workflow.
                          </p>
                        )}
                        <div className="pair-summary">
                          <Dna size={17} />
                          {mode === "multiqc"
                            ? "Existing FastQC reports will be copied into this run."
                            : `${pairCount} complete read pairs detected. Both reads are analyzed independently.`}
                        </div>
                      </>
                    ) : (
                      <Empty icon={Files} title="Choose your input files">
                        {mode === "multiqc"
                          ? "Select FastQC ZIPs or fastqc_data.txt files in the workspace."
                          : "Select FASTQ files in the workspace. No upload is needed."}
                      </Empty>
                    )}
                  </section>
                  <section className="form-section">
                    <div className="form-heading">
                      <span>03</span>
                      <h2>Execution resources</h2>
                    </div>
                    <div className="resource-field">
                      <div>
                        <label htmlFor="threads">CPU threads</label>
                        <p>Limited to your session’s available resources.</p>
                      </div>
                      <select
                        id="threads"
                        value={threads}
                        onChange={(e) => setThreads(Number(e.target.value))}
                      >
                        {Array.from(
                          { length: config?.max_threads || 1 },
                          (_, i) => (
                            <option key={i + 1} value={i + 1}>
                              {i + 1} {i === 0 ? "thread" : "threads"}
                            </option>
                          ),
                        )}
                      </select>
                    </div>
                    <div className="inline-note">
                      <Server size={14} />
                      Runs locally on this host. Analyses execute one at a time.
                    </div>
                  </section>
                </div>
                <aside className="analysis-summary">
                  <div className="summary-label">RUN SUMMARY</div>
                  <Dna size={46} strokeWidth={1} />
                  <h3>{name || "Untitled analysis"}</h3>
                  <dl>
                    <div>
                      <dt>Workflow</dt>
                      <dd>{modeLabel(mode)}</dd>
                    </div>
                    <div>
                      <dt>Input files</dt>
                      <dd>{configuredPaths.length}</dd>
                    </div>
                    <div>
                      <dt>CPU threads</dt>
                      <dd>{threads}</dd>
                    </div>
                    <div>
                      <dt>Executor</dt>
                      <dd>Local</dd>
                    </div>
                  </dl>
                  {config &&
                    ((!config.tools.fastqc && mode !== "multiqc") ||
                      (!config.tools.multiqc && mode !== "fastqc")) && (
                      <p className="tool-warning">
                        A required QC tool is unavailable on this host.
                        Configure it before starting.
                      </p>
                    )}
                  <button
                    className="button primary"
                    disabled={
                      busy ||
                      !configuredPaths.length ||
                      (!!config &&
                        ((!config.tools.fastqc && mode !== "multiqc") ||
                          (!config.tools.multiqc && mode !== "fastqc")))
                    }
                    onClick={() => void submit()}
                  >
                    {busy ? (
                      <LoaderCircle size={16} className="spin" />
                    ) : (
                      <Play size={15} />
                    )}
                    Run analysis
                  </button>
                  <p>
                    <ShieldCheck size={13} />
                    Your original files stay unchanged.
                  </p>
                </aside>
              </div>
            </>
          )}
          {view === "jobs" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">EXECUTION MONITOR</div>
                  <h1>
                    Analysis jobs<span className="heading-dot">.</span>
                  </h1>
                  <p>
                    Follow progress, inspect logs, and manage your analyses.
                  </p>
                </div>
                <button className="button primary" onClick={() => open("new")}>
                  <Plus size={16} />
                  New analysis
                </button>
              </div>
              <div className="jobs-toolbar">
                <div className="filter-tabs">
                  {["all", "active", "completed", "issues"].map((filter) => (
                    <button
                      key={filter}
                      className={jobFilter === filter ? "active" : ""}
                      onClick={() => setJobFilter(filter)}
                    >
                      {filter === "all"
                        ? "All jobs"
                        : filter === "active"
                          ? "Active"
                          : filter === "completed"
                            ? "Completed"
                            : "Needs attention"}
                    </button>
                  ))}
                </div>
                <span className="subtle">
                  <span className="live-dot" />
                  Live updates
                </span>
              </div>
              {runs.length ? (
                <div className="table-scroll">
                  <table className="jobs-table">
                    <thead>
                      <tr>
                        <th>Analysis</th>
                        <th>Status</th>
                        <th>Workflow</th>
                        <th>Files</th>
                        <th>Created</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {runs
                        .filter(
                          (r) =>
                            jobFilter === "all" ||
                            (jobFilter === "active" && active(r)) ||
                            (jobFilter === "completed" &&
                              r.state === "completed") ||
                            (jobFilter === "issues" &&
                              ["partial", "failed", "interrupted"].includes(
                                r.state,
                              )),
                        )
                        .map((run) => (
                          <tr
                            key={run.id}
                            className={runId === run.id ? "row-selected" : ""}
                          >
                            <td>
                              <button
                                className="job-name"
                                onClick={() => setRunId(run.id)}
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
                              {active(run) ? (
                                <button
                                  className="text-button danger"
                                  onClick={() => void cancel(run.id)}
                                >
                                  <Square size={12} />
                                  Cancel
                                </button>
                              ) : (
                                <button
                                  className="icon-button"
                                  aria-label={`Inspect ${run.name}`}
                                  onClick={() => setRunId(run.id)}
                                >
                                  <ChevronRight size={16} />
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty
                  icon={Activity}
                  title="No analyses yet"
                  action={
                    <button
                      className="button primary"
                      onClick={() => open("workspace")}
                    >
                      Browse files
                      <ArrowRight size={14} />
                    </button>
                  }
                >
                  Create a run to follow its progress here.
                </Empty>
              )}
              {currentRun && (
                <section className="job-detail">
                  <div className="section-heading">
                    <div>
                      <h2>{currentRun.name}</h2>
                      <State value={currentRun.state} />
                    </div>
                    <div>
                      {!active(currentRun) && (
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => void reselect(currentRun)}
                        >
                          <RefreshCw size={14} />
                          Rerun
                        </button>
                      )}
                      <button
                        className="button small"
                        onClick={() => open("dashboard")}
                      >
                        QC dashboard
                        <ArrowRight size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="job-progress">
                    <div>
                      <span>{currentRun.stage}</span>
                      <strong>{currentRun.progress}%</strong>
                    </div>
                    <progress max={100} value={currentRun.progress} />
                  </div>
                  {currentRun.error && (
                    <div className="error" role="alert">
                      {currentRun.error}
                    </div>
                  )}
                  <div className="log-heading">
                    <Terminal size={14} />
                    <strong>Analysis log</strong>
                    <small>stdout + stderr</small>
                    <span className="mono">{currentRun.id.slice(0, 12)}</span>
                  </div>
                  <pre className="log-panel">
                    {logs || "Waiting for process output…"}
                  </pre>
                </section>
              )}
            </>
          )}
          {(view === "dashboard" || view === "reports") && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    {view === "dashboard"
                      ? "QUALITY CONTROL"
                      : "PERSISTENT RESULTS"}
                  </div>
                  <h1>
                    {view === "dashboard" ? "QC dashboard" : "Analysis reports"}
                    <span className="heading-dot">.</span>
                  </h1>
                  <p>
                    {view === "dashboard"
                      ? "Explore read quality and inspect the metrics behind every sample."
                      : "Download the official reports and data from your analyses."}
                  </p>
                </div>
                <select
                  className="run-select"
                  aria-label="Select analysis"
                  value={runId}
                  onChange={(e) => {
                    setRunId(e.target.value);
                    setSamples([]);
                  }}
                >
                  <option value="" disabled>
                    Select an analysis
                  </option>
                  {runs.map((run) => (
                    <option key={run.id} value={run.id}>
                      {run.name} · {run.state}
                    </option>
                  ))}
                </select>
              </div>
              {!currentRun ? (
                <Empty
                  icon={view === "dashboard" ? LayoutDashboard : FileBarChart2}
                  title="Your results belong here"
                  action={
                    <button
                      className="button primary"
                      onClick={() => open("workspace")}
                    >
                      Browse FASTQ files
                      <ArrowRight size={14} />
                    </button>
                  }
                >
                  Run your first analysis to explore QC metrics and download
                  reports.
                </Empty>
              ) : (
                <>
                  <div className="run-context">
                    <span className="run-icon">
                      <FileBarChart2 size={21} />
                    </span>
                    <div>
                      <strong>{currentRun.name}</strong>
                      <span>
                        {modeLabel(currentRun.mode)} ·{" "}
                        {date(currentRun.created_at)}
                      </span>
                    </div>
                    <State value={currentRun.state} />
                    {view === "dashboard" && (
                      <button
                        className="button small"
                        onClick={() => open("reports")}
                      >
                        <ArrowDownToLine size={14} />
                        Download reports
                      </button>
                    )}
                  </div>
                  {view === "dashboard" && (
                    <>
                      {samples.length ? (
                        <>
                          <div className="metrics-strip">
                            <div>
                              <span>READ FILES</span>
                              <strong>
                                {samples.length}
                                <small>analyzed</small>
                              </strong>
                            </div>
                            <div>
                              <span>TOTAL SEQUENCES</span>
                              <strong>
                                {samples.every(
                                  (s) => s.total_sequences !== null,
                                )
                                  ? (
                                      samples.reduce(
                                        (sum, s) =>
                                          sum + (s.total_sequences || 0),
                                        0,
                                      ) / 1e6
                                    ).toFixed(2)
                                  : "—"}
                                <small>
                                  {samples.every(
                                    (s) => s.total_sequences !== null,
                                  )
                                    ? "million"
                                    : ""}
                                </small>
                              </strong>
                            </div>
                            <div>
                              <span>PASSING FILES</span>
                              <strong>
                                {
                                  samples.filter((s) => s.status === "pass")
                                    .length
                                }
                                <small>all modules pass</small>
                              </strong>
                            </div>
                            <div>
                              <span>NEEDS REVIEW</span>
                              <strong>
                                {
                                  samples.filter((s) => s.status !== "pass")
                                    .length
                                }
                                <small>warning or failure</small>
                              </strong>
                            </div>
                          </div>
                          <div className="dashboard-layout">
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
                                  {[
                                    "Per base sequence quality",
                                    "Per sequence quality scores",
                                    "Per base sequence content",
                                    "Per sequence GC content",
                                    "Per base N content",
                                    "Sequence Length Distribution",
                                    "Adapter Content",
                                  ].map((m) => (
                                    <option key={m}>{m}</option>
                                  ))}
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
                                      currentSample.modules.find(
                                        (m) => m.name === metric,
                                      )?.status || "unknown"
                                    }
                                  />
                                )}
                              </div>
                              {currentSample &&
                              currentSample.modules.some(
                                (m) => m.name === metric && m.rows.length,
                              ) ? (
                                <QualityChart
                                  sample={currentSample}
                                  metric={metric}
                                />
                              ) : (
                                <Empty
                                  icon={LayoutDashboard}
                                  title="This metric is unavailable"
                                >
                                  FastQC did not produce this metric for the
                                  selected file.
                                </Empty>
                              )}
                              <div className="chart-note">
                                <CircleHelp size={13} />
                                {metric === "Per base sequence quality"
                                  ? "Boxes show the 25th–75th percentiles. Whiskers show the 10th–90th percentiles. Scroll to zoom."
                                  : "Parsed directly from the official FastQC output. Scroll to zoom."}
                              </div>
                            </section>
                            <aside className="sample-inspector">
                              <div className="summary-label">
                                SAMPLE DETAILS
                              </div>
                              <FileText size={27} strokeWidth={1.3} />
                              <h3>{currentSample?.name}</h3>
                              <dl>
                                <div>
                                  <dt>Sequences</dt>
                                  <dd>
                                    {currentSample?.total_sequences?.toLocaleString() ||
                                      "—"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Read length</dt>
                                  <dd>
                                    {currentSample?.sequence_length || "—"} bp
                                  </dd>
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
                                      ) : (
                                        <X size={13} />
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
                                <span className="subtle">
                                  {samples.length} read files
                                </span>
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
                                        {sample.total_sequences?.toLocaleString() ||
                                          "—"}
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
                            active(currentRun)
                              ? "Waiting for QC results"
                              : "No normalized metrics available"
                          }
                          action={
                            <button
                              className="button"
                              onClick={() => open("jobs")}
                            >
                              View analysis log
                              <ArrowRight size={14} />
                            </button>
                          }
                        >
                          {active(currentRun)
                            ? "The dashboard will update as FastQC results become available."
                            : currentRun.error ||
                              "Check the analysis log for details."}
                        </Empty>
                      )}
                    </>
                  )}
                  {view === "reports" && (
                    <section className="reports-section">
                      <div className="report-intro">
                        <ShieldCheck size={18} />
                        <span>
                          Official HTML reports download as files. Native charts
                          use parsed QC data.
                        </span>
                      </div>
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
                                      {report.path
                                        .split(".")
                                        .pop()
                                        ?.toUpperCase()}
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
                          title="Reports are being prepared"
                        >
                          Downloadable files will appear here when the run
                          stops.
                        </Empty>
                      )}
                      <div className="persistence-note">
                        <HardDrive size={17} />
                        <div>
                          <strong>Saved beyond this session</strong>
                          <p>
                            Each analysis has its own output directory.
                            Restarting QualiDock restores the saved results.
                          </p>
                        </div>
                        <span className="mono">
                          {currentRun.id.slice(0, 12)}
                        </span>
                      </div>
                    </section>
                  )}
                </>
              )}
            </>
          )}
          <footer className="main-footer">
            <span>
              QualiDock<span className="footer-separator">/</span>Sequencing
              quality, in focus.
            </span>
            <span>
              v0.1 development<span className="footer-separator">·</span>
              <button onClick={() => setHelp(true)}>
                Help & documentation
                <ExternalLink size={11} />
              </button>
            </span>
          </footer>
        </main>
        <div className="statusbar">
          <span>
            <span className="live-dot" />
            Connected to local server
          </span>
          <span>
            {running.length} active jobs
            <span className="footer-separator">·</span>
            <ShieldCheck size={11} />
            Read-only source files
          </span>
        </div>
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
      {(help || resources || notifications) && (
        <div
          className="modal-backdrop"
          onClick={() => {
            setHelp(false);
            setResources(false);
            setNotifications(false);
          }}
        >
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={
              help
                ? "Getting started"
                : resources
                  ? "Session resources"
                  : "Recent activity"
            }
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              aria-label="Close dialog"
              onClick={() => {
                setHelp(false);
                setResources(false);
                setNotifications(false);
              }}
            >
              <X size={18} />
            </button>
            {help ? (
              <>
                <BookOpen size={26} />
                <h2>From reads to results</h2>
                <ol className="help-steps">
                  <li>
                    <strong>Select your files</strong>
                    <p>
                      Browse a connected root. Select both R1 and R2 files for
                      paired-end sequencing.
                    </p>
                  </li>
                  <li>
                    <strong>Configure an analysis</strong>
                    <p>
                      Choose FastQC + MultiQC, FastQC only, or combine existing
                      FastQC reports with MultiQC only.
                    </p>
                  </li>
                  <li>
                    <strong>Explore and download</strong>
                    <p>
                      Follow the log in Analysis jobs. Open QC dashboard for
                      sample metrics, and Reports for downloadable originals.
                    </p>
                  </li>
                </ol>
                <p className="inline-note">
                  QC warnings describe the data; they do not mean the execution
                  failed. No trimming or alignment is performed.
                </p>
              </>
            ) : resources ? (
              <>
                <Server size={26} />
                <h2>Session resources</h2>
                <dl>
                  <div>
                    <dt>Allocated CPU capacity</dt>
                    <dd>{config?.cpus} cores</dd>
                  </div>
                  <div>
                    <dt>Memory budget</dt>
                    <dd>{config?.memory_mb} MB</dd>
                  </div>
                  <div>
                    <dt>Maximum analysis threads</dt>
                    <dd>{config?.max_threads}</dd>
                  </div>
                  <div>
                    <dt>FastQC</dt>
                    <dd>
                      {config?.tools.fastqc ? "Available" : "Unavailable"}
                    </dd>
                  </div>
                  <div>
                    <dt>MultiQC</dt>
                    <dd>
                      {config?.tools.multiqc ? "Available" : "Unavailable"}
                    </dd>
                  </div>
                </dl>
                <p className="inline-note">
                  One analysis runs at a time. Tool processes are limited to the
                  session CPU and memory budget.
                </p>
              </>
            ) : (
              <>
                <Bell size={26} />
                <h2>Recent activity</h2>
                {runs.length ? (
                  <div className="activity-list">
                    {runs.slice(0, 5).map((run) => (
                      <button
                        key={run.id}
                        onClick={() => {
                          setRunId(run.id);
                          open("jobs");
                          setNotifications(false);
                        }}
                      >
                        <strong>{run.name}</strong>
                        <State value={run.state} />
                        <small>{date(run.updated_at)}</small>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p>
                    No analyses yet. Start your first run from the workspace.
                  </p>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
