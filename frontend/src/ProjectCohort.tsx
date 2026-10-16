import { useEffect, useState } from "react";
import { api } from "./api";
import { selectCohortRows } from "./batch";
import type { CatalogPage, ProjectEntity } from "./project";

export default function ProjectCohort({
  projectId,
  kind,
  selected,
  change,
}: {
  projectId: string;
  kind: "samples" | "sequencing-runs";
  selected: string[] | null;
  change: (ids: string[] | null) => void;
}) {
  const [search, setSearch] = useState(""),
    [offset, setOffset] = useState(0),
    [page, setPage] = useState<CatalogPage<ProjectEntity> | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const title = kind === "samples" ? "samples" : "sequencing runs";
  useEffect(() => {
    let stop = false;
    setBusy(true);
    setError("");
    void api<CatalogPage<ProjectEntity>>(
      `api/projects/${projectId}/${kind}?limit=25&offset=${offset}&search=${encodeURIComponent(search)}`,
    )
      .then((value) => {
        if (!stop) setPage(value);
      })
      .catch((err) => {
        if (!stop) setError(err.message);
      })
      .finally(() => {
        if (!stop) setBusy(false);
      });
    return () => {
      stop = true;
    };
  }, [projectId, kind, search, offset]);
  const ids = selected ?? [];
  const add = (values: string[]) => {
    try {
      change(selectCohortRows(ids, values));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot update selection.");
    }
  };
  const visible = page?.items.map((row) => row.id) ?? [];
  return (
    <section aria-label={`Choose batch ${title}`}>
      <h3>{kind === "samples" ? "Samples" : "Sequencing runs"}</h3>
      <div
        className="project-actions"
        role="group"
        aria-label={`${title} scope`}
      >
        <button
          type="button"
          className={`button small ${selected === null ? "primary" : ""}`}
          aria-pressed={selected === null}
          onClick={() => change(null)}
        >
          All project {title}
        </button>
        <button
          type="button"
          className={`button small ${selected !== null ? "primary" : ""}`}
          aria-pressed={selected !== null}
          onClick={() => change(ids)}
        >
          Choose {title}
        </button>
      </div>
      {selected === null ? (
        <p className="inline-note">
          Includes all active {title} with confirmed FASTQ references.
        </p>
      ) : (
        <>
          <label className="field-label">
            Search {title}
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <div className="project-actions">
            <span>{ids.length} selected (maximum 100)</span>
            <button
              type="button"
              className="button small"
              disabled={busy || !visible.length || ids.length >= 100}
              onClick={() => add(visible)}
            >
              Select this page
            </button>
            <button
              type="button"
              className="button small"
              disabled={!ids.length}
              onClick={() => change([])}
            >
              Clear selection
            </button>
          </div>
          <div className="table-scroll" tabIndex={0}>
            <table aria-label={`Selectable project ${title}`}>
              <thead>
                <tr>
                  <th>Select</th>
                  <th>Name</th>
                  <th>
                    {kind === "samples" ? "Assay / library" : "Platform / date"}
                  </th>
                </tr>
              </thead>
              <tbody>
                {page?.items.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Select ${row.declared.display_name} ${row.id.slice(-8)}`}
                        checked={ids.includes(row.id)}
                        disabled={!ids.includes(row.id) && ids.length >= 100}
                        onChange={(e) =>
                          e.target.checked
                            ? add([row.id])
                            : change(ids.filter((id) => id !== row.id))
                        }
                      />
                    </td>
                    <td>
                      {row.declared.display_name}
                      <small title={row.id}>
                        {row.declared.declared_identifier || row.id.slice(-8)}
                      </small>
                    </td>
                    <td>
                      {(kind === "samples"
                        ? [row.declared.assay, row.declared.library_type]
                        : [row.declared.platform, row.declared.sequenced_at]
                      )
                        .filter(Boolean)
                        .join(" · ") || "Not specified"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {busy && <p role="status">Loading {title}…</p>}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <div className="project-actions">
            <button
              type="button"
              className="button small"
              disabled={busy || !offset}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Previous {title}
            </button>
            <span>{page?.total ?? 0} records</span>
            <button
              type="button"
              className="button small"
              disabled={busy || !page || offset + 25 >= page.total}
              onClick={() => setOffset(offset + 25)}
            >
              Next {title}
            </button>
          </div>
          {!ids.length && (
            <p className="inline-note">
              Select at least one row, or use All project {title}.
            </p>
          )}
        </>
      )}
    </section>
  );
}
