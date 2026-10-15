import { useMemo, useState } from "react";
import type { MultiQCSummary } from "./types";
import {
  type AnalyticsSample,
  type Sort,
  sortStats,
  statsExport,
  rawUnit,
  toggleSelection,
} from "./analytics";
import { saveFile } from "./AnalyticsChart";
export default function GeneralStatistics({
  summary,
  entities,
  selected,
  select,
  version,
}: {
  summary?: MultiQCSummary;
  version?: string | null;
  entities: AnalyticsSample[];
  selected: Set<string>;
  select: (s: Set<string>) => void;
}) {
  const [search, setSearch] = useState(""),
    [hidden, setHidden] = useState<Set<string>>(new Set()),
    [sorts, setSorts] = useState<Sort[]>([{ key: "sample", direction: 1 }]);
  const rows = useMemo(
    () => sortStats(summary?.rows || [], search, sorts),
    [summary, search, sorts],
  );
  const columns = (summary?.columns || []).filter((c) => !hidden.has(c.key));
  const ids = useMemo(
    () =>
      new Map(
        entities.filter((e) => e.multiqcName).map((e) => [e.multiqcName, e.id]),
      ),
    [entities],
  );
  const sort = (key: string, append: boolean) =>
    setSorts((old) => {
      const existing = old.find((s) => s.key === key),
        next: Sort = { key, direction: existing?.direction === 1 ? -1 : 1 };
      return append ? [...old.filter((s) => s.key !== key), next] : [next];
    });
  const sortLabel = (key: string) => {
    const i = sorts.findIndex((s) => s.key === key);
    return i < 0
      ? ""
      : ` ${sorts[i].direction === 1 ? "↑" : "↓"}${sorts.length > 1 ? " " + (i + 1) : ""}`;
  };
  const exportRows = (extension: "csv" | "tsv") =>
    saveFile(
      statsExport(rows, columns, extension === "csv" ? "," : "\t"),
      `multiqc-general-statistics.${extension}`,
      "text/plain;charset=utf-8",
    );
  return (
    <section
      className="sample-table-section analytics-statistics"
      aria-label="MultiQC General Statistics"
    >
      <div className="section-heading">
        <h2>General Statistics</h2>
        <span className="subtle">
          MultiQC {summary?.version || version || "version unavailable"}
        </span>
      </div>
      <p className="inline-note">
        Saved MultiQC values, without display scaling. Missing values are
        unavailable. Column descriptions may describe MultiQC’s formatted
        display; raw units are shown here.
      </p>
      {!summary?.rows.length ? (
        <p role="status">
          {summary?.message ||
            "No saved MultiQC General Statistics. FastQC results remain available below; the Reports tab can generate a combined report."}
        </p>
      ) : (
        <>
          <div className="analytics-actions">
            <label>
              Search statistics{" "}
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Sample name"
              />
            </label>
            <details className="analytics-columns">
              <summary>Columns ({columns.length})</summary>
              <div>
                {summary.columns.map((c) => (
                  <label key={c.key}>
                    <input
                      type="checkbox"
                      checked={!hidden.has(c.key)}
                      onChange={() => setHidden(toggleSelection(hidden, c.key))}
                    />
                    {c.namespace} · {c.title}
                  </label>
                ))}
              </div>
            </details>
            <button className="button small" onClick={() => exportRows("csv")}>
              Export statistics CSV
            </button>
            <button className="button small" onClick={() => exportRows("tsv")}>
              Export statistics TSV
            </button>
          </div>
          <p className="inline-note">
            {rows.length} samples. Click a heading to sort; Shift-click adds a
            sort priority. Exports include filtered rows and visible columns.
          </p>
          <div
            className="table-scroll analytics-table"
            tabIndex={0}
            role="region"
            aria-label="General Statistics table"
          >
            <table>
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      aria-label="Select all filtered statistics samples"
                      checked={
                        rows.length > 0 &&
                        rows.every((r) => selected.has(ids.get(r.sample) || ""))
                      }
                      onChange={(e) => {
                        const next = new Set(selected);
                        rows.forEach((r) => {
                          const id = ids.get(r.sample);
                          if (id) {
                            if (e.target.checked) next.add(id);
                            else next.delete(id);
                          }
                        });
                        select(next);
                      }}
                    />
                  </th>
                  <th
                    aria-sort={
                      sorts[0]?.key === "sample"
                        ? sorts[0].direction === 1
                          ? "ascending"
                          : "descending"
                        : "none"
                    }
                  >
                    <button
                      className="analytics-sort"
                      onClick={(e) => sort("sample", e.shiftKey)}
                    >
                      Sample{sortLabel("sample")}
                    </button>
                  </th>
                  {columns.map((c) => (
                    <th
                      key={c.key}
                      title={`${c.namespace}: ${c.description}\nRaw field: ${c.raw_key}; original display suffix: ${c.unit || "none"}`}
                      aria-sort={
                        sorts[0]?.key === c.key
                          ? sorts[0].direction === 1
                            ? "ascending"
                            : "descending"
                          : "none"
                      }
                    >
                      <button
                        className="analytics-sort"
                        onClick={(e) => sort(c.key, e.shiftKey)}
                      >
                        {c.title}
                        {rawUnit(c) ? ` (${rawUnit(c)})` : " (raw)"}
                        {sortLabel(c.key)}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const id = ids.get(row.sample);
                  const entity = entities.find((e) => e.id === id);
                  return (
                    <tr
                      key={row.sample}
                      className={id && selected.has(id) ? "row-selected" : ""}
                    >
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Select statistics ${row.sample}`}
                          disabled={!id}
                          checked={!!id && selected.has(id)}
                          onChange={() =>
                            id && select(toggleSelection(selected, id))
                          }
                        />
                      </td>
                      <th scope="row" title={entity?.source}>
                        {row.sample}
                        {entity?.read && <small> · {entity.read}</small>}
                        {!entity?.fastqc && (
                          <small className="subtle">
                            {" "}
                            · FASTQ mapping unavailable
                          </small>
                        )}
                      </th>
                      {columns.map((c) => (
                        <td className="mono" key={c.key}>
                          {row.values[c.key] ?? (
                            <span className="subtle">Unavailable</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
