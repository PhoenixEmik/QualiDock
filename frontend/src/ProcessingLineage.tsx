import { useRef, useState, useEffect } from "react";
import { api, modeLabel, url } from "./api";
import type { DetailTab } from "./types";
interface Source {
  path: string;
  parent_recorded: boolean;
  integrity: string;
  read?: string;
  paired?: boolean;
  lane?: string;
  chunk?: string;
}
interface Lineage {
  scope: string;
  warnings: string[];
  nodes: {
    id: string;
    name: string;
    mode: string;
    state: string;
    tools: Record<string, string | null>;
    processors: { name: string; version: string }[];
    parameters: Record<string, unknown>;
    inputs: Source[];
    parents: {
      parent_id: string;
      dataset_id: string;
      input_path: string | null;
      integrity: string;
      ancestry: string;
      recorded_sha256: string | null;
    }[];
    derived_datasets: {
      id: string;
      path: string;
      source: string;
      read: string | null;
      paired: boolean;
      unit_id: string;
      records: number;
      bases: number;
      sha256: string;
    }[];
    rerun_of: string | null;
    source_run_id: string | null;
    report_count: number;
    omitted_inputs: number;
    omitted_datasets: number;
    omitted_parents: number;
  }[];
}
const status = (value: string) => value.replaceAll("_", " ");
export default function ProcessingLineage({
  runId,
  navigate,
}: {
  runId: string;
  navigate: (id: string, tab?: DetailTab) => void;
}) {
  const [data, setData] = useState<Lineage | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
  const load = async () => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setLoading(true);
    setError("");
    try {
      const result = await api<Lineage>(`api/runs/${runId}/lineage`, {
        signal: controller.signal,
      });
      if (!controller.signal.aborted) setData(result);
    } catch (err) {
      if (!controller.signal.aborted)
        setError(
          err instanceof Error ? err.message : "Source history unavailable",
        );
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  };
  return (
    <details
      className="analysis-inputs processing-lineage"
      onToggle={(event) => {
        if (event.currentTarget.open && !data && !loading) void load();
      }}
    >
      <summary>Processing Lineage</summary>
      <section aria-label="Processing Lineage" aria-busy={loading}>
        <p className="inline-note">
          Recorded source history. Metadata matches are not fresh checksums or
          full-file validation. Independent files, lanes and mates remain
          separate.
        </p>
        {loading && <p role="status">Loading source history…</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button
          className="text-button"
          disabled={loading}
          onClick={() => void load()}
        >
          Refresh source history
        </button>
        {data?.warnings.map((w) => (
          <p key={w} className="inline-note">
            {w}
          </p>
        ))}
        <ol className="lineage-steps">
          {data?.nodes.map((node) => (
            <li key={node.id}>
              <div className="section-heading">
                <h3>{node.name}</h3>
                {node.id !== runId && (
                  <button
                    className="text-button"
                    onClick={() => navigate(node.id)}
                  >
                    Open analysis {node.id}
                  </button>
                )}
              </div>
              <p>
                <strong>{modeLabel(node.mode)}</strong> · {node.state}
                {node.id === runId ? " · Selected analysis" : ""}
              </p>
              <p className="mono">{node.id}</p>
              <p>
                {[
                  ...Object.entries(node.tools).map(
                    ([name, version]) =>
                      `${name}: ${version || "version not recorded"}`,
                  ),
                  ...node.processors.map((p) => `${p.name}: ${p.version}`),
                ].join(" · ") || "Tool version not recorded"}
              </p>
              <details>
                <summary>Recorded parameters</summary>
                <pre>{JSON.stringify(node.parameters, null, 2)}</pre>
              </details>
              <h4>Source datasets</h4>
              <ul>
                {node.inputs.map((input) => (
                  <li key={input.path}>
                    <span className="mono">{input.path}</span>
                    <p>
                      {[
                        input.read,
                        input.lane,
                        input.chunk ? `chunk ${input.chunk}` : null,
                        input.paired
                          ? "paired"
                          : "independent / no confirmed pair",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <p>
                      {input.parent_recorded
                        ? "Recorded derived input"
                        : "External input; parent ancestry not recorded"}{" "}
                      · {status(input.integrity)}
                    </p>
                  </li>
                ))}
              </ul>
              {node.parents.map((edge, i) => (
                <p key={i}>
                  Parent dataset {edge.dataset_id} · {edge.parent_id} ·{" "}
                  {status(edge.integrity)} · {status(edge.ancestry)}
                  {edge.recorded_sha256 && (
                    <span className="mono">
                      {" "}
                      · Recorded SHA-256: {edge.recorded_sha256}
                    </span>
                  )}
                </p>
              ))}
              <h4>
                Derived datasets ({node.derived_datasets.length}
                {node.omitted_datasets
                  ? ` + ${node.omitted_datasets} omitted`
                  : ""}
                )
              </h4>
              <ul>
                {node.derived_datasets.map((output) => (
                  <li key={output.id}>
                    <span className="mono">{output.path}</span> · {output.id} ·{" "}
                    {output.read || "independent read"} · unit {output.unit_id}{" "}
                    · {output.records} reads / {output.bases} bases
                    <small className="mono">Source: {output.source}</small>
                    <a
                      href={url(
                        `api/runs/${node.id}/download?path=${encodeURIComponent(output.path)}`,
                      )}
                    >
                      Download recorded FASTQ {output.id}
                    </a>
                  </li>
                ))}
              </ul>
              {(node.omitted_inputs > 0 || node.omitted_parents > 0) && (
                <p>
                  Bounded view: {node.omitted_inputs} inputs and{" "}
                  {node.omitted_parents} parent references omitted. Open the
                  associated analysis for more details.
                </p>
              )}
              {!!node.report_count && (
                <button
                  className="text-button"
                  onClick={() => navigate(node.id, "reports")}
                >
                  View reports for {node.name}
                </button>
              )}
              {node.rerun_of && (
                <p>
                  Configuration reused from{" "}
                  <button
                    className="text-button"
                    onClick={() => navigate(node.rerun_of!)}
                  >
                    analysis {node.rerun_of}
                  </button>
                  . A rerun is not a derived-data edge.
                </p>
              )}
              {node.source_run_id && (
                <p>
                  Recorded report source:{" "}
                  <button
                    className="text-button"
                    onClick={() => navigate(node.source_run_id!)}
                  >
                    analysis {node.source_run_id}
                  </button>
                </p>
              )}
            </li>
          ))}
        </ol>
      </section>
    </details>
  );
}
