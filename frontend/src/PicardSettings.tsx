import type { Config, PicardOptions } from "./types";

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
