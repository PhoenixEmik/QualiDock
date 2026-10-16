import { useEffect, useState } from "react";
import { api } from "./api";
import { assignmentsFor, entityLabel } from "./project";
import type {
  AnalysisLink,
  CatalogPage,
  ProjectAssociation,
  ProjectEntity,
  ProjectFile,
} from "./project";

function IdentityPicker({
  projectId,
  kind,
  value,
  change,
}: {
  projectId: string;
  kind: "samples" | "sequencing-runs";
  value: string;
  change: (id: string) => void;
}) {
  const [search, setSearch] = useState(""),
    [items, setItems] = useState<ProjectEntity[]>([]),
    [error, setError] = useState("");
  const title = kind === "samples" ? "Sample" : "Sequencing run";
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      void api<CatalogPage<ProjectEntity>>(
        `api/projects/${projectId}/${kind}?limit=100&search=${encodeURIComponent(search)}`,
      )
        .then((page) => {
          if (!cancelled) {
            setItems(page.items);
            setError("");
          }
        })
        .catch((err) => {
          if (!cancelled) setError(err.message);
        });
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [projectId, kind, search]);
  return (
    <div>
      <label className="field-label">
        Find {title.toLowerCase()} identity
        <input
          className="wide-input"
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            change("");
          }}
        />
      </label>
      <label className="field-label">
        Confirmed {title.toLowerCase()} identity
        <select
          className="wide-input"
          value={value}
          onChange={(e) => change(e.target.value)}
        >
          <option value="">Choose an explicit ID</option>
          {value && !items.some((item) => item.id === value) && (
            <option value={value}>Current ID · {value}</option>
          )}
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {entityLabel(item)}
            </option>
          ))}
        </select>
      </label>
      <p className="inline-note">
        Up to 100 matches. Search to find additional records; identical labels
        retain different IDs.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

