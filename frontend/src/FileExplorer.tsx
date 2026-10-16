import { useEffect, useRef } from "react";
import {
  ArrowLeft,
  ChevronRight,
  FileArchive,
  FileText,
  Folder,
  FolderOpen,
  HardDrive,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { bytes, date } from "./api";
import { Empty } from "./Feedback";
import {
  explorerRows,
  explorerLanes,
  matchesRow,
  rowInputPaths,
  selectionState,
  type ExplorerMode,
} from "./explorer";
import type { Entry, Listing } from "./types";

interface Props {
  listing: Listing | null;
  roots: string[];
  path: string;
  search: string;
  selected: Map<string, Entry>;
  mode: ExplorerMode;
  busy: boolean;
  setPath: (value: string) => void;
  setSearch: (value: string) => void;
  setMode: (value: ExplorerMode) => void;
  browse: (path: string, offset?: number, refresh?: boolean) => Promise<void>;
  select: (paths: string[], checked: boolean) => Promise<void>;
}

export default function FileExplorer({
  listing,
  roots,
  path,
  search,
  selected,
  mode,
  busy,
  setPath,
  setSearch,
  setMode,
  browse,
  select,
}: Props) {
  const pathInput = useRef<HTMLInputElement>(null);
  const previousDirectory = useRef(listing?.path);
  useEffect(() => {
    if (
      previousDirectory.current &&
      previousDirectory.current !== listing?.path
    ) {
      pathInput.current?.focus();
    }
    previousDirectory.current = listing?.path;
  }, [listing?.path]);
  const rows = explorerRows(
    listing?.entries || [],
    mode,
    listing?.sample_groups,
  ).filter((row) => matchesRow(row, search));
  const paths = [...new Set(rows.flatMap(rowInputPaths))];
  const selection = selectionState(paths, selected);
  return (
    <section className="file-section" aria-labelledby="explorer-title">
      <div className="section-heading explorer-toolbar">
        <div>
          <FolderOpen size={19} />
          <h2 id="explorer-title">File explorer</h2>
        </div>
        <div className="explorer-tools">
          <div className="view-toggle" role="group" aria-label="Explorer view">
            {(["samples", "files"] as const).map((value) => (
              <button
                key={value}
                aria-pressed={mode === value}
                className={mode === value ? "active" : ""}
                onClick={() => setMode(value)}
              >
                {value === "samples" ? "Samples" : "Files"}
              </button>
            ))}
          </div>
          <label className="search-box">
            <Search size={15} />
            <input
              aria-label="Search files and samples"
              aria-describedby="explorer-search-help"
              placeholder="Search names…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <span id="explorer-search-help" className="sr-only">
              Searches loaded entries by sample name or either read filename.
              Load more files to include additional entries.
            </span>
          </label>
          <button
            className="icon-button"
            aria-label="Refresh directory"
            onClick={() => listing && void browse(listing.path, 0, true)}
            disabled={busy || !listing}
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
          onClick={() => listing?.parent && void browse(listing.parent)}
        >
          <ArrowLeft size={15} />
        </button>
        <HardDrive size={14} />
        {roots.length > 1 && (
          <select
            aria-label="Connected storage root"
            value={
              roots
                .filter(
                  (root) =>
                    listing?.path === root ||
                    listing?.path.startsWith(root + "/"),
                )
                .sort((a, b) => b.length - a.length)[0] || ""
            }
            onChange={(event) => void browse(event.target.value)}
            disabled={busy}
          >
            <option value="" disabled>
              Storage root
            </option>
            {roots.map((root) => (
              <option key={root} value={root}>
                {root}
              </option>
            ))}
          </select>
        )}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void browse(path);
          }}
        >
          <input
            ref={pathInput}
            aria-label="Directory path"
            value={path}
            onChange={(event) => setPath(event.target.value)}
            spellCheck={false}
          />
          <button
            className="text-button"
            type="submit"
            disabled={busy || !path}
          >
            Go
          </button>
        </form>
      </div>
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label={
          mode === "samples"
            ? "Samples and directory entries"
            : "Directory files"
        }
        aria-busy={busy}
      >
        <table className="file-table">
          <thead>
            <tr>
              <th className="check-cell">
                <input
                  type="checkbox"
                  aria-label={`Select all visible ${mode === "samples" ? "samples and reports" : "input files"}`}
                  checked={selection.all}
                  aria-checked={selection.some ? "mixed" : selection.all}
                  ref={(element) => {
                    if (element) element.indeterminate = selection.some;
                  }}
                  disabled={busy || !paths.length}
                  onChange={(event) => void select(paths, event.target.checked)}
                />
              </th>
              <th>{mode === "samples" ? "Sample / name" : "Name"}</th>
              <th>Type</th>
              <th>Read pairing</th>
              <th>{mode === "samples" ? "Loaded size" : "Size"}</th>
              <th>Modified</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const first = row.files[0];
              const inputs = rowInputPaths(row);
              const state = selectionState(inputs, selected);
              const size =
                first.kind === "directory"
                  ? null
                  : row.files.reduce((sum, file) => sum + (file.size || 0), 0);
              const modified = Math.max(
                ...row.files.map((file) => file.modified),
              );
              return (
                <tr
                  key={row.id}
                  className={state.all || state.some ? "row-selected" : ""}
                >
                  <td className="check-cell">
                    {inputs.length > 0 && (
                      <input
                        id={`selection-${encodeURIComponent(row.id)}`}
                        type="checkbox"
                        aria-label={`Select ${row.sample ? "sample" : "file"} ${row.name}`}
                        checked={state.all}
                        aria-checked={state.some ? "mixed" : state.all}
                        ref={(element) => {
                          if (element) element.indeterminate = state.some;
                        }}
                        disabled={busy}
                        onChange={(event) =>
                          void select(inputs, event.target.checked)
                        }
                      />
                    )}
                  </td>
                  <td>
                    {first.kind === "directory" ? (
                      <button
                        className="file-name directory"
                        onClick={() => void browse(first.path)}
                        disabled={busy}
                      >
                        <Folder size={19} fill="var(--surface-muted)" />
                        <span>{row.name}</span>
                        <ChevronRight size={14} />
                      </button>
                    ) : (
                      <>
                        <div
                          className={`file-name ${first.kind}`}
                          title={first.path}
                        >
                          {first.kind === "fastqc" ? (
                            <FileArchive size={18} />
                          ) : (
                            <FileText size={18} />
                          )}
                          {inputs.length ? (
                            <label
                              htmlFor={`selection-${encodeURIComponent(row.id)}`}
                            >
                              {row.name}
                            </label>
                          ) : (
                            <span>{row.name}</span>
                          )}
                        </div>
                        {row.sample && (
                          <details className="sample-files">
                            <summary>
                              {row.files.length}{" "}
                              {row.files.length === 1 ? "file" : "files"}
                              {inputs.length > row.files.length
                                ? " loaded · more reads on another page"
                                : ""}
                            </summary>
                            <ul className="explorer-lanes">
                              {explorerLanes(row).map((lane) => {
                                const laneSelection = selectionState(
                                  lane.paths,
                                  selected,
                                );
                                return (
                                  <li key={lane.id}>
                                    <details open>
                                      <summary>
                                        <input
                                          type="checkbox"
                                          aria-label={`Select lane ${lane.name} of ${row.name}`}
                                          checked={laneSelection.all}
                                          ref={(element) => {
                                            if (element)
                                              element.indeterminate =
                                                laneSelection.some;
                                          }}
                                          disabled={busy}
                                          onClick={(event) =>
                                            event.stopPropagation()
                                          }
                                          onChange={(event) =>
                                            void select(
                                              lane.paths,
                                              event.target.checked,
                                            )
                                          }
                                        />
                                        {lane.name}
                                        {lane.incomplete
                                          ? " · Incomplete pair"
                                          : ""}
                                      </summary>
                                      <ul>
                                        {lane.files.map((file) => (
                                          <li key={file.path}>
                                            <label>
                                              <input
                                                type="checkbox"
                                                aria-label={`Select read ${file.name}`}
                                                checked={selected.has(
                                                  file.path,
                                                )}
                                                disabled={busy}
                                                onChange={(event) =>
                                                  void select(
                                                    [file.path],
                                                    event.target.checked,
                                                  )
                                                }
                                              />
                                              <span className="sample-read">
                                                {file.read || "Read"}
                                              </span>
                                              <span title={file.path}>
                                                {file.name}
                                              </span>
                                            </label>
                                            <small>
                                              {bytes(file.size)} ·{" "}
                                              {date(
                                                new Date(
                                                  file.modified * 1000,
                                                ).toISOString(),
                                              )}
                                            </small>
                                          </li>
                                        ))}
                                      </ul>
                                    </details>
                                  </li>
                                );
                              })}
                            </ul>
                          </details>
                        )}
                      </>
                    )}
                  </td>
                  <td>
                    <span className={`filetype ${first.kind}`}>
                      {first.kind === "directory"
                        ? "Folder"
                        : first.kind === "fastq"
                          ? row.sample
                            ? "FASTQ"
                            : first.name.toLowerCase().endsWith(".gz")
                              ? "FASTQ.GZ"
                              : "FASTQ"
                          : first.kind === "fastqc"
                            ? "FastQC report"
                            : first.kind === "qcreport"
                              ? "QC JSON (validate on import)"
                              : "File"}
                    </span>
                  </td>
                  <td>
                    {row.pairing ? (
                      <div className="read-pairing">
                        <span
                          className={
                            row.pairing === "Paired-end"
                              ? "pair-label"
                              : row.pairing === "Incomplete pair" ||
                                  row.pairing === "Ambiguous naming"
                                ? "orphan-label"
                                : "subtle"
                          }
                        >
                          {!row.sample && first.read && (
                            <strong>{first.read} · </strong>
                          )}
                          {row.pairing}
                        </span>
                        <small>{row.description}</small>
                      </div>
                    ) : (
                      <span className="subtle">—</span>
                    )}
                  </td>
                  <td className="mono">{bytes(size)}</td>
                  <td className="subtle">
                    {date(new Date(modified * 1000).toISOString())}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!rows.length && (
        <Empty
          icon={FolderOpen}
          title={
            search
              ? "No matching names"
              : busy
                ? "Loading directory"
                : "This directory is empty"
          }
        >
          {search
            ? "Search by sample name or either read filename."
            : "Choose another storage root or enter a directory path above."}
        </Empty>
      )}
      <div className="file-footer">
        <span>
          <ShieldCheck size={13} />
          Source files are read-only
        </span>
        <span>
          {listing
            ? `${rows.length} entries shown · ${listing.entries.length} of ${listing.total} files and folders loaded`
            : "No directory loaded"}
        </span>
        {listing &&
          listing.next_offset !== null &&
          (listing.next_offset ?? listing.entries.length) < listing.total && (
            <button
              disabled={busy}
              onClick={() =>
                void browse(
                  listing.path,
                  listing.next_offset ?? listing.entries.length,
                )
              }
            >
              Load more
            </button>
          )}
      </div>
    </section>
  );
}
