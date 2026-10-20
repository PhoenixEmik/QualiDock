import { NativePlot } from "./AnalyticsChart";
import { picardRnaView } from "./geneBodyChart";
import { useMemo, useState } from "react";
import { url } from "./api";
import ReportedTable from "./ReportedTable";
import type { Run } from "./types";

export default function PicardResults({ run }: { run: Run }) {
  const rows = run.qc?.results || [];
  const [selected, setSelected] = useState("");
  const row = rows.find((r) => r.id === selected) || rows[0];
  const data = row?.state === "completed" ? row.picard : undefined;
  const registered = new Set(run.reports.map((r) => r.path));
  const columns = [
    "PAIR_ORIENTATION",
    "READ_PAIRS",
    "MEDIAN_INSERT_SIZE",
    "MEAN_INSERT_SIZE",
    "STANDARD_DEVIATION",
    "LIBRARY",
  ];
  const labels = [
    "Orientation",
    "Read-pair observations",
    "Median (bp)",
    "Mean (bp, trimmed)",
    "SD (bp, trimmed)",
    "Population",
  ];
  return (
    <section className="form-section" aria-label="Picard insert-size results">
      <h2>Picard insert-size QC</h2>
      <p className="inline-note">
        Picard {run.tools?.picard?.version || "version unavailable"} · Java{" "}
        {run.tools?.java?.version || "version unavailable"}. Original upstream
        calculations and reported precision; no read lengths or unique molecule
        counts are inferred.
      </p>
      <label className="field-label" htmlFor="insert-result-input">
        Alignment file
      </label>
      <select
        id="insert-result-input"
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
          {data.status === "unavailable" ? (
            <p role="status">
              Picard reported no qualifying paired observations (
              {data.mapped_pairs_reported}). No insert-size metrics or histogram
              were produced; no distribution is inferred for single-end data.
            </p>
          ) : (
            <>
              <p className="inline-note">
                BAM-wide rows have blank sample/library fields. Named rows are
                Picard's library populations; do not sum library and all-read
                rows. Mean, SD and histogram use the original median +{" "}
                {data.deviations} × MAD cutoff. Orientation categories below
                fraction {data.minimum_orientation_fraction} can be absent.
                Read-pair observations after tool filtering are not independent
                biological molecules. Missing values and ? are unavailable.
              </p>
              <div
                className="table-scroll"
                tabIndex={0}
                role="region"
                aria-label="Insert-size summary"
              >
                <table>
                  <thead>
                    <tr>
                      {labels.map((label) => (
                        <th key={label}>{label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.metrics.rows.map((values, i) => (
                      <tr key={i}>
                        {columns.map((column, j) => {
                          const value =
                            values[data.metrics.columns.indexOf(column)];
                          const empty =
                            values[
                              data.metrics.columns.indexOf("READ_PAIRS")
                            ] === "0" &&
                            j >= 2 &&
                            j <= 4;
                          const display =
                            column === "LIBRARY"
                              ? value
                                ? `${values[data.metrics.columns.indexOf("SAMPLE")] || "Sample unavailable"} / ${value}`
                                : "All reads"
                              : empty || !value || value === "?"
                                ? "Unavailable"
                                : value;
                          return j ? (
                            <td key={column}>{display}</td>
                          ) : (
                            <th key={column} scope="row">
                              {display}
                            </th>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {data.metrics.total_rows > data.metrics.rows.length && (
                <p className="inline-note">
                  Showing {data.metrics.rows.length} of{" "}
                  {data.metrics.total_rows} rows; original metrics retain every
                  reported population.
                </p>
              )}
              <details>
                <summary>Original metrics and histogram data</summary>
                <ReportedTable
                  label="Original Picard metrics"
                  data={data.metrics}
                />
                <ReportedTable
                  label="Original insert-size histogram"
                  data={data.histogram}
                  open
                />
              </details>
            </>
          )}
          <p className="inline-note">
            Insert size uses Picard's qualifying alignment/template
            observations. It is not read length; genomic RNA-seq spans can
            include introns. Results depend on duplicate/orientation/tail
            filtering and library preparation.
          </p>
          <details>
            <summary>Execution settings</summary>
            <pre>{JSON.stringify(run.qc?.options, null, 2)}</pre>
            <p>
              Java maximum heap: {data.heap_mb} MiB, with additional headroom
              under the shared process-tree limit.{" "}
              {data.rscript_version
                ? `Rscript ${data.rscript_version}.`
                : "PDF was not requested; original numeric histogram is retained when observations exist."}
            </p>
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

const rnaSummary: [string,string,string][] = [
  ["PF_BASES","PF bases","bases in PF records, including unmapped sequence"],
  ["PF_ALIGNED_BASES","PF aligned bases","aligned bases, not fragments"],
  ["CODING_BASES","Coding bases","bases assigned by Picard"],
  ["UTR_BASES","UTR bases","bases assigned by Picard"],
  ["INTRONIC_BASES","Intronic bases","bases assigned by Picard"],
  ["INTERGENIC_BASES","Intergenic bases","bases assigned by Picard"],
  ["RIBOSOMAL_BASES","rRNA bases","bases; requires selected rRNA intervals"],
  ...["CODING","UTR","INTRONIC","INTERGENIC","RIBOSOMAL","MRNA"].map(k =>
    ["PCT_"+k+"_BASES",(k === "MRNA" ? "Coding + UTR" : k)+" fraction","fraction of PF_ALIGNED_BASES"] as [string,string,string]),
  ["PCT_USABLE_BASES","Usable base fraction","coding + UTR / PF_BASES"],
  ["CORRECT_STRAND_READS","Correct-strand observations","qualifying aligned records; not fragments"],
  ["INCORRECT_STRAND_READS","Incorrect-strand observations","qualifying aligned records; not fragments"],
  ["MEDIAN_5PRIME_BIAS","Median 5′ bias","relative coverage; eligible transcripts only"],
  ["MEDIAN_3PRIME_BIAS","Median 3′ bias","relative coverage; eligible transcripts only"],
  ["MEDIAN_5PRIME_TO_3PRIME_BIAS","Median 5′ / 3′ bias","ratio; eligible transcripts only"],
];

export function PicardRnaResults({run}:{run:Run}) {
  const rows=run.qc?.results || [], [selected,setSelected]=useState("");
  const row=rows.find(r => r.id===selected) || rows[0], data=row?.picard;
  const view=useMemo(() => picardRnaView(data?.histogram.rows || [],row?.name || ""),[data,row?.name]);
  const registered=new Set(run.reports.map(r => r.path));
  const values=Object.fromEntries((data?.metrics.columns || []).map((c,i) => [c,data?.metrics.rows[0]?.[i] || ""]));
  return <section className="form-section" aria-label="Picard RNA-seq results">
    <h2>Picard RNA-seq metrics</h2>
    <p className="inline-note">Picard {run.tools?.picard?.version || "version unavailable"} · ALL_READS · strand specificity: {String(run.qc?.options.strand || "unavailable")}. These are base assignments and qualifying alignment observations, not unique molecules. PCT fields below retain original fractions (0–1), not percent units.</p>
    <label className="field-label" htmlFor="rna-picard-input">Alignment file</label>
    <select id="rna-picard-input" className="wide-input" value={row?.id || ""} onChange={e => setSelected(e.target.value)}>
      {rows.map(r => <option key={r.id} value={r.id}>{r.name} · {r.state} · {r.path}</option>)}
    </select>
    {row && <><h3>{row.name}</h3><p className="mono output-destination">{row.path}</p><p role="status">{row.state}{row.error ? " · "+row.error : ""}</p></>}
    {data && <>
      {data.warnings?.map(w => <p role="status" key={w}>{w}</p>)}
      <div className="table-scroll" tabIndex={0} role="region" aria-label="RNA metrics summary"><table>
        <thead><tr><th>Metric</th><th>Original value</th><th>Unit / denominator</th></tr></thead>
        <tbody>{rnaSummary.map(([key,label,unit]) => {
          const unavailable=(key.startsWith("MEDIAN_") && !data.coverage_available) ||
            (key.includes("STRAND_READS") && run.qc?.options.strand==="NONE") ||
            (key.startsWith("PCT_") && values[key==="PCT_USABLE_BASES" ? "PF_BASES" : "PF_ALIGNED_BASES"]==="0");
          return <tr key={key}><th scope="row">{label}</th><td>{unavailable || !values[key] ? "Unavailable" : values[key]}</td><td>{unit}</td></tr>;
        })}</tbody>
      </table></div>
      {!run.qc?.rrna && <p className="inline-note">No rRNA annotation selected. Unavailable rRNA metrics do not establish absence of biological rRNA.</p>}
      <p className="inline-note">Picard base fractions differ from RSeQC tag counts. Selected strand counting is not an inferred protocol; NONE does not assess correct/incorrect strand agreement.</p>
      <h3>Transcript-normalized gene-body coverage</h3>
      {data.coverage_available ? <NativePlot view={view} /> : <p role="status">Coverage unavailable: no eligible transcript histogram was reported. Upstream default-zero bias values are not meaningful biological observations.</p>}
      <p className="inline-note">Original 101 positions 0–100, 5′ → 3′; normalized by transcript mean across Picard-selected eligible models, not absolute depth or RSeQC's 1–100 profile. Picard 3.5.0 omits an alignment-block end in its coverage counter; boundary effects can exclude otherwise covered transcripts. No correction or automatic quality classification is applied.</p>
      <ReportedTable label="Original Picard RNA metrics" data={data.metrics} />
      <ReportedTable label="Original Picard normalized coverage" data={data.histogram} />
      <details><summary>Annotation and execution provenance</summary>
        <pre>{JSON.stringify({options:run.qc?.options,annotation:run.qc?.annotation,rrna:run.qc?.rrna},null,2)}</pre>
        <p>Java heap {data.heap_mb} MiB; Rscript {data.rscript_version || "not requested"}. Original PDF: {data.plot_status}.</p>
        <p>Annotation dictionary compatibility checks names and coordinate bounds, not independent assembly sequence identity. Different annotations or counting populations are not interchangeable.</p>
      </details>
      <div className="inline-actions">{Object.entries(data.reports).filter(([,p]) => registered.has(p)).map(([name,path]) =>
        <a key={name} className="button small" download href={url("api/runs/"+run.id+"/download?path="+encodeURIComponent(path))}>Download {name.replaceAll("_"," ")}</a>)}</div>
    </>}
  </section>;
}
