import { useEffect, useMemo, useState } from "react";
import { api, url } from "./api";
import { NativePlot, saveFile } from "./AnalyticsChart";
import ProjectCohort from "./ProjectCohort";
import { cohortMetrics, cohortPlot, pointLabel } from "./cohort";
import type { CohortPoint, CohortResult } from "./cohort";
import type { DetailTab } from "./types";

type Query = Record<string, unknown>;
export default function ProjectComparison({
  projectId,
  openAnalysis,
}: {
  projectId: string;
  openAnalysis: (id: string, tab: DetailTab, reportId?: string) => void;
}) {
  const base = `api/projects/${projectId}/comparisons`;
  const [projects, setProjects] = useState<string[]>([projectId]);
  const [samples, setSamples] = useState<string[] | null>(null),
    [runs, setRuns] = useState<string[] | null>(null);
  const [metric, setMetric] = useState("q30_percent"),
    [groupBy, setGroupBy] = useState("file");
  const [filters, setFilters] = useState<Record<string, string>>({}),
    [reference, setReference] = useState("");
  const [adapter, setAdapter] = useState(""),
    [position, setPosition] = useState("");
  const [result, setResult] = useState<CohortResult | null>(null),
    [query, setQuery] = useState<Query | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [stage, setStage] = useState("raw_fastq");
  const load = async (body: Query) => {
    setBusy(true);
    setError("");
    try {
      const value = await api<CohortResult>(`${base}/query`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setResult(value);
      setQuery(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot load comparison");
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    void load({ project_ids: [projectId] });
  }, [projectId]);
  const plot = useMemo(() => result && cohortPlot(result), [result]);
  const apply = () => {
    if (samples?.length === 0 || runs?.length === 0) {
      setError("Select at least one sample/run, or use All project scope.");
      return;
    }
    const activeFilters = Object.fromEntries(
      Object.entries(filters)
        .filter(([, value]) => value !== "")
        .map(([key, value]) => [
          key,
          key.startsWith("length_") ? Number(value) : value,
        ]),
    );
    void load({
      project_ids: projects,
      sample_ids: projects.length === 1 ? samples : null,
      sequencing_run_ids: projects.length === 1 ? runs : null,
      metric,
      group_by: groupBy,
      filters: activeFilters,
      rule:
        metric === "q30_percent" && reference !== ""
          ? { minimum_percent: reference }
          : null,
      ...(metric === "adapter_bin_percent"
        ? { adapter: adapter || null, position: position || null }
        : {}),
    });
  };
  const download = async (format: "csv" | "tsv", exclusions = false) => {
    if (!query || !result) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(url(`${base}/export`), {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-QualiDock-Request": "1",
        },
        body: JSON.stringify({
          ...query,
          fingerprint: result.fingerprint,
          definition_id: result.selected_group,
          format,
          exclusions,
        }),
      });
      if (!response.ok) {
        const failure = await response.json();
        throw new Error(
          typeof failure.detail === "string"
            ? failure.detail
            : "Cannot export; refresh comparison.",
        );
      }
      saveFile(
        await response.text(),
        `qualidock-cohort${exclusions ? "-excluded" : ""}.${format}`,
        format === "csv"
          ? "text/csv;charset=utf-8"
          : "text/tab-separated-values;charset=utf-8",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot export comparison");
    } finally {
      setBusy(false);
    }
  };
  const sources = (point: CohortPoint) => (
    <details>
      <summary>
        Sources (
        {
          (point.sources.length ? point.sources : (point.references ?? []))
            .length
        }
        )
      </summary>
      {(point.sources.length ? point.sources : (point.references ?? [])).map(
        (source, i) => (
          <div
            key={`${source.analysis_id}-${source.file_id}-${i}`}
            className="cohort-source"
          >
            <span>
              {source.filename || source.file_id} ·{" "}
              {source.analysis_id.slice(-8)}
            </span>
            <small>
              {Object.entries(source.tools ?? {})
                .map(([tool, version]) => `${tool} ${version ?? "unknown"}`)
                .join(" · ")}
            </small>
            <div className="project-actions">
              <button
                className="button small"
                onClick={() =>
                  openAnalysis(
                    source.analysis_id,
                    "metrics",
                    source.report_id ?? undefined,
                  )
                }
              >
                Inspect source QC
              </button>
              <button
                className="button small"
                onClick={() => openAnalysis(source.analysis_id, "reports")}
              >
                Original reports
              </button>
            </div>
          </div>
        ),
      )}
      <pre>
        {JSON.stringify(
          {
            definition: point.definition,
            sources: point.sources,
            context: point.context,
          },
          null,
          2,
        )}
      </pre>
    </details>
  );
  const table = (points: CohortPoint[], excluded: boolean) => (
    <div className="table-scroll" tabIndex={0}>
      <table
        aria-label={
          excluded ? "Excluded cohort evidence" : "Cohort metric values"
        }
      >
        <thead>
          <tr>
            <th>Run / sample / read</th>
            <th>Reported value</th>
            <th>
              {excluded ? "Unavailable / excluded reason" : "Reference check"}
            </th>
            <th>Provenance</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.id}>
              <td>
                {pointLabel(point)}
                <small>
                  {point.context.project_name} ·{" "}
                  {point.context.input_stage ?? "unknown stage"}
                </small>
              </td>
              <td>
                {point.value === null
                  ? "Unavailable"
                  : `${point.value} ${point.unit}`}
                <small>Raw: {point.raw_value ?? "Unavailable"}</small>
                {point.denominator !== undefined &&
                  point.denominator !== null && (
                    <small>
                      {point.numerator} / {point.denominator} quality bases
                    </small>
                  )}
              </td>
              <td>
                {excluded ? (
                  point.reason
                ) : point.rule_result === "review" ? (
                  <strong className="cohort-review">
                    Review: below declared reference
                  </strong>
                ) : point.rule_result === "within_declared_reference" ? (
                  "Within declared reference"
                ) : (
                  "Not requested"
                )}
                {point.context_note && <small>{point.context_note}</small>}
                {point.definition_note && (
                  <small>{point.definition_note}</small>
                )}
              </td>
              <td>{sources(point)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return (
    <section aria-label="Project cohort comparison">
      <h2>Compare runs & projects</h2>
      <p className="inline-note">
        Explore saved file-level evidence. Compatible definitions and input
        stages are compared separately. R1/R2 and lanes retain their identities;
        selection never starts QC.
      </p>
      <div className="project-actions">
        <label className="field-label">
          Comparison metric
          <select
            aria-label="Comparison metric"
            value={metric}
            onChange={(e) => {
              setMetric(e.target.value);
              if (
                !["reads", "bases", "q20_percent", "q30_percent"].includes(
                  e.target.value,
                )
              )
                setGroupBy("file");
            }}
          >
            {cohortMetrics.map(([id, title]) => (
              <option key={id} value={id}>
                {title}
              </option>
            ))}
          </select>
        </label>
        <label className="field-label">
          Display scope
          <select
            aria-label="Comparison display scope"
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value)}
          >
            <option value="file">Individual read files</option>
            <option
              value="run"
              disabled={
                !["reads", "bases", "q20_percent", "q30_percent"].includes(
                  metric,
                )
              }
            >
              Selected-file totals per run
            </option>
          </select>
        </label>
        <button className="button primary" disabled={busy} onClick={apply}>
          Apply comparison
        </button>
      </div>
      <details>
        <summary>Choose samples, sequencing runs or projects</summary>
        <ProjectCohort
          projectId={projectId}
          kind="projects"
          selected={projects}
          change={(ids) => {
            setProjects(ids ?? [projectId]);
            setSamples(null);
            setRuns(null);
          }}
          maximum={5}
          allowAll={false}
          required={[projectId]}
        />
        {projects.length === 1 ? (
          <div className="cohort-pickers">
            <ProjectCohort
              projectId={projectId}
              kind="samples"
              selected={samples}
              change={setSamples}
            />
            <ProjectCohort
              projectId={projectId}
              kind="sequencing-runs"
              selected={runs}
              change={setRuns}
            />
          </div>
        ) : (
          <p>
            Includes active samples and runs in the selected projects. Use
            context filters to narrow the comparison.
          </p>
        )}
      </details>
      <details>
        <summary>Context filters & optional review reference</summary>
        <div className="project-actions">
          {[
            ["platform", "Platform"],
            ["assay", "Assay / protocol"],
            ["library_type", "Library type"],
            ["input_stage", "Input stage"],
          ].map(([key, label]) => (
            <label className="field-label" key={key}>
              {label}
              <select
                aria-label={`Comparison ${label}`}
                value={filters[key] ?? ""}
                onChange={(e) =>
                  setFilters({ ...filters, [key]: e.target.value })
                }
              >
                <option value="">All declared contexts</option>
                {[
                  ...new Set([
                    ...(result?.facets[key] ?? []),
                    ...(filters[key] ? [filters[key]] : []),
                  ]),
                ].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
          ))}
          {[
            ["date_from", "Sequencing date from"],
            ["date_to", "Sequencing date to"],
            ["length_min", "File minimum length ≥ (bp)"],
            ["length_max", "File maximum length ≤ (bp)"],
          ].map(([key, label]) => (
            <label className="field-label" key={key}>
              {label}
              <input
                aria-label={label}
                type={key.startsWith("date_") ? "date" : "number"}
                min="0"
                value={filters[key] ?? ""}
                onChange={(e) =>
                  setFilters({ ...filters, [key]: e.target.value })
                }
              />
            </label>
          ))}
          {metric === "q30_percent" && (
            <label className="field-label">
              Optional Q30 minimum (%)
              <input
                aria-label="Optional Q30 minimum (%)"
                type="number"
                min="0"
                max="100"
                step="any"
                value={reference}
                placeholder="No reference applied"
                onChange={(e) => setReference(e.target.value)}
              />
            </label>
          )}
        </div>
        <p className="inline-note">
          The Q30 reference is user-declared and produces a review signal, not
          an assay or sample failure. Dates refer to declared sequencing dates.
          Length filters select complete files without filtering reads.
        </p>
      </details>
      {metric === "adapter_bin_percent" && (
        <div className="project-actions">
          <label className="field-label">
            Adapter category
            <select
              aria-label="Adapter category"
              value={adapter}
              onChange={(e) => setAdapter(e.target.value)}
            >
              <option value="">Select original category</option>
              {result?.adapter_categories.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="field-label">
            Original position bin
            <select
              aria-label="Original position bin"
              value={position}
              onChange={(e) => setPosition(e.target.value)}
            >
              <option value="">Select reported bin</option>
              {result?.position_bins.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <p>
            Apply once to discover saved categories, then select a category/bin
            and apply. Cross-analysis adapter definitions require recorded
            configuration identity.
          </p>
        </div>
      )}
      {busy && <p role="status">Loading saved comparison evidence…</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <section aria-label="Cohort comparison result" aria-busy={busy}>
          <h3>{result.metric.name}</h3>
          <p>{result.metric.description}</p>
          {!!result.unknown_stage_run_total && (
            <details>
              <summary>
                Declare input stage for unknown runs (
                {result.unknown_stage_run_total})
              </summary>
              <p>
                Only change these declarations if you know the inputs'
                processing stage. Historical QC and release evidence remain
                unchanged.
              </p>
              <ul>
                {result.unknown_stage_runs.map((run) => (
                  <li key={run.id}>{run.name}</li>
                ))}
              </ul>
              <div className="project-actions">
                <label>
                  Input stage for listed unknown runs
                  <select
                    aria-label="Input stage for listed unknown runs"
                    value={stage}
                    onChange={(e) => setStage(e.target.value)}
                  >
                    <option value="raw_fastq">Raw FASTQ</option>
                    <option value="upstream_processed">
                      Upstream processed
                    </option>
                  </select>
                </label>
                <button
                  className="button small"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError("");
                    try {
                      await api(`${base}/run-context`, {
                        method: "PATCH",
                        body: JSON.stringify({
                          project_ids:
                            (query?.project_ids as string[]) ?? projects,
                          records: result.unknown_stage_runs.map(
                            ({ id, revision }) => ({ id, revision }),
                          ),
                          fields: { input_stage: stage },
                        }),
                      });
                      await load(query ?? {});
                    } catch (err) {
                      setError(
                        err instanceof Error
                          ? err.message
                          : "Cannot update stage",
                      );
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Confirm stage for {result.unknown_stage_runs.length} listed
                  runs
                </button>
              </div>
              {result.unknown_stage_run_total >
                result.unknown_stage_runs.length && (
                <p>
                  Only the first {result.unknown_stage_runs.length} listed
                  records are updated; refresh to review remaining records.
                </p>
              )}
            </details>
          )}
          {result.groups.length > 0 && (
            <label className="field-label">
              Compatible definition
              <select
                aria-label="Compatible definition"
                value={result.selected_group ?? ""}
                disabled={busy}
                onChange={(e) =>
                  void load({
                    ...query,
                    offset: 0,
                    definition_id: e.target.value,
                  })
                }
              >
                {result.groups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.label} ({group.count})
                  </option>
                ))}
              </select>
            </label>
          )}
          {result.points.length > 0 && plot ? (
            <>
              <NativePlot view={plot} />
              {table(result.points, false)}
            </>
          ) : (
            <p className="inline-note">
              No comparable values in this scope. Inspect exclusions, available
              source reports, and input-stage declarations below.
            </p>
          )}
          <div className="project-actions">
            <span>
              {result.total} compatible · {result.excluded_total} unavailable /
              excluded
            </span>
            <button
              className="button small"
              disabled={busy || !result.total}
              onClick={() => void download("csv")}
            >
              Export cohort CSV
            </button>
            <button
              className="button small"
              disabled={busy || !result.total}
              onClick={() => void download("tsv")}
            >
              Export cohort TSV
            </button>
            <button
              className="button small"
              disabled={busy || !result.offset}
              onClick={() =>
                void load({
                  ...query,
                  offset: Math.max(0, result.offset - 100),
                })
              }
            >
              Previous comparison page
            </button>
            <button
              className="button small"
              disabled={
                busy ||
                result.offset + 100 >=
                  Math.max(result.total, result.excluded_total)
              }
              onClick={() =>
                void load({ ...query, offset: result.offset + 100 })
              }
            >
              Next comparison page
            </button>
          </div>
          {result.excluded_total > 0 && (
            <details>
              <summary>
                Unavailable & incompatible evidence ({result.excluded_total})
              </summary>
              {table(result.excluded, true)}
              <button
                className="button small"
                disabled={busy}
                onClick={() => void download("csv", true)}
              >
                Export excluded evidence CSV
              </button>
            </details>
          )}
          <p className="inline-note">
            {result.scope_note} Chart shows this page (up to 100 records);
            exports contain all records in the selected compatible definition.
            Spreadsheet-safe CSV/TSV preserves raw fractions and source
            provenance.
          </p>
        </section>
      )}
    </section>
  );
}
