import type { Run, Sample } from "./types";
import { overviewCounts } from "./analytics";
import { useMemo } from "react";

export default function AnalyticsSummary({
  run,
  samples,
  loading,
}: {
  run: Run;
  samples: Sample[];
  loading: boolean;
}) {
  const counts = useMemo(() => overviewCounts(run, samples), [run, samples]);
  const metrics = [
    {
      label: "Read files",
      value: counts.readFiles,
      description:
        "FASTQ files with saved FastQC results; individual reads and lanes remain separate.",
    },
    {
      label: "Confirmed read pairs",
      value: counts.readPairs,
      description:
        "Pairs with both FastQC results and mutual, unambiguous saved input pairing metadata. Filenames alone never establish a pair.",
    },
    {
      label: "Files with failed modules",
      value: counts.withFailures,
      description:
        "Read files with at least one original FastQC FAIL module classification. This is not an overall sample failure verdict.",
    },
  ];
  return (
    <section
      className="qc-overview-summary"
      aria-label="QC analytics summary"
      aria-busy={loading}
    >
      <h2>QC Analytics</h2>
      <dl>
        {metrics.map((metric) => (
          <div key={metric.label} title={metric.description}>
            <dt>{metric.label}</dt>
            <dd>
              {loading ? (
                "—"
              ) : metric.value === null ? (
                <span className="qc-count-unavailable">Unavailable</span>
              ) : (
                metric.value.toLocaleString()
              )}
            </dd>
          </div>
        ))}
      </dl>
      <p className="inline-note">
        {loading
          ? "Loading saved FastQC results…"
          : "Counts cover saved FastQC results. Module failures do not imply that a sequencing sample is unusable."}
        {!loading &&
          counts.readPairs === null &&
          " Pairing metadata is unavailable; read pairs are not inferred."}
      </p>
    </section>
  );
}
