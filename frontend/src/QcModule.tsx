import type { Sample } from "./types";
import { findModule, tableOnly } from "./qc";
import QualityChart from "./QualityChart";
import RawData from "./RawData";
import { gcReferenceUnavailable, gcReferenceNote } from "./fastqcTheme";

export default function QcModule({
  sample,
  metric,
}: {
  sample: Sample;
  metric: string;
}) {
  const module = findModule(sample, metric);
  if (!module || module.available === false)
    return (
      <p className="inline-note">
        This module is unavailable in this FastQC result.
        {module?.summary_status &&
          ` summary.txt reports ${module.summary_status.toUpperCase()}, but no module data is available.`}
      </p>
    );
  return (
    <>
      {module.metadata?.map((row, index) => (
        <p className="inline-note" key={index}>
          {row.join(": ")}
        </p>
      ))}
      {!module.rows.length ? (
        <p className="inline-note">
          {metric === "Overrepresented sequences"
            ? "No overrepresented sequences were reported."
            : "FastQC reported no data rows for this module."}{" "}
          Module status: {module.status.toUpperCase()}.
        </p>
      ) : !tableOnly(module) ? (
        <>
          <QualityChart sample={sample} metric={metric} />
        </>
      ) : null}
      {gcReferenceUnavailable(module) && (
        <p className="inline-note">{gcReferenceNote}</p>
      )}
      <RawData
        key={`${sample.id}:${metric}`}
        module={module}
        sampleName={sample.name}
        initiallyOpen={tableOnly(module)}
      />
      {module.summary_status && module.summary_status !== module.status && (
        <p className="error">
          summary.txt reports {module.summary_status.toUpperCase()};
          fastqc_data.txt reports {module.status.toUpperCase()}. Both source
          reports are preserved.
        </p>
      )}
    </>
  );
}
