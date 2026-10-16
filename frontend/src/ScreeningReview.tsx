import { useEffect, useMemo, useState } from "react";
import type { Run } from "./types";
import type { DeliveryData } from "./delivery";
import type { ScreeningConfig, ScreeningMetrics } from "./screening";
import { taxonomyIds } from "./screening";
import { api, url } from "./api";
import { quantity } from "./delivery";
import { exportModule, type ExportMode } from "./rawExport";
import { saveFile } from "./AnalyticsChart";
import ExportModeSelect from "./ExportModeSelect";

export default function ScreeningReview({
  run,
  data,
  refresh,
}: {
  run: Run;
  data: DeliveryData;
  refresh: () => void;
}) {
  const [open, setOpen] = useState(false),
    [config, setConfig] = useState<ScreeningConfig | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const [databaseId, setDatabaseId] = useState(""),
    [assay, setAssay] = useState(data.assay),
    [expected, setExpected] = useState(""),
    [threads, setThreads] = useState(1);
  const [selection, setSelection] = useState<Set<string> | null>(null),
    [fileId, setFileId] = useState("");
  const [metrics, setMetrics] = useState<ScreeningMetrics | null>(null),
    [search, setSearch] = useState(""),
    [limit, setLimit] = useState(100),
    [mode, setMode] = useState<ExportMode>("spreadsheet");
  const selected = data.files
    .map((file) => file.file_id)
    .filter((id) => selection === null || selection.has(id));
  const record = run.screening,
    active = !!record && ["queued", "running"].includes(record.state);
  const availableFiles =
    record?.files.filter((file) => file.metrics_artifact) || [];
  const file =
    availableFiles.find((file) => file.id === fileId) || availableFiles[0];
  const current = data.files.find((entry) => entry.file_id === file?.id);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api<ScreeningConfig>("api/screening")
      .then((value) => {
        if (!cancelled) {
          setConfig(value);
          setDatabaseId(
            (previous) =>
              previous || value.databases.find((db) => db.available)?.id || "",
          );
        }
      })
      .catch((error) => {
        if (!cancelled) setError((error as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);
  useEffect(() => {
    setMetrics(null);
    if (!open || active || !file) return;
    let cancelled = false;
    setLoading(true);
    api<ScreeningMetrics>(
      `api/runs/${run.id}/screening-metrics?${new URLSearchParams({ file_id: file.id })}`,
    )
      .then((value) => {
        if (!cancelled) {
          setMetrics(value);
          setLimit(100);
        }
      })
      .catch((error) => {
        if (!cancelled) setError((error as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, active, file?.id, record?.task_id, run.id]);
  const perform = async (task: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await task();
      refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const start = () =>
    perform(() =>
      api(`api/runs/${run.id}/screening`, {
        method: "POST",
        body: JSON.stringify({
          file_ids: selected,
          database_id: databaseId,
          threads,
          assay: assay || "Unspecified",
          expected_taxids: taxonomyIds(expected),
        }),
      }),
    );
  const rows = useMemo(
    () =>
      metrics?.rows.filter(
        (row) =>
          !search.trim() ||
          (row.taxid + " " + row.name)
            .toLowerCase()
            .includes(search.trim().toLowerCase()),
      ) || [],
    [metrics, search],
  );
  const exportRows = (extension: "csv" | "tsv") => {
    if (metrics)
      saveFile(
        exportModule(
          { columns: metrics.columns, rows: rows.map((row) => row.raw) },
          extension === "csv" ? "," : "\t",
          mode,
        ),
        `kraken2-${file?.id}.${extension}`,
        "text/plain;charset=utf-8",
      );
  };
  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        Optional offline screening · {record?.state || "Not evaluated"}
      </summary>
      {open && (
        <section aria-label="Optional offline screening">
          <p className="inline-note">
            Opt-in Kraken2 taxonomic evidence using an explicitly configured
            offline reference. Reads are not uploaded to remote services. Each
            FASTQ is classified independently; clade counts overlap and must not
            be summed. Results are preliminary, not proof of contamination,
            index misassignment or sample swap. FastQC overrepresented sequences
            are separate evidence.
          </p>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {config ? (
            <>
              <p>
                Kraken2: {config.tool.version || "Unavailable"}
                {config.tool.error && ` · ${config.tool.error}`}
              </p>
              {config.error && <p role="alert">{config.error}</p>}
              <div className="analytics-actions">
                <label>
                  Offline reference{" "}
                  <select
                    aria-label="Offline screening reference"
                    value={databaseId}
                    onChange={(event) => setDatabaseId(event.target.value)}
                  >
                    <option value="">
                      Choose a configured offline reference
                    </option>
                    {config.databases.map((db) => (
                      <option
                        key={db.id}
                        value={db.id}
                        disabled={!db.available}
                      >
                        {db.name} · declared {db.version}
                        {!db.available ? " · unavailable" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Assay context{" "}
                  <input
                    aria-label="Screening assay context"
                    maxLength={120}
                    value={assay}
                    onChange={(event) => setAssay(event.target.value)}
                  />
                </label>
                <label>
                  Expected taxonomy IDs (optional, exact annotation){" "}
                  <input
                    aria-label="Expected screening taxonomy IDs"
                    value={expected}
                    onChange={(event) => setExpected(event.target.value)}
                    placeholder="e.g. 4932"
                  />
                </label>
                <label>
                  CPU threads{" "}
                  <input
                    aria-label="Screening CPU threads"
                    type="number"
                    min={1}
                    max={config.max_threads}
                    value={threads}
                    onChange={(event) => setThreads(Number(event.target.value))}
                  />
                </label>
              </div>
              {!config.databases.some((db) => db.available) && (
                <p>
                  No configured offline reference is available. Core FastQC /
                  MultiQC and release checks remain usable without optional
                  screening.
                </p>
              )}
              <details>
                <summary>
                  Read files selected for screening ({selected.length})
                </summary>
                <div className="analytics-actions">
                  <button
                    className="button small"
                    onClick={() => setSelection(null)}
                  >
                    Select all screening files
                  </button>
                  <button
                    className="button small"
                    onClick={() => setSelection(new Set())}
                  >
                    Clear screening selection
                  </button>
                </div>
                <div className="analytics-selection-list">
                  {data.files.map((file) => (
                    <label key={file.file_id} title={file.path}>
                      <input
                        type="checkbox"
                        checked={selected.includes(file.file_id)}
                        onChange={(event) =>
                          setSelection((value) => {
                            const next = new Set(
                              value || data.files.map((file) => file.file_id),
                            );
                            event.target.checked
                              ? next.add(file.file_id)
                              : next.delete(file.file_id);
                            return next;
                          })
                        }
                      />
                      {file.filename} ·{" "}
                      {[file.lane, file.chunk, file.read]
                        .filter(Boolean)
                        .join(" / ")}{" "}
                      <small className="mono">{file.file_id}</small>
                    </label>
                  ))}
                </div>
              </details>
              <p className="inline-note">
                All submitted records are requested; actual processed counts are
                checked against current saved input counts. No subsampling or
                FASTQ copies. Reference SHA-256 is streamed before
                classification, which can take time for large databases. The
                existing shared CPU/memory queue and cancellation apply.
              </p>
              <button
                className="button small"
                disabled={
                  busy ||
                  active ||
                  !config.tool.compatible ||
                  !databaseId ||
                  !selected.length ||
                  ["queued", "running"].includes(run.state)
                }
                onClick={() => void start()}
              >
                Start offline screening
              </button>
            </>
          ) : (
            <p role="status">
              Detecting optional tool and configured references…
            </p>
          )}
          {record ? (
            <>
              <p role="status">
                Screening: {record.state} · {record.phase} ·{" "}
                {
                  record.files.filter((file) => file.state === "completed")
                    .length
                }{" "}
                of {record.total_files} files with confirmed count coverage
              </p>
              <p>
                {record.assay} · declared reference {record.database.name} ·{" "}
                {record.database.version}
              </p>
              <p className="inline-note">
                Declared reference source: {record.database.source}. Declared
                taxonomy coverage is not an independently verified complete
                species inventory. Unclassified reads do not establish absence
                or a clean sample.
              </p>
              {record.expected_taxids.length > 0 && (
                <p>
                  Declared expected tax IDs: {record.expected_taxids.join(", ")}
                  . Not explicitly listed in this reference's declared coverage:{" "}
                  {record.expected_taxids
                    .filter(
                      (id) => !record.database.reference_taxids.includes(id),
                    )
                    .join(", ") || "None"}
                  . Taxonomy annotations do not infer lineages or a sample
                  identity.
                </p>
              )}
              {record.error && <p className="error">{record.error}</p>}
              <div className="analytics-actions">
                {active && (
                  <button
                    className="button small danger"
                    disabled={busy}
                    onClick={() =>
                      void perform(() =>
                        api(`api/runs/${run.id}/screening/cancel`, {
                          method: "POST",
                          body: "{}",
                        }),
                      )
                    }
                  >
                    Cancel offline screening
                  </button>
                )}
                <button className="button small" onClick={refresh}>
                  Refresh screening evidence
                </button>
                {run.reports.some(
                  (report) => report.path === record.artifact,
                ) && (
                  <a
                    className="button small"
                    download
                    href={url(
                      `api/runs/${run.id}/download?${new URLSearchParams({ path: record.artifact })}`,
                    )}
                  >
                    Screening JSON
                  </a>
                )}
              </div>
              <div className="table-scroll" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th>FASTQ</th>
                      <th>Execution / coverage</th>
                      <th>Processed / source denominator</th>
                      <th>Classified / unclassified records</th>
                    </tr>
                  </thead>
                  <tbody>
                    {record.files.map((row) => (
                      <tr key={row.id}>
                        <td title={row.path}>
                          {row.name}
                          <small className="mono">{row.id}</small>
                        </td>
                        <td>
                          {row.state} / {row.coverage.replaceAll("_", " ")}
                          <small>{row.error}</small>
                          {row.report_artifact &&
                            run.reports.some(
                              (report) => report.path === row.report_artifact,
                            ) && (
                              <a
                                download
                                href={url(
                                  `api/runs/${run.id}/download?${new URLSearchParams({ path: row.report_artifact })}`,
                                )}
                              >
                                Original TSV
                              </a>
                            )}
                          {run.reports.some(
                            (report) =>
                              report.path ===
                              record.artifact.replace(
                                /screening\.json$/,
                                row.id + ".log",
                              ),
                          ) && (
                            <a
                              download
                              href={url(
                                `api/runs/${run.id}/download?${new URLSearchParams({ path: record.artifact.replace(/screening\.json$/, row.id + ".log") })}`,
                              )}
                            >
                              Tool log
                            </a>
                          )}
                        </td>
                        <td>
                          {quantity(row.records_processed)} /{" "}
                          {quantity(row.known_input_records)}
                          <small>
                            {row.screened_fraction === null
                              ? "Fraction not evaluated"
                              : `${quantity(row.screened_fraction * 100)}% of reported input records`}
                          </small>
                          <small>{row.denominator_source}</small>
                        </td>
                        <td>
                          {quantity(row.classified_records)} /{" "}
                          {quantity(row.unclassified_records)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!active && !!availableFiles.length && (
                <>
                  <div className="analytics-actions">
                    <label>
                      Read-file evidence{" "}
                      <select
                        aria-label="Screening read-file evidence"
                        value={file?.id || ""}
                        onChange={(event) => setFileId(event.target.value)}
                      >
                        {availableFiles.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name} · {row.id.slice(-8)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Search taxon{" "}
                      <input
                        type="search"
                        aria-label="Search screening taxon"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                      />
                    </label>
                  </div>
                  <p className="mono">{file?.path}</p>
                  <p className="inline-note">
                    {current?.screening_snapshot_matches
                      ? "Source metadata matches this saved screening evidence at the last check."
                      : "Source metadata changed or is unavailable; this saved classification is historical."}
                  </p>
                  {loading && (
                    <p role="status">Loading saved taxonomic evidence…</p>
                  )}
                  {metrics &&
                    metrics.file_id === file?.id &&
                    metrics.source_task_id === record.task_id && (
                      <>
                        <p className="inline-note">
                          {metrics.denominator} Reported percentages retain the
                          tool's original precision. Expected annotations are
                          exact taxonomy-ID matches, not automatic contamination
                          decisions.
                        </p>
                        <div className="analytics-actions">
                          <ExportModeSelect value={mode} change={setMode} />
                          <button
                            className="button small"
                            onClick={() => exportRows("csv")}
                          >
                            Export screening CSV
                          </button>
                          <button
                            className="button small"
                            onClick={() => exportRows("tsv")}
                          >
                            Export screening TSV
                          </button>
                          {file?.report_artifact && (
                            <a
                              className="button small"
                              download
                              href={url(
                                `api/runs/${run.id}/download?${new URLSearchParams({ path: file.report_artifact })}`,
                              )}
                            >
                              Original Kraken2 report
                            </a>
                          )}
                        </div>
                        <div className="table-scroll" tabIndex={0}>
                          <table aria-label="Kraken2 taxonomic assignments">
                            <thead>
                              <tr>
                                {metrics.columns.map((column) => (
                                  <th key={column}>{column}</th>
                                ))}
                                <th>Declared expected ID</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rows.slice(0, limit).map((row) => (
                                <tr key={row.taxid}>
                                  {row.raw.map((value, index) => (
                                    <td key={index}>{value}</td>
                                  ))}
                                  <td>
                                    {metrics.expected_taxids.includes(row.taxid)
                                      ? "Explicitly listed"
                                      : "—"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {!rows.length && (
                          <p role="status">
                            {metrics.rows.length
                              ? "No taxa match this search."
                              : "No taxon rows were reported. Zero-read percentages are unavailable; this does not establish absence of a taxon."}
                          </p>
                        )}
                        {rows.length > limit && (
                          <button
                            className="button small"
                            onClick={() => setLimit((value) => value + 200)}
                          >
                            Show more taxon rows
                          </button>
                        )}
                      </>
                    )}
                </>
              )}
              <details>
                <summary>
                  Reference file checksums ({record.database_files.length})
                </summary>
                {record.database_files.map((entry) => (
                  <p key={entry.name} className="mono">
                    {entry.name} · {entry.bytes.toLocaleString()} bytes ·
                    SHA-256 {entry.sha256}
                  </p>
                ))}
              </details>
            </>
          ) : (
            <p role="status">Not evaluated. No screening task was requested.</p>
          )}
        </section>
      )}
    </details>
  );
}
