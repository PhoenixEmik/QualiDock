import type { Config, RnaOptions, Run } from "./types";

export default function RnaQcSettings({
  mode,
  setMode,
  value,
  change,
  config,
  busy,
}: {
  mode: Run["mode"];
  setMode: (mode: Run["mode"]) => void;
  value: RnaOptions;
  change: (value: RnaOptions) => void;
  config: Config | null;
  busy: boolean;
}) {
  return (
    <div className="form-section">
      <label>
        <input
          type="checkbox"
          checked={!!value.multiqc}
          disabled={busy || !config?.tools.multiqc}
          onChange={(e) => change({ ...value, multiqc: e.target.checked })}
        />{" "}
        Aggregate original RSeQC reports with MultiQC
      </label>
      <p className="inline-note">
        Optional combined report in Reports. Missing General Statistics do not
        mean missing RSeQC module results.
      </p>
      <label className="field-label" htmlFor="rna-operation">
        RSeQC operation
      </label>
      <select
        id="rna-operation"
        value={mode}
        onChange={(e) => setMode(e.target.value as Run["mode"])}
        disabled={busy}
      >
        <option value="rseqc-infer">Library strandedness fractions</option>
        <option value="rseqc-distribution">
          Read distribution across annotations
        </option>
      </select>
      <label className="field-label" htmlFor="rna-annotation">
        Gene annotation (BED12)
      </label>
      <select
        id="rna-annotation"
        value={value.annotation}
        disabled={busy}
        onChange={(e) => change({ ...value, annotation: e.target.value })}
      >
        <option value="">Choose an approved gene model</option>
        {config?.rna_annotations?.map((a) => (
          <option key={a.id} value={a.id} disabled={!a.available}>
            {a.id}
            {a.error ? ` · ${a.error}` : ` · ${a.transcripts} transcripts`}
          </option>
        ))}
      </select>
      {!config?.rna_annotations?.some((a) => a.available) && (
        <p role="status">
          No usable BED12 annotation. An administrator must configure an
          existing local gene model.
        </p>
      )}
      <p className="inline-note">
        BAM only. Gene-model contig names and coordinate bounds must match the
        alignment header; this does not independently verify genome assembly
        identity. No reference downloads, index creation or source editing.
      </p>
      {mode === "rseqc-infer" ? (
        <details className="processing-advanced">
          <summary>Strandedness settings (optional)</summary>
          <label>
            Maximum usable alignments{" "}
            <input
              type="number"
              min={1}
              max={10000000}
              value={value.sample_size}
              disabled={busy}
              onChange={(e) =>
                change({ ...value, sample_size: Number(e.target.value) })
              }
            />
          </label>
          <label>
            Minimum alignment MAPQ{" "}
            <input
              type="number"
              min={0}
              max={255}
              value={value.mapq}
              disabled={busy}
              onChange={(e) =>
                change({ ...value, mapq: Number(e.target.value) })
              }
            />
          </label>
          <p className="inline-note">
            First eligible annotation-overlapping alignment records, not random
            read pairs. This cap does not bound input I/O. Small samples may be
            unreliable; no automatic protocol classification is applied.
          </p>
        </details>
      ) : (
        <p className="inline-note">
          Scans alignment records. Tags are aligned blocks, not independent
          fragments. Nested upstream/downstream categories are not additive.
        </p>
      )}
    </div>
  );
}
