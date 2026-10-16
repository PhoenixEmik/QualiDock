import { useMemo, useState } from "react";
import {
  type AnalyticsSample,
  comparisonMetrics,
  multiComparison,
  sourceExport,
} from "./analytics";
import AnalyticsChart, { saveFile } from "./AnalyticsChart";
import { moduleKey } from "./qc";
import ExportModeSelect from "./ExportModeSelect";
import type { ExportMode } from "./rawExport";
export default function CompareSamples({
  entities,
  selected,
}: {
  entities: AnalyticsSample[];
  selected: Set<string>;
}) {
  const [metric, setMetric] = useState(comparisonMetrics[0]),
    [normalized, setNormalized] = useState(false);
  const [exportMode, setExportMode] = useState<ExportMode>("spreadsheet");
  const chosen = useMemo(
    () => entities.filter((e) => selected.has(e.id)),
    [entities, selected],
  );
  const percent =
    normalized && moduleKey(metric) === "persequencequalityscores";
  const model = useMemo(
    () => multiComparison(chosen, metric, percent),
    [chosen, metric, percent],
  );
  return (
    <section
      className="sample-table-section"
      aria-label="Multi-sample comparison"
    >
      <div className="analytics-actions">
        <ExportModeSelect value={exportMode} change={setExportMode} />
        <h2>Compare Samples</h2>
        <label>
          Metric{" "}
          <select
            aria-label="Multi-sample metric"
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
          >
            {comparisonMetrics.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        </label>
        {moduleKey(metric) === "persequencequalityscores" && (
          <label>
            <input
              type="checkbox"
              checked={normalized}
              onChange={(e) => setNormalized(e.target.checked)}
            />
            Normalize to reported Total Sequences (%)
          </label>
        )}
        <button
          className="button small"
          disabled={!chosen.length}
          onClick={() =>
            saveFile(
              sourceExport(chosen, metric, ",", exportMode),
              "fastqc-comparison.csv",
              "text/csv;charset=utf-8",
            )
          }
        >
          Export source CSV
        </button>
        <button
          className="button small"
          disabled={!chosen.length}
          onClick={() =>
            saveFile(
              sourceExport(chosen, metric, "\t", exportMode),
              "fastqc-comparison.tsv",
              "text/tab-separated-values;charset=utf-8",
            )
          }
        >
          Export source TSV
        </button>
      </div>
      <p className="inline-note">
        Select read files above or in Overview. Legend entries toggle individual
        curves. Each filename and report identity stays separate, including
        lanes and R1 / R2.
      </p>
      {!chosen.length && (
        <p role="status">
          No samples selected. Choose one or more saved read results to compare.
        </p>
      )}
      {chosen.length > 12 && (
        <p className="inline-note">
          {chosen.length} selected files may produce crowded plots. Reduce the
          shared selection for clearer inspection.
        </p>
      )}
      {model.notes.map((note) => (
        <p className="inline-note" key={note}>
          {note}
        </p>
      ))}
      {!!model.unavailable.length && (
        <details>
          <summary>Unavailable metrics ({model.unavailable.length})</summary>
          <ul>
            {model.unavailable.map((name, i) => (
              <li key={i}>{name}</li>
            ))}
          </ul>
        </details>
      )}
      {model.groups.map((group, i) => (
        <div key={i}>
          {model.groups.length > 1 && (
            <h3>
              Compatible group {i + 1} ·{" "}
              {group.members.map((m) => m.name).join(", ")}
            </h3>
          )}
          <AnalyticsChart
            group={group}
            quality={moduleKey(metric) === "perbasesequencequality"}
          />
        </div>
      ))}
    </section>
  );
}