interface Inventory {
  analysis_id: string;
  files: ProjectFile[];
  associations: ProjectAssociation[];
}
export default function ProjectAssignments({
  projectId,
  link,
  changed,
  inspect,
  close,
}: {
  projectId: string;
  link: AnalysisLink;
  changed: () => void;
  inspect: (analysisId: string, reportId: string) => void;
  close: () => void;
}) {
  const [data, setData] = useState<Inventory | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0),
    [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set()),
    [editing, setEditing] = useState<ProjectAssociation | null>(null);
  const [sampleId, setSampleId] = useState(""),
    [runId, setRunId] = useState(""),
    [reason, setReason] = useState("");
  const [lane, setLane] = useState(""),
    [chunk, setChunk] = useState(""),
    [library, setLibrary] = useState(""),
    [role, setRole] = useState("");
  const base = `api/projects/${projectId}`;
  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError("");
    void api<Inventory>(`${base}/analyses/${link.id}/inventory`)
      .then((value) => {
        if (!cancelled) setData(value);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [base, link.id, refresh]);
  const assigned = new Map(data?.associations.map((row) => [row.file_id, row]));
  const files = (data?.files ?? []).filter((file) =>
    (file.filename + file.file_id)
      .toLocaleLowerCase()
      .includes(search.toLocaleLowerCase()),
  );
  const reload = () => {
    setEditing(null);
    setSelected(new Set());
    setReason("");
    setRefresh((n) => n + 1);
  };
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const chosen = (data?.files ?? []).filter((file) =>
        selected.has(file.file_id),
      );
      const assignments = assignmentsFor(chosen, sampleId, runId);
      if (!assignments.length)
        throw new Error("Select at least one accessible unassigned file.");
      if (editing) {
        const assignment = {
          ...assignments[0],
          source: "user_assigned",
          lane: lane || null,
          chunk: chunk || null,
          library_identifier: library || null,
          read: role || null,
        };
        await api(`${base}/associations/${editing.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            revision: editing.revision,
            assignment,
            reason,
          }),
        });
      } else
        await api(`${base}/analyses/${link.id}/assignments`, {
          method: "POST",
          body: JSON.stringify({ assignments }),
        });
      reload();
      changed();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to save associations.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="form-section" aria-label="Project file assignments">
      <div className="project-actions">
        <h3>Files · {link.analysis?.name ?? link.analysis_id}</h3>
        <button className="button small" onClick={close}>
          Close file assignments
        </button>
        <button className="button small" disabled={busy} onClick={reload}>
          Refresh linked file metadata
        </button>
      </div>
      <p className="inline-note">
        Confirm identities explicitly. Assignments organize files; they do not
        prove biological identity, rerun QC, merge lanes or change original
        reports. Corrections require a reason and preserve earlier snapshots.
      </p>
      {!data && !error && <p role="status">Loading linked files…</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {data && (
        <>
          <p>
            {data.files.length} FASTQ references · {data.associations.length}{" "}
            assigned · {data.files.length - data.associations.length} unresolved
          </p>
          {!data.files.length && (
            <p className="inline-note">
              No original FASTQ references are available in this analysis. Its
              reports remain accessible.
            </p>
          )}
          <label className="field-label">
            Search linked FASTQ files
            <input
              className="wide-input"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <div className="table-scroll" tabIndex={0}>
            <table aria-label="Project linked FASTQ files">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      aria-label="Select all visible unassigned FASTQs"
                      disabled={busy || !!editing}
                      checked={
                        files.some(
                          (f) => !assigned.has(f.file_id) && f.input_available,
                        ) &&
                        files
                          .filter(
                            (f) =>
                              !assigned.has(f.file_id) && f.input_available,
                          )
                          .every((f) => selected.has(f.file_id))
                      }
                      onChange={(e) => {
                        const next = new Set(selected);
                        for (const f of files.filter(
                          (f) => !assigned.has(f.file_id) && f.input_available,
                        )) {
                          if (e.target.checked) next.add(f.file_id);
                          else next.delete(f.file_id);
                        }
                        setSelected(next);
                      }}
                    />
                  </th>
                  <th>FASTQ / identity</th>
                  <th>Lane / chunk / read</th>
                  <th>Declared sample / run</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {files.map((file) => {
                  const association = assigned.get(file.file_id);
                  return (
                    <tr key={file.file_id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Select ${file.filename} ${file.file_id}`}
                          disabled={
                            busy ||
                            !!association ||
                            !!editing ||
                            !file.input_available
                          }
                          checked={selected.has(file.file_id)}
                          onChange={(e) => {
                            const next = new Set(selected);
                            if (e.target.checked) next.add(file.file_id);
                            else next.delete(file.file_id);
                            setSelected(next);
                          }}
                        />
                      </td>
                      <td className="project-label">
                        {file.filename}
                        <small>{file.file_id}</small>
                        {!file.input_available && (
                          <small>Source unavailable</small>
                        )}
                      </td>
                      <td>
                        {[
                          association?.declared.lane ?? file.lane,
                          association?.declared.chunk ?? file.chunk,
                          association?.declared.read ?? file.read,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "Unknown"}
                      </td>
                      <td>
                        {association ? (
                          <>
                            <small>{association.sample_id}</small>
                            <small>{association.sequencing_run_id}</small>
                            <small>Revision {association.revision}</small>
                          </>
                        ) : (
                          "Unresolved — no auto-match"
                        )}
                      </td>
                      <td>
                        <div className="project-actions">
                          {file.report_id && (
                            <button
                              className="button small"
                              onClick={() =>
                                inspect(link.analysis_id, file.report_id!)
                              }
                            >
                              Inspect read QC
                            </button>
                          )}
                          {association && (
                            <button
                              className="button small"
                              disabled={busy || !file.input_available}
                              onClick={() => {
                                setEditing(association);
                                setSelected(new Set([file.file_id]));
                                setSampleId(association.sample_id);
                                setRunId(association.sequencing_run_id);
                                setLane(association.declared.lane ?? "");
                                setChunk(association.declared.chunk ?? "");
                                setLibrary(
                                  association.declared.library_identifier ?? "",
                                );
                                setRole(association.declared.read ?? "");
                                setReason("");
                              }}
                            >
                              Correct association
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!!data.files.length && (
            <fieldset disabled={busy} className="project-fields">
              <legend>
                {editing
                  ? "Correct one declared association"
                  : `Confirm ${selected.size} selected FASTQ files`}
              </legend>
              <IdentityPicker
                projectId={projectId}
                kind="samples"
                value={sampleId}
                change={setSampleId}
              />
              <IdentityPicker
                projectId={projectId}
                kind="sequencing-runs"
                value={runId}
                change={setRunId}
              />
              {editing && (
                <>
                  <label className="field-label">
                    Lane
                    <input
                      className="wide-input"
                      value={lane}
                      maxLength={200}
                      onChange={(e) => setLane(e.target.value)}
                    />
                  </label>
                  <label className="field-label">
                    Chunk
                    <input
                      className="wide-input"
                      value={chunk}
                      maxLength={200}
                      onChange={(e) => setChunk(e.target.value)}
                    />
                  </label>
                  <label className="field-label">
                    Library identifier
                    <input
                      className="wide-input"
                      value={library}
                      maxLength={200}
                      onChange={(e) => setLibrary(e.target.value)}
                    />
                  </label>
                  <label className="field-label">
                    Declared read role
                    <select
                      className="wide-input"
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                    >
                      <option value="">Unknown</option>
                      {["R1", "R2", "SE", "unpaired"].map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field-label project-wide">
                    Association correction reason
                    <textarea
                      className="wide-input"
                      value={reason}
                      maxLength={2000}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </label>
                </>
              )}
              <div className="project-actions project-wide">
                <button
                  className="button primary"
                  disabled={
                    !selected.size ||
                    !sampleId ||
                    !runId ||
                    (!!editing && !reason.trim())
                  }
                  onClick={() => void save()}
                >
                  {busy
                    ? "Saving…"
                    : editing
                      ? "Save reasoned correction"
                      : "Confirm file assignments"}
                </button>
                {editing && (
                  <button className="button" onClick={reload}>
                    Cancel association correction
                  </button>
                )}
              </div>
            </fieldset>
          )}
        </>
      )}
    </section>
  );
}
