import type { Sample } from "./types";
import { findModule, tableOnly } from "./qc";
import QualityChart from "./QualityChart";

export default function QcModule({
  sample,
  metric,
}: {
  sample: Sample;
  metric: string;
}) {
  const module = findModule(sample, metric);
  if (!module || module.available === false)
    return (
      <p className="inline-note">
        This module is unavailable in this FastQC result.
      </p>
    );
  const table = (
    <div className="table-scroll qc-data-table">
      <table>
        <caption>Values reported by FastQC</caption>
        <thead>
          <tr>
            {module.columns.map((column, index) => (
              <th key={index}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {module.rows.map((row, index) => (
            <tr key={index}>
              {row.map((value, column) => (
                <td key={column} className="mono">
                  {value || "Unavailable"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return (
    <>
      {module.metadata?.map((row, index) => (
        <p className="inline-note" key={index}>
          {row.join(": ")}
        </p>
      ))}
      {!module.rows.length ? (
        <p className="inline-note">
          {metric === "Overrepresented sequences"
            ? "No overrepresented sequences were reported."
            : "FastQC reported no data rows for this module."}{" "}
          Module status: {module.status.toUpperCase()}.
        </p>
      ) : tableOnly(module) ? (
        table
      ) : (
        <>
          <QualityChart sample={sample} metric={metric} />
          <details className="qc-raw-data">
            <summary>Show exact reported values</summary>
            {table}
          </details>
        </>
      )}
      {module.summary_status && module.summary_status !== module.status && (
        <p className="error">
          summary.txt reports {module.summary_status.toUpperCase()};
          fastqc_data.txt reports {module.status.toUpperCase()}. Both source
          reports are preserved.
        </p>
      )}
    </>
  );
}
