import type { Sample } from "./types";
import { findModule, moduleNames, moduleStatus } from "./qc";
import { State } from "./Feedback";

export default function ModuleNavigation({
  samples,
  metric,
  select,
}: {
  samples: Sample[];
  metric: string;
  select: (name: string) => void;
}) {
  const names = [...new Set(samples.flatMap(moduleNames))];
  return (
    <nav className="qc-module-navigation" aria-label="FastQC modules">
      {names.map((name) => (
        <button
          key={name}
          type="button"
          className={metric === name ? "selected" : ""}
          aria-current={metric === name ? "true" : undefined}
          onClick={() => {
            select(name);
            window.requestAnimationFrame(() =>
              document.getElementById("qc-metric-heading")?.focus(),
            );
          }}
        >
          <span>{name}</span>
          <span className="qc-module-states">
            {samples.map((sample, i) => {
              const module = findModule(sample, name);
              return (
                <span
                  key={sample.id}
                  title={`${sample.name}${module?.summary_status ? ` · summary.txt: ${module.summary_status}` : ""}`}
                >
                  {samples.length > 1 && <small>{i === 0 ? "R1" : "R2"}</small>}
                  <State value={moduleStatus(sample, name)} />
                </span>
              );
            })}
          </span>
        </button>
      ))}
    </nav>
  );
}
