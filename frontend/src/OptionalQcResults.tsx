import { url } from "./api";
import type { Run } from "./types";

const metrics: [string, string, string][] = [
  ["reads", "Reads", "reads"],
  ["bases", "Bases", "nt"],
  ["n50", "Read length N50", "nt"],
  ["mean_length", "Mean read length (reported integer)", "nt"],
  ["median_length", "Median read length", "nt"],
  ["shortest", "Shortest read", "nt"],
  ["longest", "Longest read", "nt"],
  ["mean_quality", "Mean read quality", "Phred"],
  ["median_quality", "Median read quality", "Phred"],
];

export default function OptionalQcResults({ run }: { run: Run }) {
  return (
    <section className="form-section" aria-label="nanoq QC results">
      <h2>nanoq long-read QC</h2>
      <p className="inline-note">
        nanoq {run.tools?.nanoq?.version || "version unavailable"} ·
        Report-only, no filtering. Read qualities summarize per-read error
        probabilities; they are not FastQC per-base means or Q20/Q30 base
        percentages. Quality is evaluated by nanoq using its Phred+33
        convention. No platform identity is inferred.
      </p>
      {run.qc?.results.map((row) => (
        <section
          key={row.id}
          className="form-section"
          aria-label={`QC result ${row.name}`}
        >
          <h3>{row.name}</h3>
          <p className="mono output-destination">{row.path}</p>
          <p role="status">
            {row.state}
            {row.error ? ` · ${row.error}` : ""}
          </p>
          {row.state === "completed" && row.summary && (
            <>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Reported value</th>
                      <th>Unit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.map(([key, label, unit]) => (
                      <tr key={key}>
                        <th scope="row">{label}</th>
                        <td>
                          {typeof row.summary?.[key] === "number"
                            ? String(row.summary[key])
                            : "Unavailable"}
                        </td>
                        <td>{unit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <details>
                <summary>Reported threshold counts</summary>
                <p>
                  Strictly greater than each threshold, as implemented by nanoq
                  0.10.0. Counts refer to reads.
                </p>
                {(["length_thresholds", "quality_thresholds"] as const).map(
                  (key) => (
                    <div className="table-scroll" key={key}>
                      <table>
                        <caption>
                          {key === "length_thresholds"
                            ? "Read length (nt)"
                            : "Read quality (Phred)"}
                        </caption>
                        <thead>
                          <tr>
                            <th>Threshold</th>
                            <th>Reads</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(row.summary?.[key] || {}).map(
                            ([threshold, count]) => (
                              <tr key={threshold}>
                                <th scope="row">&gt; {threshold}</th>
                                <td>{count}</td>
                              </tr>
                            ),
                          )}
                        </tbody>
                      </table>
                    </div>
                  ),
                )}
              </details>
              <a
                className="button small"
                href={url(
                  `api/runs/${run.id}/download?path=${encodeURIComponent(row.report)}`,
                )}
              >
                Download original JSON
              </a>
              {row.source_sha256 && (
                <details>
                  <summary>Source provenance</summary>
                  <p className="mono output-destination">
                    SHA-256: {row.source_sha256}
                  </p>
                </details>
              )}
            </>
          )}
        </section>
      ))}
      <p className="inline-note">
        MultiQC aggregation is unavailable for this JSON adapter. MultiQC's
        nanoq module expects a text report; the original JSON remains available.
      </p>
    </section>
  );
}
