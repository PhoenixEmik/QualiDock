import { useState } from "react";
import { api } from "./api";
import type { DeclaredFields } from "./project";

interface Preview {
  fingerprint: string;
  count: number;
  submitted_text_sha256: string;
  rows: DeclaredFields[];
}
export default function ProjectImport({
  projectId,
  saved,
}: {
  projectId: string;
  saved: () => void;
}) {
  const [format, setFormat] = useState("csv"),
    [content, setContent] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const submit = async (confirm: boolean) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<Preview & { reused?: boolean }>(
        `api/projects/${projectId}/samples/import`,
        {
          method: "POST",
          body: JSON.stringify({
            format,
            content,
            ...(confirm && preview ? { fingerprint: preview.fingerprint } : {}),
          }),
        },
      );
      if (confirm) {
        setPreview(null);
        setContent("");
        setNotice(
          `${result.count} sample records ${result.reused ? "already imported" : "imported"}.`,
        );
        saved();
      } else setPreview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed.");
      if (confirm) setPreview(null);
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="form-section project-import">
      <summary>Import sample metadata</summary>
      <p className="inline-note">
        UTF-8 CSV or JSON, at most 1 MiB / 500 rows. Imports create declared
        sample records; they do not auto-match FASTQs or overwrite existing
        samples.
      </p>
      <p className="inline-note">
        CSV headers: display_name, declared_identifier, assay, library_type,
        expected_yield_metric, expected_yield_minimum, notes. JSON uses the same
        declared fields as the API, with optional expected_yield.
      </p>
      <div className="project-actions">
        <label className="field-label">
          Metadata format
          <select
            value={format}
            disabled={busy}
            onChange={(e) => {
              setFormat(e.target.value);
              setPreview(null);
            }}
          >
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </select>
        </label>
        <label className="field-label">
          Metadata file
          <input
            type="file"
            accept=".csv,.json,text/csv,application/json"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setError("");
              setPreview(null);
              if (file.size > 1024 ** 2) {
                setError("Metadata file exceeds 1 MiB.");
                return;
              }
              setFormat(file.name.endsWith(".json") ? "json" : "csv");
              void file
                .text()
                .then(setContent)
                .catch(() => setError("Unable to read metadata file."));
            }}
          />
        </label>
      </div>
      <label className="field-label">
        Metadata content
        <textarea
          className="wide-input"
          rows={5}
          value={content}
          disabled={busy}
          maxLength={1024 ** 2}
          onChange={(e) => {
            setContent(e.target.value);
            setPreview(null);
          }}
        />
      </label>
      <button
        className="button"
        disabled={busy || !content}
        onClick={() => void submit(false)}
      >
        Preview metadata import
      </button>
      {preview && (
        <>
          <p>
            {preview.count} new sample records. Submitted UTF-8 text SHA-256:{" "}
            <code className="project-hash">
              {preview.submitted_text_sha256}
            </code>
          </p>
          <div className="table-scroll" tabIndex={0}>
            <table aria-label="Sample import preview">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Declared ID</th>
                  <th>Assay</th>
                  <th>Expectation</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.slice(0, 100).map((row, i) => (
                  <tr key={i}>
                    <td>{row.display_name}</td>
                    <td>{row.declared_identifier || "Unknown"}</td>
                    <td>{row.assay || "Unknown"}</td>
                    <td>
                      {row.expected_yield
                        ? `${row.expected_yield.minimum} ${row.expected_yield.metric}`
                        : "Unknown"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.count > 100 && (
            <p className="inline-note">
              First 100 rows shown. Review the source metadata for all{" "}
              {preview.count} rows before confirming.
            </p>
          )}
          <button
            className="button primary"
            disabled={busy}
            onClick={() => void submit(true)}
          >
            Confirm import of {preview.count} samples
          </button>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
    </details>
  );
}
