import { useState } from "react";
import type { SampleConfiguration } from "./types";
import {
  assignPair,
  moveToGroup,
  pairRecords,
  removePair,
} from "./sampleConfig";
export default function SampleEditor({
  value,
  change,
  busy,
}: {
  value: SampleConfiguration;
  change: (v: SampleConfiguration) => void;
  busy: boolean;
}) {
  const [r1, setR1] = useState(""),
    [r2, setR2] = useState(""),
    [lane, setLane] = useState(""),
    [chunk, setChunk] = useState(""),
    [error, setError] = useState(""),
    [groupName, setGroupName] = useState(""),
    [groupSeed, setGroupSeed] = useState("");
  const pairs = pairRecords(value.input_pairing),
    unpaired = value.input_pairing.filter((r) => !r.paired);
  const startingFile = value.input_pairing.find((r) => r.path === groupSeed);
  return (
    <section
      className="form-section sample-editor"
      aria-label="Sample and pairing editor"
    >
      <div className="form-heading">
        <h2>Samples & read pairing</h2>
        <small>
          {value.sample_groups.length} groups · {pairs.length} pairs ·{" "}
          {value.input_pairing.length} FASTQ files
        </small>
      </div>
      <p className="inline-note">
        Pairing and grouping are metadata only. Manual assignments reflect your
        choices; they do not verify biological relationships. Each FASTQ is
        analyzed independently.
      </p>
      {value.pairing_note && <p role="status">{value.pairing_note}</p>}
      {unpaired.some((record) => record.read || record.ambiguous) && (
        <p className="inline-note" role="status">
          Some read-labeled files have missing or ambiguous mates in this
          selection. Review them below; unpaired files can still be analyzed.
        </p>
      )}
      <details open>
        <summary>Review read pairs ({pairs.length})</summary>
        <div className="metadata-pairs">
          {pairs.map((pair) => (
            <div key={pair.key}>
              <strong>
                {pair.r1?.name || "R1 missing"} /{" "}
                {pair.r2?.name || "R2 missing"}
              </strong>
              <small>
                {pair.r1?.lane || "Lane unspecified"} ·{" "}
                {pair.r1?.chunk || "Chunk unspecified"} ·{" "}
                {pair.r1?.source || "auto"}
              </small>
              {pair.r1?.source === "auto" && (
                <button
                  disabled={busy}
                  className="button small"
                  onClick={() =>
                    change({
                      ...value,
                      input_pairing: value.input_pairing.map((r) =>
                        r.pair_key === pair.key
                          ? { ...r, source: "confirmed" }
                          : r,
                      ),
                    })
                  }
                >
                  Confirm pair
                </button>
              )}
              <button
                disabled={busy}
                className="button small"
                aria-label={`Remove pairing ${pair.r1?.name}`}
                onClick={() => change(removePair(value, pair.key))}
              >
                Remove pairing
              </button>
            </div>
          ))}
        </div>
      </details>
      <details>
        <summary>Assign or correct a pair</summary>
        <p className="inline-note">
          Remove an existing pairing first to reassign its files. Files may also
          remain single-end or unpaired.
        </p>
        <div className="analytics-actions">
          <label>
            R1{" "}
            <select
              aria-label="Assign R1 file"
              value={r1}
              onChange={(e) => setR1(e.target.value)}
              disabled={busy}
            >
              <option value="">Choose file</option>
              {unpaired.map((r) => (
                <option key={r.path} value={r.path}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            R2{" "}
            <select
              aria-label="Assign R2 file"
              value={r2}
              onChange={(e) => setR2(e.target.value)}
              disabled={busy}
            >
              <option value="">Choose file</option>
              {unpaired.map((r) => (
                <option key={r.path} value={r.path}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Lane{" "}
            <input
              aria-label="Pair lane"
              maxLength={80}
              value={lane}
              onChange={(e) => setLane(e.target.value)}
              disabled={busy}
            />
          </label>
          <label>
            Chunk{" "}
            <input
              aria-label="Pair chunk"
              maxLength={80}
              value={chunk}
              onChange={(e) => setChunk(e.target.value)}
              disabled={busy}
            />
          </label>
          <button
            className="button small"
            disabled={busy || !r1 || !r2}
            onClick={() => {
              try {
                change(
                  assignPair(
                    value,
                    "manual:" + crypto.randomUUID(),
                    r1,
                    r2,
                    lane || null,
                    chunk || null,
                  ),
                );
                setR1("");
                setR2("");
                setError("");
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Assign pair
          </button>
        </div>
        {error && <p role="alert">{error}</p>}
      </details>
      <details open>
        <summary>Sample groups & unpaired reads</summary>
        <p className="inline-note">
          Moving one paired read moves its mate too. Remove the pairing first if
          these files belong to separate groups.
        </p>
        <div className="analytics-actions">
          <label>
            New group name{" "}
            <input
              value={groupName}
              maxLength={120}
              onChange={(e) => setGroupName(e.target.value)}
              disabled={busy}
            />
          </label>
          <label>
            Starting file{" "}
            <select
              aria-label="New sample starting file"
              value={groupSeed}
              onChange={(e) => setGroupSeed(e.target.value)}
              disabled={busy}
            >
              <option value="">Choose file</option>
              {value.input_pairing.map((r) => (
                <option key={r.path} value={r.path}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="button small"
            disabled={busy || !groupName.trim() || !startingFile}
            onClick={() => {
              if (!startingFile) return;
              const id = "sample:" + crypto.randomUUID();
              change(
                moveToGroup(
                  {
                    ...value,
                    sample_groups: [
                      ...value.sample_groups,
                      {
                        id,
                        display_name: groupName.trim(),
                        files: [],
                        source: "manual",
                      },
                    ],
                  },
                  startingFile.path,
                  id,
                ),
              );
              setGroupName("");
              setGroupSeed("");
            }}
          >
            Create sample group
          </button>
        </div>
        <div className="metadata-groups">
          {value.sample_groups.map((group) => (
            <details key={group.id} open>
              <summary>
                {group.display_name} · {group.files.length} files ·{" "}
                {group.source}
              </summary>
              <button
                className="button small"
                disabled={busy || group.source !== "auto"}
                onClick={() =>
                  change({
                    ...value,
                    sample_groups: value.sample_groups.map((g) =>
                      g.id === group.id ? { ...g, source: "confirmed" } : g,
                    ),
                  })
                }
              >
                Confirm group
              </button>
              <label>
                Sample display name{" "}
                <input
                  aria-label={`Sample name ${group.display_name}`}
                  maxLength={120}
                  value={group.display_name}
                  disabled={busy}
                  onChange={(e) =>
                    change({
                      ...value,
                      sample_groups: value.sample_groups.map((g) =>
                        g.id === group.id
                          ? {
                              ...g,
                              display_name: e.target.value,
                              source: "manual",
                            }
                          : g,
                      ),
                    })
                  }
                />
              </label>
              <ul>
                {group.files.map((path) => {
                  const file = value.input_pairing.find(
                    (r) => r.path === path,
                  )!;
                  return (
                    <li key={path}>
                      <span title={path}>
                        {file.name}
                        <small>
                          {[file.lane, file.chunk, file.read]
                            .filter(Boolean)
                            .join(" · ") || "Lane/read unspecified"}
                        </small>
                      </span>
                      <label>
                        Group{" "}
                        <select
                          aria-label={`Group for ${file.name}`}
                          value={group.id}
                          onChange={(e) =>
                            change(moveToGroup(value, path, e.target.value))
                          }
                          disabled={busy}
                        >
                          {value.sample_groups.map((g) => (
                            <option key={g.id} value={g.id}>
                              {g.display_name}
                              {value.sample_groups.some(
                                (other) =>
                                  other.id !== g.id &&
                                  other.display_name === g.display_name,
                              )
                                ? ` · ${g.id}`
                                : ""}
                            </option>
                          ))}
                        </select>
                      </label>
                      {!file.paired && (
                        <label>
                          Read type{" "}
                          <select
                            aria-label={`Read type ${file.name}`}
                            value={
                              file.assignment === "single"
                                ? "single"
                                : "unpaired"
                            }
                            onChange={(e) =>
                              change({
                                ...value,
                                input_pairing: value.input_pairing.map((r) =>
                                  r.path === path
                                    ? {
                                        ...r,
                                        assignment: e.target.value as
                                          "single" | "unpaired",
                                        source: "manual",
                                        read: null,
                                      }
                                    : r,
                                ),
                              })
                            }
                            disabled={busy}
                          >
                            <option value="unpaired">
                              Unpaired / incomplete
                            </option>
                            <option value="single">Single-end</option>
                          </select>
                        </label>
                      )}
                    </li>
                  );
                })}
              </ul>
            </details>
          ))}
        </div>
      </details>
    </section>
  );
}

/** Shared optional review; metadata remains validated by the existing API. */
export function ReadRelationships({
  value,
  change,
  prepare,
  busy,
}: {
  value: SampleConfiguration | null;
  change: (value: SampleConfiguration) => void;
  prepare: () => Promise<unknown>;
  busy: boolean;
}) {
  return (
    <details className="processing-advanced">
      <summary>Review read relationships (optional)</summary>
      {value ? (
        <SampleEditor value={value} change={change} busy={busy} />
      ) : (
        <button
          className="button"
          disabled={busy}
          onClick={() => void prepare()}
        >
          Detect and review pairs
        </button>
      )}
    </details>
  );
}
