import type { ReportedTable as ReportedTableData } from "./types";

export default function ReportedTable({
  label,
  data,
  open = false,
}: {
  label: string;
  data: ReportedTableData;
  open?: boolean;
}) {
  return (
    <details open={open}>
      <summary>
        {label} ({data.total_rows} reported rows)
      </summary>
      {data.total_rows > data.rows.length && (
        <p className="inline-note">
          Showing {data.rows.length} rows. Download the original file for all
          reported values.
        </p>
      )}
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label={label}
      >
        <table>
          <thead>
            <tr>
              {data.columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((values, i) => (
              <tr key={i}>
                {values.map((v, j) =>
                  j ? (
                    <td key={j}>{v || "Unavailable"}</td>
                  ) : (
                    <th key={j} scope="row">
                      {v}
                    </th>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
