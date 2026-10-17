import AlignmentResults from "./AlignmentResults";
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
  if (run.qc?.tool === "samtools") return <AlignmentResults run={run} />;
  if (run.qc?.tool === "fastq_screen") return <ScreenResults run={run} />;
  if (run.qc?.tool === "nanoplot") return <NanoPlotResults run={run} />;
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
                download
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

function NanoPlotResults({ run }: { run: Run }) {
  const download = (path: string) =>
    url(`/api/runs/${run.id}/download?path=${encodeURIComponent(path)}`);
  return (
    <section className="form-section" aria-label="NanoPlot QC results">
      <h2>NanoPlot long-read QC</h2>
      <p className="inline-note">
        NanoPlot {run.tools?.nanoplot?.version || "version unavailable"}.
        Original read-level NanoStats; these are independent of nanoq and FastQC
        per-base statistics. Reported precision is preserved. Phred+33 is the
        tool convention, not detected encoding. Reads above a Q threshold are
        read-count percentages, not Q20/Q30 base percentages; reported Mb fields
        are rounded by NanoPlot.
      </p>
      <p className="inline-note">
        Time/channel activity and yield over time: unavailable from ordinary
        FASTQ. Input is fully extracted before plotting. The upstream scatter
        can display a random subset of up to 10,000 reads; NanoStats describes
        the full input. Original interactive plots are in Reports. PNG export is
        unavailable in this safe profile; it would require an upstream fix to
        avoid automatic Chrome downloads.
      </p>
      {run.qc?.results.map((row) => (
        <section className="form-section" key={row.id}>
          <h3>{row.name}</h3>
          <p className="mono output-destination">{row.path}</p>
          <p role="status">
            {row.state}
            {row.error ? ` · ${row.error}` : ""}
          </p>
          {row.state === "completed" && row.nanoplot && (
            <>
              <div
                className="table-scroll"
                role="region"
                aria-label={`NanoStats ${row.name}`}
                tabIndex={0}
              >
                <table>
                  <thead>
                    <tr>
                      {row.nanoplot.columns.map((c) => (
                        <th key={c}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {row.nanoplot.rows.map(([key, value]) => (
                      <tr key={key}>
                        <th scope="row">{key}</th>
                        <td>{value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <a
                download
                className="button secondary small"
                href={download(row.report)}
              >
                Download original NanoStats
              </a>{" "}
              <a
                className="button secondary small"
                download
                href={download(row.nanoplot.html)}
              >
                Download original NanoPlot HTML
              </a>
              {row.nanoplot.plots.length > 0 && (
                <details>
                  <summary>Original plot files</summary>
                  {row.nanoplot.plots.map((path) => (
                    <p key={path}>
                      <a download href={download(path)}>
                        Download {path.split("/").pop()}
                      </a>
                    </p>
                  ))}
                </details>
              )}
              <details>
                <summary>Source provenance</summary>
                <p className="mono output-destination">
                  SHA-256: {row.source_sha256 || "Unavailable"}
                </p>
              </details>
            </>
          )}
        </section>
      ))}
    </section>
  );
}

function ScreenResults({ run }: { run: Run }) {
  const panel = run.qc?.reference_panel;
  return (
    <section className="form-section" aria-label="FastQ Screen results">
      <h2>FastQ Screen</h2>
      <p className="inline-note">
        FastQ Screen {run.tools?.fastq_screen?.version || "version unavailable"}{" "}
        · Bowtie2 {run.tools?.bowtie2?.version || "version unavailable"} ·
        Panel: {panel?.id || "unavailable"}
      </p>
      <p>
        Read-level mapping observations depend on the selected references and
        alignment settings. They are not proof of contamination or sample
        identity. R1 and R2 are screened independently; no paired alignments or
        whole-library abundance estimates.
      </p>
      <p className="inline-note">
        Target subset: {String(run.qc?.options.subset ?? "Unavailable")} reads
        per file. Systematic subsampling can process up to twice this target.
        Phred+33 alignment convention.
      </p>
      {run.qc?.results.map((row) => (
        <section
          key={row.id}
          className="form-section"
          aria-label={`Screen result ${row.name}`}
        >
          <h3>{row.name}</h3>
          <p className="mono output-destination">{row.path}</p>
          <p role="status">
            {row.state}
            {row.error ? ` · ${row.error}` : ""}
          </p>
          {row.state === "completed" && row.screen && (
            <>
              <p>
                {row.screen.processed_reads.toLocaleString()} reads screened ·{" "}
                {row.screen.no_genome_percent}% hit no reference in this panel.
              </p>
              <div
                className="table-scroll"
                role="region"
                aria-label={`Reference mapping summary ${row.name}`}
                tabIndex={0}
              >
                <table>
                  <caption>
                    Original FastQ Screen categories: # columns are counts; %
                    columns are percentages of screened reads.
                  </caption>
                  <thead>
                    <tr>
                      {row.screen.columns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {row.screen.rows.map((values) => (
                      <tr key={values[0]}>
                        {values.map((value, index) =>
                          index === 0 ? (
                            <th key={index} scope="row">
                              {value}
                            </th>
                          ) : (
                            <td key={index}>{value}</td>
                          ),
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <a
                className="button small"
                download
                href={url(
                  `api/runs/${run.id}/download?path=${encodeURIComponent(row.report)}`,
                )}
              >
                Download original summary
              </a>
            </>
          )}
        </section>
      ))}
      <details>
        <summary>Reference provenance</summary>
        <p className="mono output-destination">
          Configuration SHA-256: {panel?.sha256 || "Unavailable"}
        </p>
        <p>
          {panel?.index_identity || "Index identity unavailable"}. The actual
          reference content has not been independently checksummed by QualiDock.
        </p>
        <ul>
          {panel?.references.map((reference) => (
            <li key={reference.name}>
              {reference.name}:{" "}
              <span className="mono output-destination">
                {reference.prefix}
              </span>
            </li>
          ))}
        </ul>
      </details>
      <p className="inline-note">
        Official HTML, available graphs and optional MultiQC are in Reports.
        Graphs require the optional upstream GD::Graph module. No FASTQ outputs
        are published.
      </p>
    </section>
  );
}
