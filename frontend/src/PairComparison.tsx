import { useMemo, useState } from "react";
import type { SamplePair } from "./pairing";
import { compareModules } from "./comparison";
import { moduleKey } from "./qc";
import QcModule from "./QcModule";
import QualityChart from "./QualityChart";
import RawData from "./RawData";
import { gcReferenceUnavailable } from "./fastqcTheme";

export default function PairComparison({
  pair,
  metric,
}: {
  pair: SamplePair;
  metric: string;
}) {
  const [median, setMedian] = useState(false);
  const [visibility, setVisibility] = useState<Record<string, boolean>>({});
  const data = useMemo(
    () => compareModules(pair.r1, pair.r2, metric, median),
    [pair, metric, median],
  );
  return (
    <section className="qc-comparison" aria-label="R1 / R2 module comparison">
      <p className="inline-note" role="status">
        {data.reason}
      </p>
      {data.mode === "overlay" ? (
        <>
          {moduleKey(metric) === "perbasesequencequality" && (
            <label className="qc-median-control">
              <input
                type="checkbox"
                checked={median}
                onChange={(event) => setMedian(event.target.checked)}
              />{" "}
              Show reported medians
            </label>
          )}
          <fieldset className="qc-series-controls">
            <legend>Visible series</legend>
            {data.series.map((series) => (
              <label key={series.name}>
                <input
                  type="checkbox"
                  checked={visibility[series.name] !== false}
                  onChange={(event) =>
                    setVisibility((value) => ({
                      ...value,
                      [series.name]: event.target.checked,
                    }))
                  }
                />
                {series.name}
              </label>
            ))}
          </fieldset>
          {moduleKey(metric) === "perbasesequencecontent" && (
            <p className="inline-note">
              Colors identify nucleotides. Solid lines / circles: R1. Dashed
              lines / triangles: R2.
            </p>
          )}
          <QualityChart
            sample={pair.r1}
            mate={pair.r2}
            metric={metric}
            median={median}
            visibility={visibility}
          />
          {data.modules.some(
            (module) => module && gcReferenceUnavailable(module),
          ) && (
            <p className="inline-note">
              The theoretical GC distribution is unavailable for one or both
              reads. Only shared reported columns are compared. Inspect Raw Data
              or the official report for per-read details; no model is
              calculated.
            </p>
          )}
          {data.modules.map(
            (module, i) =>
              module && (
                <div key={i}>
                  {module.metadata?.map((row, index) => (
                    <p className="inline-note" key={index}>
                      {i === 0 ? "R1" : "R2"} · {row.join(": ")}
                    </p>
                  ))}
                  <RawData
                    module={module}
                    sampleName={`${i === 0 ? "R1" : "R2"} · ${i === 0 ? pair.r1.name : pair.r2.name}`}
                  />
                  {module.summary_status &&
                    module.summary_status !== module.status && (
                      <p className="error">
                        {i === 0 ? "R1" : "R2"}: summary.txt reports{" "}
                        {module.summary_status.toUpperCase()}; fastqc_data.txt
                        reports {module.status.toUpperCase()}. Original reports
                        are preserved.
                      </p>
                    )}
                </div>
              ),
          )}
        </>
      ) : (
        <div className="qc-separate-reads">
          {[pair.r1, pair.r2].map((sample, i) => (
            <section key={sample.id}>
              <h3>
                {i === 0 ? "R1" : "R2"} · {sample.name}
              </h3>
              <QcModule sample={sample} metric={metric} />
            </section>
          ))}
        </div>
      )}
    </section>
  );
}
