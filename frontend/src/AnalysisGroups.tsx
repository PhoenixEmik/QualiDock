import { useMemo } from "react";
import type { Run, Sample } from "./types";
import { analyticsSamples } from "./analytics";
export default function AnalysisGroups({
  run,
  samples,
  selected,
  select,
  inspect,
}: {
  run: Run;
  samples: Sample[];
  selected?: Set<string>;
  select?: (s: Set<string>) => void;
  inspect?: (id: string) => void;
}) {
  const entities = useMemo(
    () => analyticsSamples(run, samples),
    [run, samples],
  );
  if (!run.sample_groups?.length) return null;
  return (
    <section
      className="sample-table-section analysis-groups"
      aria-label="Saved sample groups"
    >
      <h2>Sample groups</h2>
      <p className="inline-note">
        Organization metadata only. Lane and read results remain separate; no QC
        distributions are merged.
      </p>
      {run.sample_groups.map((group) => {
        const members = entities.filter(
          (entity) => entity.groupId === group.id,
        );
        return (
          <details key={group.id}>
            <summary>
              {select && (
                <input
                  type="checkbox"
                  aria-label={`Select group ${group.display_name}`}
                  checked={
                    members.length > 0 &&
                    members.every((e) => selected?.has(e.id))
                  }
                  disabled={!members.length}
                  ref={(el) => {
                    if (el)
                      el.indeterminate =
                        members.some((e) => selected?.has(e.id)) &&
                        !members.every((e) => selected?.has(e.id));
                  }}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => {
                    const next = new Set(selected);
                    for (const member of members) {
                      if (e.target.checked) next.add(member.id);
                      else next.delete(member.id);
                    }
                    select(next);
                  }}
                />
              )}
              {group.display_name} · {group.files.length} FASTQ files ·{" "}
              {group.source}
            </summary>
            <ul>
              {group.files.map((path) => {
                const member = members.find((e) => e.source === path),
                  record = run.input_pairing?.find((r) => r.path === path);
                return (
                  <li key={path}>
                    <span title={path}>
                      {path.split("/").pop()}
                      <small>
                        {[
                          record?.lane,
                          record?.chunk && `Chunk ${record.chunk}`,
                          record?.read,
                          record?.source,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "Unpaired / metadata unavailable"}
                      </small>
                    </span>
                    {inspect && member ? (
                      <button
                        className="button small"
                        onClick={() => inspect(member.id)}
                      >
                        Inspect read
                      </button>
                    ) : inspect ? (
                      <small>No saved FastQC result</small>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </details>
        );
      })}
    </section>
  );
}
