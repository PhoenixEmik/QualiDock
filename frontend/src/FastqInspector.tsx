import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { inspectorRequest, type FastqPreview } from "./inspector";
import type { DatasetReference } from "./types";

export default function FastqInspector({
  paths,
  references = [],
}: {
  paths: string[];
  references?: DatasetReference[];
}) {
  const [open, setOpen] = useState(false),
    [count, setCount] = useState(5),
    [paired, setPaired] = useState(false);
  const [data, setData] = useState<FastqPreview | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const pending = useRef<AbortController | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => () => pending.current?.abort(), []);
  const load = async () => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setOpen(true);
    setLoading(true);
    setData(null);
    setError("");
    try {
      const response = await api<FastqPreview>("api/inspector", {
        method: "POST",
        body: JSON.stringify(
          inspectorRequest(paths, references, count, paired),
        ),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) setData(response);
    } catch (err) {
      if (!controller.signal.aborted)
        setError(
          err instanceof Error ? err.message : "FASTQ preview unavailable",
        );
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  };
  return (
    <div className="fastq-inspector">
      <button
        ref={button}
        className="button small"
        disabled={!paths.length || paths.length > 2}
        aria-expanded={open}
        onClick={() => void load()}
      >
        Inspect FASTQ
      </button>
      {paths.length > 2 && <small>Select one or two files to inspect.</small>}
      {open && (
        <section
          className="inspector-panel"
          aria-label="FASTQ Inspector"
          aria-busy={loading}
        >
          <div className="section-heading">
            <h2>FASTQ Inspector</h2>
            <button
              className="text-button"
              onClick={() => {
                pending.current?.abort();
                setOpen(false);
                setData(null);
                button.current?.focus();
              }}
            >
              Close Inspector
            </button>
          </div>
          <p className="inline-note">
            Bounded first-record preview, not a random sample or comprehensive
            QC. Quality characters are shown unchanged; quality encoding is not
            inferred. Full-file structure, gzip integrity and pairing are not
            validated.
          </p>
          <ol>
            {paths.map((path, i) => (
              <li key={path} className="mono">
                {paths.length === 2 ? `File ${i + 1}: ` : ""}
                {path}
              </li>
            ))}
          </ol>
          <div className="processing-selection">
            <label>
              Preview records{" "}
              <input
                aria-label="Preview records"
                type="number"
                min={1}
                max={20}
                value={count}
                onChange={(event) => {
                  setCount(Number(event.target.value));
                  setData(null);
                }}
              />
            </label>
            {paths.length === 2 && (
              <label>
                <input
                  type="checkbox"
                  checked={paired}
                  onChange={(event) => {
                    setPaired(event.target.checked);
                    setData(null);
                  }}
                />
                I confirm the displayed order is R1 then R2
              </label>
            )}
            <button
              className="button small"
              disabled={
                loading || !Number.isInteger(count) || count < 1 || count > 20
              }
              onClick={() => void load()}
            >
              Refresh preview
            </button>
          </div>
          {loading && <p role="status">Reading bounded preview…</p>}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {data?.paired && (
            <p role="status">
              Observed first-N pair identifiers:{" "}
              {data.pairs.length
                ? data.pairs
                    .map((row) => `#${row.ordinal} ${row.status}`)
                    .join(" · ")
                : "Unavailable"}
              . This does not establish whole-file synchronization.
            </p>
          )}
          <div className="inspector-files">
            {data?.files.map((file, i) => (
              <section
                key={file.path}
                aria-label={`Preview file ${i + 1}`}
                tabIndex={0}
              >
                <h3>
                  {paired ? `R${i + 1} · ` : ""}
                  {file.path.split("/").pop()}
                </h3>
                {file.status !== "available" && (
                  <p role="status">
                    {file.status === "empty"
                      ? "No FASTQ records."
                      : `${file.status}: ${file.error}`}
                  </p>
                )}
                {file.records.map((record) => (
                  <article key={record.ordinal} className="inspector-record">
                    <h4>
                      Read {record.ordinal} · {record.length} bases
                    </h4>
                    <dl>
                      <dt>Identifier</dt>
                      <dd>
                        <code>{record.identifier}</code>
                      </dd>
                      <dt>Sequence</dt>
                      <dd>
                        <code>{record.sequence || "(empty)"}</code>
                      </dd>
                      <dt>Quality characters</dt>
                      <dd>
                        <code>{record.quality || "(empty)"}</code>
                      </dd>
                    </dl>
                  </article>
                ))}
              </section>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
