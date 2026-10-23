import type { Config, VariantOptions } from "./types";

export default function VariantSettings({ value, change, config, busy }: {
  value: VariantOptions; change: (v: VariantOptions) => void; config: Config | null; busy: boolean;
}) {
  return <fieldset disabled={busy} className="processing-advanced">
    <legend>Variant statistics</legend>
    <p className="inline-note">Whole-file, read-only BCFtools stats. Source files stay unchanged. No index, reference download, filtering or variant calling. Optional annotations and genotype fields determine which statistics are available.</p>
    <label><input type="checkbox" checked={value.per_sample} onChange={e => change({...value, per_sample: e.target.checked})} /> Request within-file per-sample statistics (requires sample columns)</label>
    <label><input type="checkbox" checked={value.multiqc} disabled={!config?.tools.multiqc} onChange={e => change({...value, multiqc: e.target.checked})} /> Generate MultiQC</label>
  </fieldset>;
}
