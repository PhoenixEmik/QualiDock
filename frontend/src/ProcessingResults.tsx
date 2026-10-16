import { useState } from "react";
import type { Run, Sample } from "./types";
import { url } from "./api";
import { downloadDataset, retention } from "./processing";
import QcModule from "./QcModule";
const metrics = [
  "Per base sequence quality",
  "Per sequence quality scores",
  "Per base sequence content",
  "Per base N content",
  "Per sequence GC content",
  "Sequence Length Distribution",
  "Sequence Duplication Levels",
  "Adapter Content",
];
const summaryMetrics = [
  ["total_reads", "Total reads"],
  ["total_bases", "Total bases"],
  ["q20_rate", "Q20 bases (%)"],
  ["q30_rate", "Q30 bases (%)"],
  ["gc_content", "GC content (%)"],
] as const;
export default function ProcessingResults({
  run,
  samples,
}: {
  run: Run;
  samples: Sample[];
}) {
  const [unitId, setUnitId] = useState(""),
    [read, setRead] = useState(0),
    [metric, setMetric] = useState(metrics[0]);
  const processing = run.processing;
  if (!processing) return null;
  const unit =
    processing.units.find((unit) => unit.id === unitId) || processing.units[0];
  const before = unit?.fastp?.summary.before_filtering,
    after = unit?.fastp?.summary.after_filtering;
  const retained = retention(before?.total_reads, after?.total_reads);
  const raw = samples.find(
      (sample) => sample.id === unit?.raw_qc?.[read]?.report,
    ),
    processed = samples.find(
      (sample) => sample.id === unit?.processed_qc?.[read]?.report,
    );
  return (
    <section className="processing-results" aria-label="Processing results">
      <h2>
        {run.mode === "fastp" ? "Before / after processing" : "SeqKit results"}
      </h2>
      <label>
        Input dataset
        <select
          value={unit?.id || ""}
          onChange={(event) => {
            setUnitId(event.target.value);
            setRead(0);
          }}
        >
          {processing.units.map((row) => (
            <option key={row.id} value={row.id}>
              {row.inputs.map((path) => path.split("/").pop()).join(" + ")}
              {row.lane ? ` · ${row.lane}` : ""} · {row.state}
            </option>
          ))}
        </select>
      </label>
      {unit && (
        <>
          <details>
            <summary>Input provenance and execution parameters</summary>
            <ul>
              {unit.inputs.map((path) => (
                <li key={path} className="mono">
                  {path}
                </li>
              ))}
            </ul>
            <pre>{JSON.stringify(processing.options, null, 2)}</pre>
            <p>
              Tool:{" "}
              {run.tools?.[run.mode === "fastp" ? "fastp" : "seqkit"]
                ?.version || "Unavailable"}
              . Original files are read-only.
            </p>
          </details>
          {unit.error && (
            <p className="error" role="alert">
              {unit.error}
            </p>
          )}
          {before && after && (
            <>
              <p className="inline-note">
                {unit.inputs.length === 2
                  ? "Statistics cover both mates together; total reads counts R1 and R2 reads, not read pairs."
                  : "Statistics cover this single-end input."}{" "}
                Percentages below are the fastp-reported rates × 100. FastQC
                does not supply Q20/Q30 base percentages.
              </p>
              <div className="table-scroll">
                <table className="processing-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Raw · before filtering</th>
                      <th>Processed · after filtering</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summaryMetrics.map(([key, label]) => (
                      <tr key={key}>
                        <th>{label}</th>
                        {[before, after].map((stage, i) => (
                          <td key={i}>
                            {typeof stage[key] === "number"
                              ? key.endsWith("_rate") || key === "gc_content"
                                ? `${(stage[key] * 100).toPrecision(8)}%`
                                : stage[key].toLocaleString()
                              : "Unavailable"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p>
                {retained
                  ? `${retained.retained.toFixed(2)}% retained · ${retained.removed.toFixed(2)}% removed (reported read counts).`
                  : "Retention percentage unavailable (zero or missing raw read count)."}
              </p>
              <details>
                <summary>
                  Original fastp filtering and trimming statistics
                </summary>
                <pre>
                  {JSON.stringify(
                    {
                      filtering_result: unit.fastp?.filtering_result,
                      adapter_cutting: unit.fastp?.adapter_cutting,
                    },
                    null,
                    2,
                  )}
                </pre>
                <a
                  className="button small"
                  href={url(
                    downloadDataset(run, `processing/${unit.id}/fastp.json`),
                  )}
                >
                  Download original fastp JSON
                </a>
              </details>
              {processing.options.compare_qc && (
                <>
                  <div className="processing-chart-controls">
                    <label>
                      Read
                      <select
                        value={read}
                        onChange={(event) =>
                          setRead(Number(event.target.value))
                        }
                      >
                        {unit.inputs.map((path, i) => (
                          <option key={path} value={i}>
                            {unit.inputs.length === 2 ? `R${i + 1} · ` : ""}
                            {path.split("/").pop()}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      FastQC module
                      <select
                        value={metric}
                        onChange={(event) => setMetric(event.target.value)}
                      >
                        {metrics.map((name) => (
                          <option key={name}>{name}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <p className="inline-note">
                    Each chart keeps its own reported positions and bins.
                    Differently grouped intervals are not overlaid or
                    interpolated.
                  </p>
                  <div className="processing-charts">
                    {[
                      [raw, "Raw · before processing"],
                      [processed, "Processed · after processing"],
                    ].map(([sample, label]) => (
                      <section key={String(label)} className="chart-panel">
                        <h3>{String(label)}</h3>
                        {sample && typeof sample !== "string" ? (
                          <QcModule sample={sample} metric={metric} />
                        ) : (
                          <p>
                            FastQC data unavailable. Inspect execution errors
                            and original reports.
                          </p>
                        )}
                      </section>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
          {unit.statistics?.map((row, index) => (
            <div className="table-scroll" key={index}>
              <table className="processing-table">
                <caption>Original SeqKit statistics (reported values)</caption>
                <tbody>
                  {Object.entries(row).map(([key, value]) => (
                    <tr key={key}>
                      <th>{key}</th>
                      <td>{value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}
      <h3>Derived FASTQ datasets</h3>
      {!run.derived_datasets?.length ? (
        <p>
          No published derived FASTQs.{" "}
          {["queued", "running"].includes(run.state)
            ? "Files are available only after successful processing and validation."
            : run.mode === "seqkit-stats"
              ? "Statistics is a read-only operation."
              : "Incomplete or cancelled outputs are not published."}
        </p>
      ) : (
        <div className="table-scroll">
          <table className="processing-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Derived file</th>
                <th>Reads</th>
                <th>Bases</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody>
              {run.derived_datasets.map((entry) => (
                <tr key={entry.id}>
                  <td title={entry.source}>{entry.source.split("/").pop()}</td>
                  <td title={entry.path}>
                    {entry.unit_id} · {entry.read || "independent read file"}
                  </td>
                  <td>{entry.records.toLocaleString()}</td>
                  <td>{entry.bases.toLocaleString()}</td>
                  <td>
                    <a
                      className="button small"
                      href={url(downloadDataset(run, entry.path))}
                    >
                      Download FASTQ
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
