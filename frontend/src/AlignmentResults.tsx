import { url } from "./api";
import type { Run } from "./types";

export default function AlignmentResults({ run }: { run: Run }) {
  return (
    <section className="form-section" aria-label="SAMtools QC results">
      <h2>SAMtools alignment QC</h2>
      <p className="inline-note">
        SAMtools {run.tools?.samtools?.version || "version unavailable"}.
        quickcheck checks the header and EOF only; it is not complete alignment
        integrity validation. flagstat and stats perform separate record scans.
        No sorting, indexing or source modification.
      </p>
      <p className="inline-note">
        flagstat counts alignment segments in nonexclusive flag categories,
        separated by the input QC-fail flag. These are not independent read-pair
        counts. Reported mapped percentages use total segments; primary mapped
        uses primary segments; properly paired and singleton percentages use
        paired-in-sequencing segments, separately in each QC column. SAMtools
        stats excludes secondary/supplementary alignments from raw total
        sequences. No Q20/Q30 base percentages are inferred.
      </p>
      {run.qc?.reference && (
        <details>
          <summary>Approved CRAM reference</summary>
          <p>{run.qc.reference.id}</p>
          <p className="mono output-destination">{run.qc.reference.path}</p>
          <p>{run.qc.reference.identity}</p>
          <p className="mono output-destination">
            FAI SHA-256: {run.qc.reference.fai_sha256}
          </p>
        </details>
      )}
      {run.qc?.results.map((row) => (
        <section key={row.id} className="form-section">
          <h3>{row.name}</h3>
          <p className="mono output-destination">{row.path}</p>
          <p role="status">
            {row.state}
            {row.error ? ` · ${row.error}` : ""}
          </p>
          {row.state === "completed" && row.alignment && (
            <>
              <p>
                {row.alignment.format} · quickcheck: {row.alignment.quickcheck}
              </p>
              {(
                [
                  ["Flag statistics", row.alignment.flagstat],
                  ["Summary statistics", row.alignment.stats],
                ] as const
              ).map(([label, table]) => (
                <details key={label} open={label === "Flag statistics"}>
                  <summary>{label}</summary>
                  <div
                    className="table-scroll"
                    role="region"
                    aria-label={`${label} ${row.name}`}
                    tabIndex={0}
                  >
                    <table>
                      <thead>
                        <tr>
                          {table.columns.map((c) => (
                            <th key={c}>{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {table.rows.map((values, i) => (
                          <tr key={i}>
                            {values.map((value, j) =>
                              j ? (
                                <td key={j}>{value || "Unavailable"}</td>
                              ) : (
                                <th key={j} scope="row">
                                  {value}
                                </th>
                              ),
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              ))}
              <div className="inline-actions">
                {Object.entries(row.alignment.reports).map(([name, path]) => (
                  <a
                    key={name}
                    className="button small"
                    href={url(
                      `api/runs/${run.id}/download?path=${encodeURIComponent(path)}`,
                    )}
                  >
                    Download original {name}
                  </a>
                ))}
              </div>
            </>
          )}
        </section>
      ))}
    </section>
  );
}
