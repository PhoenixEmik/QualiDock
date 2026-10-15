import { moduleHelp } from "./moduleNotes";

export default function ModuleHelp({ metric }: { metric: string }) {
  const help = moduleHelp(metric);
  return (
    <details className="qc-help">
      <summary>About this module</summary>
      {help ? (
        <>
          <p>{help.measures}</p>
          <p>{help.classification}</p>
          <p>{help.context}</p>
          <p>{help.caution}</p>
          <p>
            FastQC's saved PASS/WARN/FAIL classifications are preserved.
            Thresholds can depend on version and configuration; QualiDock does
            not recalculate them.
          </p>
          <p>
            Whole-genome, RNA-seq, amplicon, targeted and methylation-related
            libraries (including Illumina 5-Base Solution) need
            protocol-specific expectations. Do not transfer assumptions between
            different assay chemistries. A flag alone is not a recommendation to
            trim, filter or discard reads.
          </p>
          <a
            className="text-button"
            href={help.source}
            target="_blank"
            rel="noopener noreferrer"
          >
            FastQC module documentation
          </a>
        </>
      ) : (
        <p>
          No reviewed explanatory note is available for this additional module.
          The original reported data and classification remain available.
        </p>
      )}
    </details>
  );
}
