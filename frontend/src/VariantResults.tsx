import { useMemo, useState } from "react";
import { url } from "./api";
import { NativePlot } from "./AnalyticsChart";
import ReportedTable from "./ReportedTable";
import { variantViews } from "./variantChart";
import type { Run } from "./types";

export function VariantOverview({run}: {run: Run}) {
  return <section className="form-section" aria-label="Variant overview">
    <h2>Variant overview</h2>
    <p>BCFtools {run.tools?.bcftools?.version || "version unavailable"} · {run.sample_count} completed input files. Each file may contain several biological samples.</p>
    {run.qc?.results.map(r => <div key={r.id}>
      <h3>{r.name}</h3>
      <p className="mono output-destination">{r.path}</p>
      {r.state === "completed" && r.variant ? <p>
        <strong>{r.variant.summary.rows.find(([k]) => k === "number of records:")?.[1]} reported records</strong> · {r.variant.sample_count} within-file samples · Ti/Tv: {r.variant.tstv_ratio ?? "Unavailable (no transversions)"} · {r.variant.input_format} / {r.variant.compression}
      </p> : <p role="status">{r.state} {r.error}</p>}
    </div>)}
    <p className="inline-note">Records, unique loci, alternate alleles and genotypes are different units. gVCF reference blocks count as records here; record counts do not establish genome-wide coverage. Detailed statistics and original reports are under QC metrics.</p>
  </section>;
}

export default function VariantResults({run}: {run: Run}) {
  const rows = run.qc?.results || [];
  const [selected, select] = useState("");
  const row = rows.find(r => r.id === selected) || rows[0];
  const data = row?.state === "completed" ? row.variant : undefined;
  const views = useMemo(() => data ? variantViews(data) : null, [data]);
  const registered = new Set(run.reports.map(r => r.path));
  return <section className="form-section" aria-label="BCFtools variant results">
    <h2>BCFtools variant QC</h2>
    <label className="field-label" htmlFor="variant-input">Variant input file</label>
    <select id="variant-input" className="wide-input" value={row?.id || ""} onChange={e => select(e.target.value)}>
      {rows.map(r => <option key={r.id} value={r.id}>{r.name} · {r.state} · {r.path}</option>)}
    </select>
    <p className="mono output-destination">{row?.path}</p>
    <p role="status">{row?.state} {row?.error}</p>
    {data && views && <>
      <p>{data.input_format} / {data.compression} · {data.sample_count} within-file samples · Ti/Tv: <strong>{data.tstv_ratio ?? "Unavailable (no transversions)"}</strong></p>
      <p className="inline-note">Composition categories overlap and may omit symbolic alleles. MNPs are separate from SNPs. The upstream multiallelic definition may include gVCF symbolic alleles. These counts do not measure callable bases or whole-genome coverage.</p>
      {views.composition && <NativePlot view={views.composition} />}
      <ReportedTable label="Original record summary" data={data.summary} open />
      {views.tstv && <NativePlot view={views.tstv} />}
      <ReportedTable label="Original Ti/Tv values" data={data.tstv} />
      <p className="inline-note">Upstream reports 0.00 when the denominator is zero; the native ratio remains unavailable. Counts concern SNP substitutions and may include multiple alternate alleles per record.</p>
      {views.quality ? <NativePlot view={views.quality} /> : <p role="status">Quality chart unavailable: no measured QUAL counts, more than 2000 bins, or counts exceed exact chart precision.</p>}
      <ReportedTable label="Original QUAL distribution" data={data.quality} />
      {views.depth ? <NativePlot view={views.depth} /> : <p role="status">Depth chart unavailable: no measured depth observations, more than 2000 bins, or counts exceed exact chart precision.</p>}
      <p className="inline-note">Site depth uses INFO/DP; genotype depth requires requested per-sample statistics and FORMAT/DP. Fractions use their respective observed populations. Underflow bins (&lt;0) can contain missing values and are excluded from the chart. Zero depth is retained when actually reported.</p>
      <ReportedTable label="Original depth distribution" data={data.depth} />
      {data.sample_statistics_available ? <ReportedTable label="Within-file sample counts" data={data.sample_counts} open /> : <p role="status">Per-sample genotype statistics unavailable: not requested or no FORMAT/GT declaration.</p>}
      <p className="inline-note">Within-file sample IDs are separate from input-file identities. Average sample depth is omitted because upstream zero can also mean unavailable depth. Allele-frequency bins remain in the original report: its zero bin can mix singletons and unknown denominators.</p>
      <ReportedTable label="Original substitution counts" data={data.substitutions} />
      <details><summary>Original report provenance</summary>
        <p className="mono output-destination">SHA-256: {data.report_sha256}</p>
        <p className="mono output-destination">Source snapshot: {JSON.stringify(data.source_snapshot)}</p>
        <p>Uninterpreted sections: {data.uninterpreted_sections.join(", ") || "None"}. Full unchanged reports retain upstream column definitions.</p>
      </details>
      <div className="inline-actions">{Object.entries(data.reports).filter(([, path]) => registered.has(path)).map(([name, path]) => <a key={name} className="button small" download href={url(`api/runs/${run.id}/download?path=${encodeURIComponent(path)}`)}>Download original {name === "stats" ? "BCFtools stats" : name}</a>)}</div>
    </>}
  </section>;
}
