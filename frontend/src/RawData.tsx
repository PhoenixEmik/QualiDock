import { useMemo, useState } from "react";
import type { Module } from "./types";
import { exportFilename, exportModule, type ExportMode } from "./rawExport";
import ExportModeSelect from "./ExportModeSelect";

export default function RawData({
  module,
  sampleName,
  initiallyOpen = false,
}: {
  module: Module;
  sampleName: string;
  initiallyOpen?: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const [page, setPage] = useState(0);
  const [exportMode, setExportMode] = useState<ExportMode>("spreadsheet");
  const start = Math.min(
    page * 200,
    Math.max(0, Math.floor((module.rows.length - 1) / 200) * 200),
  );
  const download = (extension: "csv" | "tsv") => {
    const blob = new Blob(
      [exportModule(module, extension === "csv" ? "," : "\t", exportMode)],
      {
        type: `${extension === "csv" ? "text/csv" : "text/tab-separated-values"};charset=utf-8`,
      },
    );
    const source = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = source;
    anchor.download = exportFilename(sampleName, module.name, extension);
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(source), 1000);
  };
  const width = useMemo(
    () =>
      open
        ? module.rows.reduce(
            (max, row) => Math.max(max, row.length),
            module.columns.length,
          )
        : 0,
    [open, module],
  );
  return (
    <details
      className="qc-raw-data"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        Raw Data · {sampleName} · {module.rows.length.toLocaleString()} rows
      </summary>
      {open && (
        <>
          <div className="qc-export-actions">
            <span>
              Original column names and values; blanks are unavailable.
            </span>
            <ExportModeSelect value={exportMode} change={setExportMode} />
            <button className="button small" onClick={() => download("csv")}>
              Export CSV
            </button>
            <button className="button small" onClick={() => download("tsv")}>
              Export TSV
            </button>
          </div>
          <div
            className="table-scroll qc-data-table"
            tabIndex={0}
            role="region"
            aria-label={`Raw FastQC data for ${sampleName}: ${module.name}`}
          >
            <table>
              <caption>Values reported by FastQC</caption>
              <thead>
                <tr>
                  {Array.from({ length: width }, (_, i) => (
                    <th key={i}>{module.columns[i] ?? "Unlabelled field"}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {module.rows.slice(start, start + 200).map((row, i) => (
                  <tr key={i}>
                    {Array.from({ length: width }, (_, j) => (
                      <td key={j} className="mono">
                        {row[j] === undefined || row[j] === "" ? (
                          <span className="subtle">Unavailable</span>
                        ) : (
                          row[j]
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {module.rows.length > 200 && (
            <div className="qc-export-actions" aria-label="Raw data pages">
              <span>
                Rows {start + 1}–{Math.min(start + 200, module.rows.length)} of{" "}
                {module.rows.length}. Exports include all rows.
              </span>
              <button
                className="button small"
                disabled={start === 0}
                onClick={() => setPage((value) => value - 1)}
              >
                Previous rows
              </button>
              <button
                className="button small"
                disabled={start + 200 >= module.rows.length}
                onClick={() => setPage((value) => value + 1)}
              >
                Next rows
              </button>
            </div>
          )}
        </>
      )}
    </details>
  );
}
