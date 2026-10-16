import { useState } from "react";
import type { Run } from "./types";
import { api, url, date } from "./api";

export default function IntegrityReview({
  run,
  refresh,
}: {
  run: Run;
  refresh: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const record = run.integrity;
  const active = !!record && ["queued", "running"].includes(record.state);
  const unavailable = run.mode === "multiqc" && !run.sample_input_paths?.length;
  const act = async (mode: "full" | "quick" | "cancel") => {
    setBusy(true);
    setError("");
    try {
      await api(
        `api/runs/${run.id}/integrity${mode === "cancel" ? "/cancel" : ""}`,
        {
          method: "POST",
          body: JSON.stringify(mode === "cancel" ? {} : { mode }),
        },
      );
      refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section
      className="sample-table-section integrity-review"
      aria-label="FASTQ integrity validation"
    >
      <h2>FASTQ integrity</h2>
      <p className="inline-note">
        Read-only structural and gzip checks, source SHA-256, and exact
        normalized mate identifiers in original order. This is separate from
        FastQC module classifications. Source checksums are computed here;
        transfer verification is not performed.
      </p>
      <div className="analytics-actions">
        <button
          className="button small"
          disabled={
            busy ||
            active ||
            unavailable ||
            ["queued", "running"].includes(run.state)
          }
          onClick={() => void act("full")}
        >
          Full FASTQ validation
        </button>
        <button
          className="button small"
          disabled={
            busy ||
            active ||
            unavailable ||
            ["queued", "running"].includes(run.state)
          }
          onClick={() => void act("quick")}
        >
          Quick scan (up to 10,000 reads/file)
        </button>
        {active && (
          <button
            className="button small danger"
            disabled={busy}
            onClick={() => void act("cancel")}
          >
            Cancel validation
          </button>
        )}
        {record &&
          run.reports.some((report) => report.path === record.artifact) && (
            <a
              className="button small"
              download
              href={url(
                `api/runs/${run.id}/download?${new URLSearchParams({ path: record.artifact })}`,
              )}
            >
              Validation JSON
            </a>
          )}
      </div>
      {error && <p role="alert">{error}</p>}
      {unavailable && (
        <p className="inline-note">
          Imported reports alone cannot establish integrity of absent source
          FASTQs.
        </p>
      )}
      {!record ? (
        <p role="status">
          Not evaluated. A quick or interrupted scan never asserts unscanned
          records or mate synchronization.
        </p>
      ) : (
        <>
          <p role="status">
            {record.state} · {record.result.replaceAll("_", " ")} ·{" "}
            {record.mode} scan · validator {record.version} ·{" "}
            {record.files.filter((file) => file.state === "passed").length} of{" "}
            {record.total_files} files fully validated
          </p>
          {record.error && <p className="error">{record.error}</p>}
          {record.current_file && active && (
            <p className="mono">
              {record.current_file.path} ·{" "}
              {record.current_file.records_scanned.toLocaleString()} records
              scanned (partial)
            </p>
          )}
          {record.finished_at && (
            <p className="inline-note">Finished {date(record.finished_at)}</p>
          )}
          <details>
            <summary>File and mate evidence</summary>
            <div className="table-scroll" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th>Original FASTQ</th>
                    <th>Validation</th>
                    <th>Reads / bases scanned</th>
                    <th>Coverage / gzip CRC</th>
                    <th>Source SHA-256</th>
                  </tr>
                </thead>
                <tbody>
                  {record.files.map((file) => (
                    <tr key={file.id}>
                      <td className="mono">{file.path}</td>
                      <td>
                        {file.state}
                        <small>{file.error}</small>
                      </td>
                      <td>
                        {file.records_scanned.toLocaleString()} reads /{" "}
                        {file.bases_scanned.toLocaleString()} bases
                      </td>
                      <td>
                        {file.coverage} / {file.gzip_crc}
                      </td>
                      <td className="mono">{file.sha256 || "Not evaluated"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!record.pairs.length && (
              <p>
                No confirmed read pairs to compare. Single-end and unpaired
                files remain independent.
              </p>
            )}
            {record.pairs.map((pair) => (
              <p key={pair.id}>
                {pair.id}: {pair.state}{" "}
                {pair.error ||
                  "Matching counts and identifier order; no biological sample identity is inferred."}
              </p>
            ))}
          </details>
        </>
      )}
    </section>
  );
}
