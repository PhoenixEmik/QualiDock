import type { Config, PicardOptions, PicardRnaOptions } from "./types";

export default function PicardSettings({
  value,
  change,
  config,
  busy,
}: {
  value: PicardOptions;
  change: (value: PicardOptions) => void;
  config: Config | null;
  busy: boolean;
}) {
  const plotting = !!config?.tool_details?.picard?.rscript_executable;
  return (
    <div className="form-section">
      <p className="inline-note">
        Read-only, coordinate-sorted BAM. Original Picard insert-size statistics
        and numeric histogram, grouped by orientation. CRAM is not yet
        qualified; no sorting, duplicate marking or source editing.
      </p>
      <label>
        <input
          type="checkbox"
          checked={!!value.multiqc}
          disabled={busy || value.by_library || !config?.tools.multiqc}
          onChange={(e) => change({ ...value, multiqc: e.target.checked })}
        />{" "}
        Aggregate original insert-size reports with MultiQC
      </label>
      {value.by_library && (
        <p role="status">
          MultiQC is unavailable for per-library reports: its module combines
          overlapping populations. Native metrics and original library reports
          remain available.
        </p>
      )}
      <details className="processing-advanced">
        <summary>Insert-size settings (optional)</summary>
        <label>
          <input
            type="checkbox"
            checked={value.by_library}
            disabled={busy}
            onChange={(e) =>
              change({
                ...value,
                by_library: e.target.checked,
                multiqc: e.target.checked ? false : value.multiqc,
              })
            }
          />{" "}
          Also report individual libraries
        </label>
        <p className="inline-note">
          Default statistics cover all reads in each BAM. Per-library metrics
          require SM/LB read-group metadata with unambiguous library names;
          grouping is performed by Picard.
        </p>
        <label>
          <input
            type="checkbox"
            checked={value.include_duplicates}
            disabled={busy}
            onChange={(e) =>
              change({ ...value, include_duplicates: e.target.checked })
            }
          />{" "}
          Include alignments marked as duplicates
        </label>
        <label>
          <input
            type="checkbox"
            checked={value.histogram_pdf}
            disabled={busy || !plotting}
            onChange={(e) =>
              change({ ...value, histogram_pdf: e.target.checked })
            }
          />{" "}
          Generate original PDF histogram (Rscript)
        </label>
        {!plotting && (
          <p role="status">
            Rscript is unavailable. Original numeric histogram and metrics can
            still be generated.
          </p>
        )}
      </details>
      <p className="inline-note">
        Orientation categories below Picard's 0.05 fraction threshold are
        omitted. Mean, standard deviation and histograms use upstream's median +
        10 × MAD tail cutoff. Missing orientations are unavailable, not zero.
        Genomic RNA-seq template spans can include introns and do not directly
        measure mature RNA fragments.
      </p>
    </div>
  );
}


export function PicardRnaSettings({ value, change, config, busy }: {
  value: PicardRnaOptions; change: (value: PicardRnaOptions) => void; config: Config | null; busy: boolean;
}) {
  const annotations = config?.rna_refflat_annotations || [], intervals = config?.rrna_intervals || [];
  const plotting = !!config?.tool_details?.picard?.rscript_executable;
  return <div className="form-section">
    <p className="inline-note">Read-only coordinate-sorted BAM, Picard 3.5.0, ALL_READS only. No CRAM, sorting, indexing or automatic BED12 conversion.</p>
    <label className="field-label" htmlFor="picard-ref">Approved native refFlat annotation</label>
    <select id="picard-ref" className="wide-input" value={value.annotation} disabled={busy} onChange={e => change({...value, annotation:e.target.value})}>
      <option value="">Select approved refFlat</option>
      {annotations.map(a => <option key={a.id} value={a.id} disabled={!a.available}>{a.id}{a.available ? "" : " · unavailable"}</option>)}
    </select>
    {!annotations.some(a => a.available) && <p role="status">No approved native refFlat is available. Ask the operator to configure QUALIDOCK_RNA_REFFLAT_ANNOTATIONS.</p>}
    {annotations.filter(a => !a.available).map(a => <p key={a.id} role="status">{a.id}: {a.error}</p>)}
    <label className="field-label" htmlFor="picard-strand">Picard strand specificity</label>
    <select id="picard-strand" className="wide-input" value={value.strand} disabled={busy} onChange={e => change({...value, strand:e.target.value as PicardRnaOptions["strand"]})}>
      <option value="">Choose explicitly</option>
      {["NONE","FIRST_READ_TRANSCRIPTION_STRAND","SECOND_READ_TRANSCRIPTION_STRAND"].map(s => <option key={s} value={s}>{s}</option>)}
    </select>
    <p className="inline-note">Choose the intended Picard counting semantics. RSeQC orientation fractions do not automatically select this setting; NONE is not a conclusion that the library is unstranded.</p>
    <label className="field-label" htmlFor="picard-rrna">Approved rRNA intervals (optional)</label>
    <select id="picard-rrna" className="wide-input" value={value.rrna || ""} disabled={busy} onChange={e => change({...value, rrna:e.target.value || null})}>
      <option value="">None · rRNA metrics unavailable</option>
      {intervals.map(a => <option key={a.id} value={a.id} disabled={!a.available}>{a.id}{a.available ? "" : " · unavailable"}</option>)}
    </select>
    {intervals.filter(a => !a.available).map(a => <p key={a.id} role="status">{a.id}: {a.error}</p>)}
    <label><input type="checkbox" checked={value.multiqc} disabled={busy || !config?.tools.multiqc} onChange={e => change({...value, multiqc:e.target.checked})} /> Aggregate original RNA metrics with MultiQC</label>
    <details className="processing-advanced"><summary>RNA metrics settings (optional)</summary>
      <p>Minimum eligible transcript length: 500 bases. End-bias window: 100 bases. rRNA overlap criterion: 0.8. Raising transcript eligibility does not avoid initial coverage memory allocations.</p>
      <label><input type="checkbox" checked={value.histogram_pdf} disabled={busy || !plotting} onChange={e => change({...value, histogram_pdf:e.target.checked})} /> Generate original RNA coverage PDF (Rscript)</label>
      {!plotting && <p role="status">Rscript is unavailable; numerical RNA metrics remain supported without PDF.</p>}
    </details>
  </div>;
}
