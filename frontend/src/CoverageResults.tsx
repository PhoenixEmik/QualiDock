import { useMemo, useState } from "react";
import { url } from "./api";
import { NativePlot } from "./AnalyticsChart";
import { coverageView } from "./coverageChart";
import type { ReportedTable, Run } from "./types";

function OriginalTable({
  label,
  data,
  open = false,
}: {
  label: string;
  data: ReportedTable;
  open?: boolean;
}) {
  return (
    <details open={open}>
      <summary>
        {label} ({data.total_rows} reported rows)
      </summary>
      {data.total_rows > data.rows.length && (
        <p className="inline-note">
          Showing {data.rows.length} rows. Download the original file for all
          reported values.
        </p>
      )}
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label={label}
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
    </details>
  );
}

export default function CoverageResults({ run }: { run: Run }) {
  const rows = run.qc?.results || [];
  const [selected, setSelected] = useState("");
  const row = rows.find((r) => r.id === selected) || rows[0];
  const data = row?.state === "completed" ? row.mosdepth : undefined;
  const plot = useMemo(
    () => (data?.distribution.rows.length ? coverageView(data) : null),
    [data],
  );
  const registered = new Set(run.reports.map((r) => r.path));
  return (
    <section className="form-section" aria-label="mosdepth coverage results">
      <h2>mosdepth coverage QC</h2>
      <p className="inline-note">
        mosdepth {run.tools?.mosdepth?.version || "version unavailable"}.
        Original reported depths and fractions; no per-base output, resampling
        or invented coverage. SAMtools preflight checks actual coordinate
        sorting and CRAM decoding, adding a full source scan.
      </p>
      <label className="field-label" htmlFor="coverage-input">
        Alignment file
      </label>
      <select
        id="coverage-input"
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
          <p className="inline-note">
            Minimum alignment MAPQ: {data.mapq}. Exclude flag mask:{" "}
            {data.exclude_flags}. Default CIGAR handling and mate-overlap
            correction are retained; fast/fragment modes are disabled. Values
            are alignment coverage, not unique molecules or FASTQ base-quality
            percentages.
          </p>
          <p>
            <strong>
              CDF denominator: {data.reported_reference_bases} mosdepth-reported
              reference bases.
            </strong>{" "}
            Alignment header contains {data.header_reference_bases} reference
            bases.
          </p>
          {!!data.omitted_reference_count && (
            <p className="tool-warning">
              {data.omitted_reference_count} reference(s) not reported in
              summary/CDF: {data.omitted_references.join(", ")}
              {data.omitted_reference_count > data.omitted_references.length
                ? " …"
                : ""}
              . Omitted references are unavailable here; this total is not
              whole-header/assembly breadth.
            </p>
          )}
          {plot ? (
            <NativePlot view={plot} />
          ) : (
            <p role="status">
              CDF exceeds the native view limit. Download the complete original
              distribution; no points are sampled or interpolated.
            </p>
          )}
          <p className="inline-note">
            Summary length counts reported reference positions; bases is
            cumulative aligned depth after filtering and mate-overlap
            correction, not total sequenced FASTQ bases. Mean is the original
            rounded mosdepth value. Empty aggregates have unavailable
            mean/min/max; original sentinels are retained in the raw table.
          </p>
          <OriginalTable
            label="Original coverage summary"
            data={data.summary}
            open
          />
          {data.thresholds && (
            <>
              <p>
                <strong>BED scope:</strong> requested intervals contain{" "}
                {data.requested_region_bases} bases. mosdepth regional
                summary/CDF denominator:{" "}
                {data.reported_region_bases ?? "Unavailable"} reported region
                bases. Empty contigs can be omitted from that aggregate even
                when their individual regions report zero.
              </p>
              <p className="inline-note">
                Threshold columns count bases at or above each threshold within
                that row's [start, end) interval. Its denominator is end −
                start. These are per-region counts, not global percentages;
                regions are never combined into a new QC metric.
              </p>
              <OriginalTable
                label="Original region thresholds"
                data={data.thresholds}
                open
              />
            </>
          )}
          {data.regions && (
            <OriginalTable
              label="Original regional mean coverage"
              data={data.regions}
            />
          )}
          <OriginalTable
            label="Raw reported global CDF"
            data={data.distribution}
          />
          <details>
            <summary>Index provenance</summary>
            <p className="mono output-destination">{data.index.path}</p>
            <p>
              {data.index.identity}. Operators must provide an index matching
              the exact source; snapshots alone cannot establish that binding.
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
