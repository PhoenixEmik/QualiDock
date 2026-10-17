import { useState } from "react";
import { url } from "./api";
import ReportedTable from "./ReportedTable";
import type { Run } from "./types";

export default function PicardResults({ run }: { run: Run }) {
  const rows = run.qc?.results || [];
  const [selected, setSelected] = useState("");
  const row = rows.find((r) => r.id === selected) || rows[0];
  const data = row?.state === "completed" ? row.picard : undefined;
  const registered = new Set(run.reports.map((r) => r.path));
  const columns = [
    "PAIR_ORIENTATION",
    "READ_PAIRS",
    "MEDIAN_INSERT_SIZE",
    "MEAN_INSERT_SIZE",
    "STANDARD_DEVIATION",
    "LIBRARY",
  ];
  const labels = [
    "Orientation",
    "Read-pair observations",
    "Median (bp)",
    "Mean (bp, trimmed)",
    "SD (bp, trimmed)",
    "Population",
  ];
  return (
    <section className="form-section" aria-label="Picard insert-size results">
      <h2>Picard insert-size QC</h2>
      <p className="inline-note">
        Picard {run.tools?.picard?.version || "version unavailable"} · Java{" "}
        {run.tools?.java?.version || "version unavailable"}. Original upstream
        calculations and reported precision; no read lengths or unique molecule
        counts are inferred.
      </p>
      <label className="field-label" htmlFor="insert-result-input">
        Alignment file
      </label>
      <select
        id="insert-result-input"
        className="wide-input"
        value={row?.id || ""}
        onChange={(e) => setSelected(e.target.value)}
      >
        {rows.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name} · {r.state} · {r.path}
          </option>
        ))}
      </select>
      {row && (
        <>
          <h3>{row.name}</h3>
          <p className="mono output-destination">{row.path}</p>
          <p role="status">
            {row.state}
            {row.error ? ` · ${row.error}` : ""}
          </p>
        </>
      )}
      {data && (
        <>
          {data.status === "unavailable" ? (
            <p role="status">
              Picard reported no qualifying paired observations (
              {data.mapped_pairs_reported}). No insert-size metrics or histogram
              were produced; no distribution is inferred for single-end data.
            </p>
          ) : (
            <>
              <p className="inline-note">
                BAM-wide rows have blank sample/library fields. Named rows are
                Picard's library populations; do not sum library and all-read
                rows. Mean, SD and histogram use the original median +{" "}
                {data.deviations} × MAD cutoff. Orientation categories below
                fraction {data.minimum_orientation_fraction} can be absent.
                Read-pair observations after tool filtering are not independent
                biological molecules. Missing values and ? are unavailable.
              </p>
              <div
                className="table-scroll"
                tabIndex={0}
                role="region"
                aria-label="Insert-size summary"
              >
                <table>
                  <thead>
                    <tr>
                      {labels.map((label) => (
                        <th key={label}>{label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.metrics.rows.map((values, i) => (
                      <tr key={i}>
                        {columns.map((column, j) => {
                          const value =
                            values[data.metrics.columns.indexOf(column)];
                          const empty =
                            values[
                              data.metrics.columns.indexOf("READ_PAIRS")
                            ] === "0" &&
                            j >= 2 &&
                            j <= 4;
                          const display =
                            column === "LIBRARY"
                              ? value
                                ? `${values[data.metrics.columns.indexOf("SAMPLE")] || "Sample unavailable"} / ${value}`
                                : "All reads"
                              : empty || !value || value === "?"
                                ? "Unavailable"
                                : value;
                          return j ? (
                            <td key={column}>{display}</td>
                          ) : (
                            <th key={column} scope="row">
                              {display}
                            </th>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {data.metrics.total_rows > data.metrics.rows.length && (
                <p className="inline-note">
                  Showing {data.metrics.rows.length} of{" "}
                  {data.metrics.total_rows} rows; original metrics retain every
                  reported population.
                </p>
              )}
              <details>
                <summary>Original metrics and histogram data</summary>
                <ReportedTable
                  label="Original Picard metrics"
                  data={data.metrics}
                />
                <ReportedTable
                  label="Original insert-size histogram"
                  data={data.histogram}
                  open
                />
              </details>
            </>
          )}
          <p className="inline-note">
            Insert size uses Picard's qualifying alignment/template
            observations. It is not read length; genomic RNA-seq spans can
            include introns. Results depend on duplicate/orientation/tail
            filtering and library preparation.
          </p>
          <details>
            <summary>Execution settings</summary>
            <pre>{JSON.stringify(run.qc?.options, null, 2)}</pre>
            <p>
              Java maximum heap: {data.heap_mb} MiB, with additional headroom
              under the shared process-tree limit.{" "}
              {data.rscript_version
                ? `Rscript ${data.rscript_version}.`
                : "PDF was not requested; original numeric histogram is retained when observations exist."}
            </p>
          </details>
          <div className="inline-actions">
            {Object.entries(data.reports)
              .filter(([, path]) => registered.has(path))
              .map(([name, path]) => (
                <a
                  key={name}
                  download
                  className="button small"
                  href={url(
                    `api/runs/${run.id}/download?path=${encodeURIComponent(path)}`,
                  )}
                >
                  Download {name.replaceAll("_", " ")}
                </a>
              ))}
          </div>
        </>
      )}
    </section>
  );
}
