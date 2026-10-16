import { useEffect, useRef, useState } from "react";
import { api, date, modeLabel } from "./api";
import type { DetailTab, Run } from "./types";
import type {
  AnalysisLink,
  CatalogPage,
  EntityKind,
  ProjectAssociation,
  ProjectEntity,
  ProjectEvidence,
} from "./project";
import { entityLabel } from "./project";
import ProjectEntityForm from "./ProjectEntityForm";
import ProjectImport from "./ProjectImport";
import ProjectAssignments from "./ProjectAssignments";

const blankPage = <T,>(): CatalogPage<T> => ({
  items: [],
  offset: 0,
  total: 0,
  limit: 25,
});
function Pages({
  offset,
  total,
  busy,
  setOffset,
  label,
}: {
  offset: number;
  total: number;
  busy: boolean;
  setOffset: (offset: number) => void;
  label: string;
}) {
  return (
    <div className="project-actions" aria-label={`${label} pages`}>
      <span>
        {total
          ? `${offset + 1}–${Math.min(offset + 25, total)} of ${total}`
          : "0 records"}
      </span>
      <button
        className="button small"
        disabled={busy || !offset}
        onClick={() => setOffset(Math.max(0, offset - 25))}
      >
        Previous {label}
      </button>
      <button
        className="button small"
        disabled={busy || offset + 25 >= total}
        onClick={() => setOffset(offset + 25)}
      >
        Next {label}
      </button>
    </div>
  );
}
function EntityList({
  kind,
  path,
  openProject,
  inspect,
  changed,
}: {
  kind: EntityKind;
  path: string;
  openProject?: (id: string) => void;
  inspect?: (entity: ProjectEntity) => void;
  changed?: () => void;
}) {
  const [page, setPage] = useState(blankPage<ProjectEntity>),
    [search, setSearch] = useState(""),
    [offset, setOffset] = useState(0),
    [status, setStatus] = useState("active");
  const [editing, setEditing] = useState<ProjectEntity | "new" | null>(null),
    [refresh, setRefresh] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const title =
    kind === "project"
      ? "project"
      : kind === "sample"
        ? "sample"
        : "sequencing run";
  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    setError("");
    void api<CatalogPage<ProjectEntity>>(
      `${path}?offset=${offset}&limit=25&status=${status}&search=${encodeURIComponent(search)}`,
    )
      .then((result) => {
        if (!cancelled) setPage(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, offset, status, search, refresh]);
  return (
    <section aria-label={`${title} records`}>
      <div className="project-actions">
        <h2>
          {kind === "project"
            ? "Projects"
            : kind === "sample"
              ? "Samples"
              : "Sequencing runs"}
        </h2>
        <button
          className="button primary small"
          onClick={() => setEditing("new")}
        >
          Create {title}
        </button>
        <button
          className="button small"
          onClick={() => setRefresh((n) => n + 1)}
        >
          Refresh {title} list
        </button>
      </div>
      <div className="project-actions">
        <label className="field-label">
          Search {title} metadata
          <input
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label className="field-label">
          {title[0].toUpperCase() + title.slice(1)} status
          <select
            aria-label={`${title[0].toUpperCase() + title.slice(1)} status`}
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="active">Active</option>
            <option value="archived">Archived</option>
            <option value="all">All</option>
          </select>
        </label>
      </div>
      {editing && (
        <ProjectEntityForm
          key={editing === "new" ? "new" : editing.id}
          kind={kind}
          entity={editing === "new" ? undefined : editing}
          cancel={() => setEditing(null)}
          save={async (fields) => {
            const result = await api<ProjectEntity>(
              editing === "new" ? path : `${path}/${editing.id}`,
              {
                method: editing === "new" ? "POST" : "PATCH",
                body: JSON.stringify({
                  fields,
                  ...(editing !== "new" ? { revision: editing.revision } : {}),
                }),
              },
            );
            const wasNew = editing === "new";
            setEditing(null);
            setRefresh((n) => n + 1);
            changed?.();
            if (wasNew && kind === "project") openProject?.(result.id);
          }}
        />
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {busy && <p role="status">Loading {title} records…</p>}
      {!busy && !error && !page.total && (
        <p className="inline-note">
          No {title} records match. Create a record or change the search/status
          filter.
        </p>
      )}
      {!!page.items.length && (
        <div className="table-scroll" tabIndex={0}>
          <table aria-label={`${title} records`}>
            <thead>
              <tr>
                <th>Name / stable ID</th>
                <th>Declared identifier</th>
                <th>
                  {kind === "sample"
                    ? "Assay / expectation"
                    : kind === "sequencing_run"
                      ? "Platform / date / stage"
                      : "Created"}
                </th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((entity) => (
                <tr key={entity.id}>
                  <td className="project-label">
                    {entity.declared.display_name}
                    <small>{entity.id}</small>
                  </td>
                  <td>{entity.declared.declared_identifier || "Unknown"}</td>
                  <td>
                    {kind === "sample" ? (
                      <>
                        {entity.declared.assay || "Unknown assay"}
                        <small>
                          {entity.declared.expected_yield
                            ? `${entity.declared.expected_yield.minimum.toLocaleString()} ${entity.declared.expected_yield.metric} (declared)`
                            : "No declared yield expectation"}
                        </small>
                      </>
                    ) : kind === "sequencing_run" ? (
                      <>
                        {entity.declared.platform || "Unknown platform"}
                        <small>
                          {entity.declared.sequenced_at || "Unknown date"} ·{" "}
                          {entity.declared.input_stage || "unknown"}
                        </small>
                      </>
                    ) : (
                      date(entity.created_at)
                    )}
                  </td>
                  <td>{entity.declared.status}</td>
                  <td>
                    <div className="project-actions">
                      {openProject && (
                        <button
                          className="button small"
                          onClick={() => openProject(entity.id)}
                        >
                          Open project
                        </button>
                      )}
                      <button
                        className="button small"
                        aria-label={`Edit ${title} ${entityLabel(entity)}`}
                        onClick={() => setEditing(entity)}
                      >
                        Edit {title}
                      </button>
                      {inspect && (
                        <button
                          className="button small"
                          onClick={() => inspect(entity)}
                        >
                          View associated reads
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pages
        label={`${title}s`}
        offset={offset}
        total={page.total}
        busy={busy}
        setOffset={setOffset}
      />
      {kind === "sample" && (
        <ProjectImport
          projectId={path.split("/")[2]}
          saved={() => {
            setOffset(0);
            setRefresh((n) => n + 1);
            changed?.();
          }}
        />
      )}
    </section>
  );
}

function LinkedAnalyses({
  projectId,
  refreshParent,
  openAnalysis,
  filter,
}: {
  projectId: string;
  refreshParent: () => void;
  openAnalysis: (id: string, tab: DetailTab, reportId?: string) => void;
  filter: ProjectEntity | null;
}) {
  const base = `api/projects/${projectId}`;
  const [page, setPage] = useState(blankPage<AnalysisLink>),
    [offset, setOffset] = useState(0),
    [refresh, setRefresh] = useState(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [unassigned, setUnassigned] = useState(
      blankPage<Pick<Run, "id" | "name" | "state" | "mode">>,
    ),
    [unassignedOffset, setUnassignedOffset] = useState(0),
    [showAttach, setShowAttach] = useState(false),
    [selectedAnalysis, setSelectedAnalysis] = useState("");
  const [editing, setEditing] = useState<AnalysisLink | null>(null),
    [evidence, setEvidence] = useState(blankPage<ProjectEvidence>),
    [evidenceOffset, setEvidenceOffset] = useState(0);
  const [associations, setAssociations] = useState(
      blankPage<ProjectAssociation>,
    ),
    [associationOffset, setAssociationOffset] = useState(0);
  const [captureLink, setCaptureLink] = useState<AnalysisLink | null>(null),
    [scopes, setScopes] = useState<string[][]>([]),
    [selectedScope, setSelectedScope] = useState("");
  useEffect(() => setAssociationOffset(0), [filter?.id]);
  const reload = () => {
    setRefresh((n) => n + 1);
    refreshParent();
  };
  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    setError("");
    void Promise.all([
      api<CatalogPage<AnalysisLink>>(
        `${base}/analyses?offset=${offset}&limit=25`,
      ),
      api<CatalogPage<ProjectEvidence>>(
        `${base}/evidence?offset=${evidenceOffset}&limit=25`,
      ),
    ])
      .then(([links, snapshots]) => {
        if (!cancelled) {
          setPage(links);
          setEvidence(snapshots);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [base, offset, evidenceOffset, refresh]);
  useEffect(() => {
    if (!showAttach) return;
    let cancelled = false;
    void api<typeof unassigned>(
      `api/unassigned-analyses?offset=${unassignedOffset}&limit=25`,
    )
      .then((value) => {
        if (!cancelled) setUnassigned(value);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [showAttach, unassignedOffset, refresh]);
  useEffect(() => {
    if (!filter) return;
    let cancelled = false;
    const query = `${filter.kind === "sample" ? "sample_id" : "sequencing_run_id"}=${encodeURIComponent(filter.id)}`;
    void api<CatalogPage<ProjectAssociation>>(
      `${base}/associations?${query}&offset=${associationOffset}&limit=25`,
    )
      .then((value) => {
        if (!cancelled) setAssociations(value);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [base, filter, associationOffset, refresh]);
  const attach = async () => {
    setBusy(true);
    setError("");
    try {
      await api(`${base}/analyses`, {
        method: "POST",
        body: JSON.stringify({
          analysis_id: selectedAnalysis,
          assignments: [],
        }),
      });
      setSelectedAnalysis("");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot attach analysis.");
    } finally {
      setBusy(false);
    }
  };
  const prepareCapture = async (link: AnalysisLink) => {
    setError("");
    try {
      const run = await api<Run>(`api/runs/${link.analysis_id}`);
      const unique = new Map(
        (run.release_reviews ?? []).map((event) => [
          JSON.stringify([...event.sample_ids].sort()),
          event.sample_ids,
        ]),
      );
      setScopes([...unique.values()]);
      setSelectedScope("");
      setCaptureLink(link);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Source analysis unavailable.",
      );
    }
  };
  return (
    <section aria-label="Project analyses and evidence">
      <div className="project-actions">
        <h2>Linked analyses</h2>
        <button
          className="button primary small"
          onClick={() => setShowAttach((value) => !value)}
        >
          Attach existing analysis
        </button>
        <button className="button small" disabled={busy} onClick={reload}>
          Refresh project evidence
        </button>
      </div>
      <p className="inline-note">
        Independent analyses remain unassigned until explicitly attached. File
        identities are confirmed separately. Stored snapshots describe
        historical evidence, not current project readiness.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {busy && <p role="status">Loading project analyses…</p>}
      {showAttach && (
        <section
          className="form-section"
          aria-label="Attach analysis to project"
        >
          <label className="field-label">
            Unassigned analysis
            <select
              aria-label="Unassigned analysis"
              className="wide-input"
              value={selectedAnalysis}
              onChange={(e) => setSelectedAnalysis(e.target.value)}
            >
              <option value="">Choose an existing analysis</option>
              {unassigned.items.map((run) => (
                <option value={run.id} key={run.id}>
                  {run.name} · {run.id.slice(-8)} · {modeLabel(run.mode)} ·{" "}
                  {run.state}
                </option>
              ))}
            </select>
          </label>
          <Pages
            label="unassigned analyses"
            offset={unassignedOffset}
            total={unassigned.total}
            busy={busy}
            setOffset={(value) => {
              setSelectedAnalysis("");
              setUnassignedOffset(value);
            }}
          />
          <p className="inline-note">
            This attaches the selected analysis to this project. It will not
            infer samples, copy FASTQs, or change QC/release results.
          </p>
          <button
            className="button primary"
            disabled={busy || !selectedAnalysis}
            onClick={() => void attach()}
          >
            Confirm analysis attachment
          </button>
        </section>
      )}
      {!busy && !page.total && (
        <p className="inline-note">No analyses are linked to this project.</p>
      )}
      <div className="table-scroll" tabIndex={0}>
        <table aria-label="Project linked analyses">
          <thead>
            <tr>
              <th>Analysis / ID</th>
              <th>QC execution state</th>
              <th>Open existing results</th>
              <th>Metadata / evidence</th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((link) => (
              <tr key={link.id}>
                <td className="project-label">
                  {link.analysis?.name || "Source analysis unavailable"}
                  <small>{link.analysis_id}</small>
                </td>
                <td>{link.analysis?.state || "Unknown"}</td>
                <td>
                  <div className="project-actions">
                    {(["overview", "metrics", "reports"] as DetailTab[]).map(
                      (tab) => (
                        <button
                          className="button small"
                          key={tab}
                          disabled={!link.analysis}
                          onClick={() => openAnalysis(link.analysis_id, tab)}
                        >
                          {tab === "overview"
                            ? "Overview & logs"
                            : tab === "metrics"
                              ? "QC metrics"
                              : "Reports"}
                        </button>
                      ),
                    )}
                  </div>
                </td>
                <td>
                  <div className="project-actions">
                    <button
                      className="button small"
                      disabled={!link.analysis}
                      onClick={() => setEditing(link)}
                    >
                      Assign / inspect files
                    </button>
                    <button
                      className="button small"
                      disabled={
                        !link.analysis ||
                        ["queued", "running"].includes(link.analysis.state)
                      }
                      onClick={() => void prepareCapture(link)}
                    >
                      Capture evidence
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pages
        label="linked analyses"
        offset={offset}
        total={page.total}
        busy={busy}
        setOffset={setOffset}
      />
      {editing && (
        <ProjectAssignments
          key={editing.id}
          projectId={projectId}
          link={editing}
          changed={reload}
          close={() => setEditing(null)}
          inspect={(id, reportId) => openAnalysis(id, "metrics", reportId)}
        />
      )}
      {captureLink && (
        <form
          className="form-section"
          aria-label="Capture project evidence"
          onSubmit={(e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            void api(`${base}/analyses/${captureLink.id}/evidence`, {
              method: "POST",
              body: JSON.stringify(
                selectedScope ? { sample_ids: JSON.parse(selectedScope) } : {},
              ),
            })
              .then(() => {
                setCaptureLink(null);
                reload();
              })
              .catch((err) => setError(err.message))
              .finally(() => setBusy(false));
          }}
        >
          <h3>Capture · {captureLink.analysis?.name}</h3>
          <label className="field-label">
            Project evidence scope
            <select
              aria-label="Project evidence scope"
              className="wide-input"
              value={selectedScope}
              onChange={(e) => setSelectedScope(e.target.value)}
            >
              <option value="">QC metadata only</option>
              {scopes.map((scope) => (
                <option
                  key={JSON.stringify(scope)}
                  value={JSON.stringify(scope)}
                >
                  Evaluate saved analysis-local release scope:{" "}
                  {scope.join(", ")}
                </option>
              ))}
            </select>
          </label>
          <p className="inline-note">
            A snapshot preserves current declarations and evaluated evidence.
            This action does not approve a release. Saved scopes can evaluate as
            stale or blocked.
          </p>
          <div className="project-actions">
            <button className="button primary" disabled={busy}>
              Capture immutable snapshot
            </button>
            <button
              className="button"
              type="button"
              onClick={() => setCaptureLink(null)}
            >
              Cancel evidence capture
            </button>
          </div>
        </form>
      )}
      {filter && (
        <section
          className="form-section"
          aria-label="Associated sample or run reads"
        >
          <h3>Associated reads · {entityLabel(filter)}</h3>
          <div className="table-scroll" tabIndex={0}>
            <table aria-label="Associated lane and read files">
              <thead>
                <tr>
                  <th>File / ID</th>
                  <th>Lane / chunk / read</th>
                  <th>Sample / sequencing run</th>
                  <th>Inspect</th>
                </tr>
              </thead>
              <tbody>
                {associations.items.map((row) => {
                  return (
                    <tr key={row.id}>
                      <td>
                        {row.observed.filename}
                        <small>{row.file_id}</small>
                      </td>
                      <td>
                        {[
                          row.declared.lane,
                          row.declared.chunk,
                          row.declared.read,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "Unknown"}
                      </td>
                      <td>
                        <small>{row.sample_id}</small>
                        <small>{row.sequencing_run_id}</small>
                      </td>
                      <td>
                        {row.analysis_id && row.observed.report_id ? (
                          <button
                            className="button small"
                            onClick={() =>
                              openAnalysis(
                                row.analysis_id!,
                                "metrics",
                                row.observed.report_id!,
                              )
                            }
                          >
                            Inspect lane/read QC
                          </button>
                        ) : (
                          <span>
                            Open the linked analysis page to inspect its
                            results.
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pages
            label="associated reads"
            offset={associationOffset}
            total={associations.total}
            busy={busy}
            setOffset={setAssociationOffset}
          />
          {!associations.total && (
            <p className="inline-note">
              No files are explicitly associated with this identity.
            </p>
          )}
        </section>
      )}
      <section className="form-section">
        <h3>Captured QC / release evidence</h3>
        <p className="inline-note">
          Historical snapshots retain their original declarations and review
          fingerprints. Approval, package creation and verified delivery are
          separate states; this table does not assert current readiness.
        </p>
        <div className="table-scroll" tabIndex={0}>
          <table aria-label="Project evidence snapshots">
            <thead>
              <tr>
                <th>Captured</th>
                <th>Snapshot / source</th>
                <th>QC state</th>
                <th>Captured release review</th>
                <th>Original evidence</th>
              </tr>
            </thead>
            <tbody>
              {evidence.items.map((item) => (
                <tr key={item.id}>
                  <td>{date(item.created_at)}</td>
                  <td className="project-label">
                    {item.id}
                    <small>{item.summary.analysis_id}</small>
                    <small>{item.sha256}</small>
                  </td>
                  <td>{item.summary.qc_state}</td>
                  <td>
                    {item.summary.review_state} · {item.summary.readiness}
                  </td>
                  <td>
                    <button
                      className="button small"
                      onClick={() =>
                        openAnalysis(item.summary.analysis_id, "overview")
                      }
                    >
                      Open source review
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pages
          label="snapshots"
          offset={evidenceOffset}
          total={evidence.total}
          busy={busy}
          setOffset={setEvidenceOffset}
        />
        {!evidence.total && (
          <p className="inline-note">
            No immutable evidence has been captured.
          </p>
        )}
      </section>
    </section>
  );
}

function ProjectDetail({
  id,
  back,
  openAnalysis,
}: {
  id: string;
  back: () => void;
  openAnalysis: (id: string, tab: DetailTab, reportId?: string) => void;
}) {
  const [project, setProject] = useState<ProjectEntity | null>(null),
    [error, setError] = useState(""),
    [editing, setEditing] = useState(false),
    [refresh, setRefresh] = useState(0);
  const tabs = ["Samples", "Sequencing runs", "Analyses & evidence"];
  const [tab, setTab] = useState(tabs[0]),
    [filter, setFilter] = useState<ProjectEntity | null>(null);
  const heading = useRef<HTMLHeadingElement>(null),
    base = `api/projects/${id}`;
  useEffect(() => {
    let cancelled = false;
    setError("");
    void api<ProjectEntity>(base)
      .then((value) => {
        if (!cancelled) setProject(value);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [base, refresh]);
  useEffect(() => {
    if (project?.id) heading.current?.focus();
  }, [project?.id]);
  const inspect = (entity: ProjectEntity) => {
    setFilter(entity);
    setTab(tabs[2]);
  };
  return (
    <section aria-label="Project workspace detail">
      <div className="project-actions">
        <button className="button small" onClick={back}>
          Back to projects
        </button>
        {project && (
          <button
            className="button small"
            onClick={() => setEditing((value) => !value)}
          >
            Edit project metadata
          </button>
        )}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!project ? (
        !error && <p role="status">Loading project…</p>
      ) : (
        <>
          <h2 ref={heading} tabIndex={-1}>
            {project.declared.display_name}
          </h2>
          <p className="inline-note project-hash">
            {project.id} · {project.declared.status} · revision{" "}
            {project.revision}
          </p>
          <p className="inline-note">
            {project.counts?.sample ?? 0} sample records ·{" "}
            {project.counts?.sequencing_run ?? 0} sequencing runs ·{" "}
            {project.counts?.analyses ?? 0} linked analyses. Project QC/release
            readiness: unknown; inspect original evidence.
          </p>
          {editing && (
            <ProjectEntityForm
              kind="project"
              entity={project}
              cancel={() => setEditing(false)}
              save={async (fields) => {
                await api(base, {
                  method: "PATCH",
                  body: JSON.stringify({ fields, revision: project.revision }),
                });
                setEditing(false);
                setRefresh((n) => n + 1);
              }}
            />
          )}
          <div
            className="detail-tabs"
            role="tablist"
            aria-label="Project detail sections"
          >
            {tabs.map((name, index) => (
              <button
                key={name}
                id={`${id}-tab-${index}`}
                className={tab === name ? "active" : ""}
                role="tab"
                aria-selected={tab === name}
                aria-controls={`${id}-panel`}
                tabIndex={tab === name ? 0 : -1}
                onClick={() => setTab(name)}
                onKeyDown={(event) => {
                  let next = index;
                  if (event.key === "ArrowRight")
                    next = (index + 1) % tabs.length;
                  else if (event.key === "ArrowLeft")
                    next = (index + tabs.length - 1) % tabs.length;
                  else if (event.key === "Home") next = 0;
                  else if (event.key === "End") next = tabs.length - 1;
                  else return;
                  event.preventDefault();
                  setTab(tabs[next]);
                  document.getElementById(`${id}-tab-${next}`)?.focus();
                }}
              >
                {name}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id={`${id}-panel`}
            aria-labelledby={`${id}-tab-${tabs.indexOf(tab)}`}
          >
            {tab === tabs[0] && (
              <EntityList
                kind="sample"
                path={`${base}/samples`}
                inspect={inspect}
                changed={() => setRefresh((n) => n + 1)}
              />
            )}
            {tab === tabs[1] && (
              <EntityList
                kind="sequencing_run"
                path={`${base}/sequencing-runs`}
                inspect={inspect}
                changed={() => setRefresh((n) => n + 1)}
              />
            )}
            {tab === tabs[2] && (
              <LinkedAnalyses
                projectId={id}
                refreshParent={() => setRefresh((n) => n + 1)}
                openAnalysis={openAnalysis}
                filter={filter}
              />
            )}
          </div>
        </>
      )}
    </section>
  );
}

export default function ProjectWorkspace({
  projectId,
  selectProject,
  openAnalysis,
}: {
  projectId: string;
  selectProject: (id: string) => void;
  openAnalysis: (id: string, tab: DetailTab, reportId?: string) => void;
}) {
  return (
    <div className="project-workspace">
      {projectId ? (
        <ProjectDetail
          key={projectId}
          id={projectId}
          back={() => selectProject("")}
          openAnalysis={openAnalysis}
        />
      ) : (
        <>
          <p className="inline-note">
            Organize declared samples and sequencing runs, then explicitly
            attach existing QC analyses. Standalone file analysis remains
            available in Files.
          </p>
          <EntityList
            kind="project"
            path="api/projects"
            openProject={selectProject}
          />
        </>
      )}
    </div>
  );
}
