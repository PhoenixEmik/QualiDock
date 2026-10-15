import type { Sample } from "./types";
import { inputFilename, moduleNames, moduleStatus, reportedStat } from "./qc";

export default function SampleDetails({ samples }: { samples: Sample[] }) {
  return (
    <>
      {samples.map((sample, index) => {
        const statuses = moduleNames(sample).map((name) =>
          moduleStatus(sample, name),
        );
        const length =
          reportedStat(sample, "Sequence length") || sample.sequence_length;
        return (
          <section
            className="qc-sample-details"
            key={sample.id}
            aria-label={`${samples.length > 1 ? (index === 0 ? "R1" : "R2") : "Sample"} details`}
          >
            {samples.length > 1 && <h4>{index === 0 ? "R1" : "R2"}</h4>}
            <h3>{inputFilename(sample)}</h3>
            <dl>
              {[
                ["Original input filename", inputFilename(sample)],
                [
                  "Sequences",
                  reportedStat(sample, "Total Sequences") ??
                    sample.total_sequences?.toLocaleString() ??
                    "Unavailable",
                ],
                ["Read length", length ? `${length} bp` : "Unavailable"],
                [
                  "GC content",
                  reportedStat(sample, "%GC") !== undefined
                    ? `${reportedStat(sample, "%GC")}%`
                    : sample.gc_percent === null
                      ? "Unavailable"
                      : `${sample.gc_percent}%`,
                ],
                ["Quality encoding", sample.encoding || "Unavailable"],
                ["FastQC version", sample.fastqc_version || "Unavailable"],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <h4>Module status summary</h4>
            <p className="qc-status-summary">
              {["pass", "warn", "fail", "unavailable", "unknown"]
                .filter((status) => statuses.includes(status))
                .map((status) => (
                  <span key={status}>
                    {statuses.filter((value) => value === status).length}{" "}
                    {status.toUpperCase()}
                  </span>
                ))}
            </p>
          </section>
        );
      })}
    </>
  );
}
