import { useState } from "react";
import { url } from "./api";
import type { Run } from "./types";

export default function RnaQcResults({ run }: { run: Run }) {
  const rows = run.qc?.results || [];
  const [selected, setSelected] = useState("");
  const row = rows.find((r) => r.id === selected) || rows[0];
  const data = row?.state === "completed" ? row.rseqc : undefined;
  const infer = run.mode === "rseqc-infer";
  const tool = infer ? "rseqc_infer" : "rseqc_distribution";
  const registered = new Set(run.reports.map((r) => r.path));
  return (
    <section className="form-section" aria-label="RSeQC results">
      <h2>
        {infer ? "RSeQC library strandedness" : "RSeQC read distribution"}
      </h2>
      <p className="inline-note">
        RSeQC{" "}
        {run.tools?.[tool]?.suite_version ||
          run.tools?.[tool]?.version ||
          "version unavailable"}
        . Original upstream values, with no inferred library protocol or
        biological interpretation.
      </p>
      <label className="field-label" htmlFor="rna-result-input">
        Alignment file
      </label>
      <select
        id="rna-result-input"
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
          {infer ? (
            <>
              <p>
                Upstream alignment layout: <strong>{data.layout}</strong>.
                Usable alignment records sampled:{" "}
                <strong>{data.sampled_alignments}</strong>.
              </p>
              <p className="inline-note">
                Fractions describe the sampled annotation-overlapping records,
                not all input reads or fragments. “Failed to determine” includes
                ambiguous gene-strand overlaps; reads excluded before sampling
                are outside this denominator. RSeQC reports rounded fractions;
                category counts are unavailable and are not reconstructed.
              </p>
              {data.status === "unavailable" && (
                <p role="status">
                  Upstream did not report strandedness fractions for this mixed
                  or insufficient population. No fractions or protocol are
                  inferred.
                </p>
              )}
            </>
          ) : (
            <>
              <dl className="run-metadata">
                {data.totals?.map(([name, value]) => (
                  <div key={name}>
                    <dt>{name}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              <p className="inline-note">
                Total Reads counts accepted alignment records after upstream
                filtering. Tags count aligned blocks and can exceed reads; they
                are not biological fragments. Category assignment uses block
                midpoints and upstream precedence. TSS/TES windows are nested,
                so rows must not be summed. Tags/Kb is the original upstream
                value using its +1 denominator convention, not a percentage.
              </p>
            </>
          )}
          {!!data.rows.length && (
            <div
              className="table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Original RSeQC values"
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
          )}
          <details>
            <summary>Annotation and execution provenance</summary>
            <p>
              {run.qc?.annotation?.id} · SHA-256{" "}
              <span className="mono">{run.qc?.annotation?.sha256}</span>
            </p>
            <p className="mono output-destination">
              {run.qc?.annotation?.path}
            </p>
            <p>{run.qc?.annotation?.identity}</p>
            <pre>{JSON.stringify(run.qc?.options, null, 2)}</pre>
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
