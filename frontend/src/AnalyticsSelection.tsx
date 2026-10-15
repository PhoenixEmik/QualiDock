import { useState } from "react";
import { type AnalyticsSample, toggleSelection } from "./analytics";
export default function AnalyticsSelection({
  entities,
  selected,
  select,
}: {
  entities: AnalyticsSample[];
  selected: Set<string>;
  select: (s: Set<string>) => void;
}) {
  const [search, setSearch] = useState("");
  const visible = entities.filter((e) =>
    e.name.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <details className="analytics-selection">
      <summary>
        Shared sample selection · {selected.size} of {entities.length} selected
      </summary>
      <div className="analytics-actions">
        <label>
          Search selectable samples{" "}
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <button
          className="button small"
          onClick={() => select(new Set(entities.map((e) => e.id)))}
        >
          Select All
        </button>
        <button className="button small" onClick={() => select(new Set())}>
          Clear Selection
        </button>
        <button
          className="button small"
          onClick={() => select(new Set(entities.slice(0, 6).map((e) => e.id)))}
        >
          Select first 6
        </button>
      </div>
      <div className="analytics-selection-list">
        {visible.map((entity) => (
          <div
            key={entity.id}
            title={`${entity.source}\n${entity.tool} ${entity.version || "version unavailable"}\nReport: ${entity.id}${entity.pair ? "\nConfirmed pair: " + entity.pair : ""}`}
          >
            <label>
              <input
                type="checkbox"
                checked={selected.has(entity.id)}
                onChange={() => select(toggleSelection(selected, entity.id))}
              />
              <span>
                {entity.name}
                {entity.read ? " · " + entity.read : ""}
                <small className="subtle">{entity.source}</small>
              </span>
            </label>
            <button
              className="button small"
              aria-label={`Select only ${entity.name}`}
              onClick={(e) => {
                e.preventDefault();
                select(new Set([entity.id]));
              }}
            >
              Only
            </button>
          </div>
        ))}
      </div>
      <p className="inline-note">
        Selection is shared across Overview and Compare Samples. The initial
        selection is limited to six read files. Unmapped MultiQC rows remain
        distinct and have no invented FASTQ relationship.
      </p>
    </details>
  );
}
