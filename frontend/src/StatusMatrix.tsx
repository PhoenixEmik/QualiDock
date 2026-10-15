import { useMemo, useState } from "react";
import {
  statusMatrix,
  statusValues,
  type AnalyticsSample,
  toggleSelection,
} from "./analytics";
export default function StatusMatrix({
  entities,
  selected,
  select,
  inspect,
}: {
  entities: AnalyticsSample[];
  selected: Set<string>;
  select: (s: Set<string>) => void;
  inspect: (id: string, module: string) => void;
}) {
  const [filter, setFilter] = useState("all"),
    [order, setOrder] = useState("name"),
    [problems, setProblems] = useState(false),
    [onlySelected, setOnlySelected] = useState(false),
    [search, setSearch] = useState("");
  const matrix = useMemo(() => statusMatrix(entities), [entities]);
  const columns = matrix.modules
    .map((name, i) => ({ name, i }))
    .filter(
      (c) =>
        !problems ||
        matrix.rows.some((row) => ["warn", "fail"].includes(row.statuses[c.i])),
    );
  const rows = matrix.rows
    .filter(
      (row) =>
        (!onlySelected || selected.has(row.entity.id)) &&
        row.entity.name.toLowerCase().includes(search.toLowerCase()) &&
        (filter === "all" || columns.some((c) => row.statuses[c.i] === filter)),
    )
    .sort((a, b) =>
      order === "fail"
        ? b.failures - a.failures ||
          b.warnings - a.warnings ||
          a.entity.name.localeCompare(b.entity.name)
        : order === "warn"
          ? b.warnings - a.warnings ||
            b.failures - a.failures ||
            a.entity.name.localeCompare(b.entity.name)
          : a.entity.name.localeCompare(b.entity.name),
    );
  return (
    <section className="sample-table-section" aria-label="FastQC status matrix">
      <h2>QC status heatmap</h2>
      <p className="inline-note">
        Original FastQC module classifications. A FAIL is module-specific and
        does not classify a read file as unusable. Click a cell to inspect the
        original module.
      </p>
      <div className="analytics-actions">
        <label>
          Search QC samples{" "}
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          Status{" "}
          <select
            aria-label="Filter QC status"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All statuses</option>
            {statusValues.map((s) => (
              <option key={s} value={s}>
                {s.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
        <label>
          Sort{" "}
          <select
            aria-label="Sort QC samples"
            value={order}
            onChange={(e) => setOrder(e.target.value)}
          >
            <option value="name">Filename</option>
            <option value="fail">Failure count</option>
            <option value="warn">Warning count</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={problems}
            onChange={(e) => setProblems(e.target.checked)}
          />
          Only modules with WARN / FAIL
        </label>
        <label>
          <input
            type="checkbox"
            checked={onlySelected}
            onChange={(e) => setOnlySelected(e.target.checked)}
          />
          Selected samples only
        </label>
      </div>
      <div
        className="table-scroll analytics-table status-matrix"
        tabIndex={0}
        role="region"
        aria-label="QC module status table"
      >
        <table>
          <thead>
            <tr>
              <th>Select</th>
              <th>FASTQ file</th>
              {columns.map((c) => (
                <th key={c.name}>{c.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.entity.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Select QC ${row.entity.name}`}
                    checked={selected.has(row.entity.id)}
                    onChange={() =>
                      select(toggleSelection(selected, row.entity.id))
                    }
                  />
                </td>
                <th
                  scope="row"
                  title={`${row.entity.source}\nReport: ${row.entity.id}`}
                >
                  {row.entity.name}
                  {row.entity.read && <small> · {row.entity.read}</small>}
                  <small className="subtle">
                    {row.failures} FAIL · {row.warnings} WARN
                  </small>
                </th>
                {columns.map((c) => {
                  const status = row.statuses[c.i];
                  return (
                    <td key={c.name}>
                      <button
                        className={`qc-status-cell ${status}`}
                        title={`${row.entity.name}\n${c.name}: ${status.toUpperCase()}\n${row.entity.source}`}
                        aria-label={`${row.entity.name}: ${c.name}: ${status.toUpperCase()}`}
                        onClick={() => inspect(row.entity.id, c.name)}
                      >
                        {filter === "all" || status === filter
                          ? status.toUpperCase()
                          : "·"}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && (
        <p role="status">No FASTQ results match these filters.</p>
      )}
    </section>
  );
}
