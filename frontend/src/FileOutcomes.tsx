import type { Run } from "./types";
import { url } from "./api";

export default function FileOutcomes({ run }: { run: Run }) {
  const records = run.input_outcomes;
  if (!records?.length)
    return (
      <p className="inline-note">
        Per-FASTQ execution outcomes were not recorded for this analysis.
        Imported reports do not prove execution or integrity of source FASTQs.
      </p>
    );
  const counts = new Map<string, number>();
  for (const record of records)
    counts.set(record.state, (counts.get(record.state) || 0) + 1);
  return (
    <section
      aria-label="FASTQ execution outcomes"
      className="sample-table-section"
    >
      <h2>
        {counts.get("completed") || 0} of {records.length} inputs completed
      </h2>
      <p className="inline-note">
        {[...counts].map(([state, count]) => `${count} ${state}`).join(" · ")}.
        Completion means a usable FastQC report was parsed, independently of its
        QC warnings. Individual start/progress within a FastQC batch is not
        reported.
      </p>
      <details>
        <summary>Per-file outcomes</summary>
        <div className="table-scroll" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th>FASTQ / original path</th>
                <th>Execution state</th>
                <th>Evidence / error</th>
                <th>Reports</th>
              </tr>
            </thead>
            <tbody>
              {records.map((record) => (
                <tr key={record.id}>
                  <td>
                    <strong>{record.name}</strong>
                    <small className="mono">{record.path}</small>
                  </td>
                  <td>{record.state}</td>
                  <td>
                    {record.error ||
                      (record.state === "completed"
                        ? "Parsed FastQC result"
                        : "Awaiting recorded outcome")}
                    {record.exit_code !== null && (
                      <small>FastQC batch exit: {record.exit_code}</small>
                    )}
                  </td>
                  <td>
                    {[record.report, record.html]
                      .filter((path) =>
                        run.reports.some((report) => report.path === path),
                      )
                      .map((path) => (
                        <a
                          key={path}
                          className="button small"
                          download
                          href={url(
                            `api/runs/${run.id}/download?${new URLSearchParams({ path })}`,
                          )}
                        >
                          {path.endsWith(".html") ? "HTML" : "ZIP"}
                        </a>
                      ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
