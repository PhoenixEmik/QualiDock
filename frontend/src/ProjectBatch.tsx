import { useEffect, useState } from "react";
import { api, date } from "./api";
import type { Config, DetailTab } from "./types";
import type { CatalogPage } from "./project";
import ProjectCohort from "./ProjectCohort";
import type { BatchAttempt, BatchPlan } from "./batch";
import { batchActive, stageLabel } from "./batch";

export default function ProjectBatch({
  projectId,
  openAnalysis,
}: {
  projectId: string;
  openAnalysis: (id: string, tab: DetailTab) => void;
}) {
  const base = `api/projects/${projectId}`;
  const [config, setConfig] = useState<Config | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [sampleIds, setSampleIds] = useState<string[] | null>(null),
    [runIds, setRunIds] = useState<string[] | null>(null);
  const [mode, setMode] = useState("both"),
    [integrity, setIntegrity] = useState("full"),
    [threads, setThreads] = useState(1),
    [reuse, setReuse] = useState(true),
    [checkYield, setCheckYield] = useState(true),
    [demultiplex, setDemultiplex] = useState(false),
    [output, setOutput] = useState("");
  const [plan, setPlan] = useState<BatchPlan | null>(null),
    [attempt, setAttempt] = useState<BatchAttempt | null>(null),
    [history, setHistory] = useState<CatalogPage<BatchAttempt> | null>(null),
    [offset, setOffset] = useState(0),
    [refresh, setRefresh] = useState(0);
  useEffect(() => {
    setPlan(null);
    setAttempt(null);
  }, [
    sampleIds,
    runIds,
    mode,
    integrity,
    threads,
    reuse,
    checkYield,
    demultiplex,
    output,
  ]);
  // Retain the request key across a network retry; a second click cannot queue duplicate work.
  const [request, setRequest] = useState<{ scope: string; key: string } | null>(
    null,
  );
  useEffect(() => {
    let stop = false;
    void api<Config>("api/config")
      .then((value) => {
        if (!stop) setConfig(value);
      })
      .catch((err) => {
        if (!stop) setError(err.message);
      });
    return () => {
      stop = true;
    };
  }, []);
  useEffect(() => {
    let stop = false;
    void api<CatalogPage<BatchAttempt>>(
      `${base}/batches?limit=25&offset=${offset}`,
    )
      .then((value) => {
        if (!stop) setHistory(value);
      })
      .catch((err) => {
        if (!stop) setError(err.message);
      });
    return () => {
      stop = true;
    };
  }, [base, offset, refresh]);
  const identifier = attempt?.id,
    active = attempt && batchActive(attempt.state);
  useEffect(() => {
    if (!identifier || !active) return;
    let stopped = false,
      timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await api<BatchAttempt>(`${base}/batches/${identifier}`);
        if (!stopped) {
          setAttempt(value);
          if (batchActive(value.state))
            timer = setTimeout(() => void poll(), 1000);
          else setRefresh((n) => n + 1);
        }
      } catch (err) {
        if (!stopped) {
          setError(err instanceof Error ? err.message : "Cannot refresh batch");
          timer = setTimeout(() => void poll(), 3000);
        }
      }
    };
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [base, identifier, active]);
  const preview = async () => {
    if (sampleIds?.length === 0 || runIds?.length === 0) {
      setError(
        "Select at least one sample/run, or choose All project samples/runs.",
      );
      return;
    }
    setBusy(true);
    setError("");
    setAttempt(null);
    setPlan(null);
    try {
      setPlan(
        await api<BatchPlan>(`${base}/batches/preview`, {
          method: "POST",
          body: JSON.stringify({
            sample_ids: sampleIds,
            sequencing_run_ids: runIds,
            options: {
              mode,
              threads,
              integrity,
              reuse,
              yield: checkYield,
              demultiplex,
              output_root: output || null,
            },
          }),
        }),
      );
      setRequest(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot plan batch");
    } finally {
      setBusy(false);
    }
  };
  const submit = async (retry?: BatchAttempt) => {
    if (!plan) return;
    setBusy(true);
    setError("");
    const scope = plan.id + ":" + (retry?.id ?? "initial");
    const key = request?.scope === scope ? request.key : crypto.randomUUID();
    setRequest({ scope, key });
    try {
      setAttempt(
        await api<BatchAttempt>(`${base}/batches`, {
          method: "POST",
          body: JSON.stringify({
            plan_id: plan.id,
            idempotency_key: key,
            ...(retry ? { retry_of: retry.id } : {}),
          }),
        }),
      );
      setRefresh((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot queue batch");
    } finally {
      setBusy(false);
    }
  };
  const reopen = async (id: string) => {
    setBusy(true);
    setError("");
    try {
      const value = await api<BatchAttempt>(`${base}/batches/${id}`);
      setPlan(await api<BatchPlan>(`${base}/batch-plans/${value.plan_id}`));
      setAttempt(value);
      setRequest(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot open batch");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-label="Project batch QC">
      <h2>Batch QC & validation</h2>
      <p className="inline-note">
        Plan from confirmed file identities. Each FASTQ is analyzed
        independently; lanes are never concatenated. Batch completion describes
        execution, not release approval. Project-level expected yields are not
        automatically applied across runs.
      </p>
      <form
        aria-label="Plan project batch"
        onSubmit={(e) => {
          e.preventDefault();
          void preview();
        }}
      >
        <fieldset disabled={busy || !!active} className="project-fields">
          <legend>Cohort and existing QC operations</legend>
          <ProjectCohort
            projectId={projectId}
            kind="samples"
            selected={sampleIds}
            change={setSampleIds}
          />
          <ProjectCohort
            projectId={projectId}
            kind="sequencing-runs"
            selected={runIds}
            change={setRunIds}
          />
          <label className="field-label">
            QC mode
            <select
              aria-label="Batch QC mode"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="both">FastQC + MultiQC</option>
              <option value="fastqc">FastQC only</option>
            </select>
          </label>
          <label className="field-label">
            Integrity coverage
            <select
              aria-label="Batch integrity coverage"
              value={integrity}
              onChange={(e) => setIntegrity(e.target.value)}
            >
              <option value="full">Full read-only validation</option>
              <option value="quick">
                Quick scan (full coverage may be unavailable)
              </option>
              <option value="off">Skip integrity</option>
            </select>
          </label>
          <label className="field-label">
            Threads
            <input
              aria-label="Batch threads"
              type="number"
              min={1}
              max={config?.max_threads ?? 1}
              value={threads}
              onChange={(e) => setThreads(Number(e.target.value))}
            />
          </label>
          <label className="field-label">
            Output root
            <select
              aria-label="Batch output root"
              value={output}
              onChange={(e) => setOutput(e.target.value)}
            >
              <option value="">
                Default: {config?.default_output ?? "configured result store"}
              </option>
              {config?.output_locations?.map((location) => (
                <option
                  key={location.path}
                  value={location.path}
                  disabled={!location.available}
                >
                  {location.path}
                </option>
              ))}
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={reuse}
              onChange={(e) => setReuse(e.target.checked)}
            />{" "}
            Reuse only matching completed evidence
          </label>
          <label>
            <input
              type="checkbox"
              checked={checkYield}
              onChange={(e) => setCheckYield(e.target.checked)}
            />{" "}
            Inspect existing scoped yield data/targets
          </label>
          <label>
            <input
              type="checkbox"
              checked={demultiplex}
              onChange={(e) => setDemultiplex(e.target.checked)}
            />{" "}
            Check available demultiplexing evidence
          </label>
          <button className="button primary" type="submit">
            {busy ? "Planning…" : "Preview batch plan"}
          </button>
        </fieldset>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {plan && (
        <section className="form-section" aria-label="Batch plan preview">
          <h3>
            Plan · {plan.file_count} FASTQs · {plan.units.length} run/chunk
            units
          </h3>
          <p className="inline-note project-hash">
            {plan.id} · fingerprint {plan.fingerprint}
          </p>
          <p>
            {Object.entries(plan.tools)
              .map(([name, version]) => `${name} ${version}`)
              .join(" · ")}{" "}
            · {plan.options.threads} thread(s) · {plan.options.integrity}{" "}
            integrity
          </p>
          <p>
            Source size: {plan.source_bytes.toLocaleString()} compressed/source
            bytes. Output: {plan.options.output_root}
          </p>
          <p className="inline-note">{plan.io_note}</p>
          <p>Expected outputs: {plan.expected_outputs.join("; ")}.</p>
          {plan.units.map((unit) => (
            <details key={unit.id}>
              <summary>
                {unit.display_name} · {unit.files.length} files ·{" "}
                {unit.reuse ? "Reuse completed QC" : "Run new QC"}
              </summary>
              <p>{unit.reuse_reason}</p>
              {unit.warnings.map((w) => (
                <p className="inline-note" key={w}>
                  {w}
                </p>
              ))}
              <div className="table-scroll" tabIndex={0}>
                <table aria-label={`Planned FASTQs ${unit.id}`}>
                  <thead>
                    <tr>
                      <th>Filename / stable ID</th>
                      <th>Sample</th>
                      <th>Run / lane / chunk / read</th>
                      <th>Source bytes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {unit.files.map((file) => (
                      <tr key={file.file_id}>
                        <td>
                          {file.filename}
                          <small>{file.file_id}</small>
                        </td>
                        <td>{file.sample_id}</td>
                        <td>
                          {file.sequencing_run_id}
                          <small>
                            {[
                              file.declared.lane,
                              file.declared.chunk,
                              file.declared.read,
                            ]
                              .filter(Boolean)
                              .join(" · ") || "Unpaired/unknown"}
                          </small>
                        </td>
                        <td>{file.source_snapshot.size}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ))}
          {!!plan.skipped.length && (
            <details>
              <summary>
                {plan.skipped.length} skipped/ambiguous associations
              </summary>
              <ul>
                {plan.skipped.map((row, index) => (
                  <li key={index}>
                    {row.file_id} · {row.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {!attempt && (
            <button
              className="button primary"
              disabled={busy || !plan.file_count}
              onClick={() => void submit()}
            >
              Confirm and queue batch
            </button>
          )}
        </section>
      )}
      {attempt && (
        <section
          className="form-section"
          aria-label="Batch execution status"
          aria-live="polite"
        >
          <h3>Batch {attempt.state}</h3>
          <p className="project-hash">{attempt.id}</p>
          <p>
            Release: {attempt.release_state.replaceAll("_", " ")}. No approval
            is created by this operation.
          </p>
          {attempt.error && <p className="error">{attempt.error}</p>}
          {attempt.units.map((unit) => (
            <section key={unit.id} aria-label={`Batch unit ${unit.id}`}>
              <h4>
                {unit.display_name} · {unit.file_ids.length} files
              </h4>
              <div className="table-scroll" tabIndex={0}>
                <table aria-label={`Batch stages ${unit.id}`}>
                  <thead>
                    <tr>
                      <th>Stage</th>
                      <th>Actual status</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(unit.stages).map(([name, stage]) => (
                      <tr key={name}>
                        <th>{name}</th>
                        <td>{stageLabel(stage)}</td>
                        <td>
                          {stage.reason || "—"}
                          {stage.values && (
                            <details>
                              <summary>
                                Reported yield values and scoped targets
                              </summary>
                              {stage.values.map((value) => (
                                <p key={value.sample_id}>
                                  {value.sample_name} ·{" "}
                                  {value.totals.reads ?? "unavailable"} reads ·{" "}
                                  {value.totals.bases ?? "unavailable"} bases ·{" "}
                                  {value.explanation}
                                </p>
                              ))}
                            </details>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {unit.integrity_progress?.current_file && (
                <p>
                  Scanning{" "}
                  {unit.integrity_progress.current_file.name || "source file"} ·{" "}
                  {unit.integrity_progress.current_file.records_scanned ?? 0}{" "}
                  records read so far; full coverage is not yet established.
                </p>
              )}
              {!!unit.input_outcomes?.length && (
                <details>
                  <summary>Per-file QC outcomes</summary>
                  <ul>
                    {unit.input_outcomes.map((file) => (
                      <li key={file.id}>
                        {file.name} · {file.state}
                        {file.error ? ` · ${file.error}` : ""}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {unit.analysis_id && (
                <div className="project-actions">
                  <button
                    className="button small"
                    onClick={() => openAnalysis(unit.analysis_id!, "overview")}
                  >
                    Open batch analysis & logs
                  </button>
                  <button
                    className="button small"
                    onClick={() => openAnalysis(unit.analysis_id!, "metrics")}
                  >
                    QC metrics
                  </button>
                  <button
                    className="button small"
                    onClick={() => openAnalysis(unit.analysis_id!, "reports")}
                  >
                    Reports
                  </button>
                </div>
              )}
            </section>
          ))}
          {batchActive(attempt.state) ? (
            <button
              className="button"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                void api<BatchAttempt>(`${base}/batches/${attempt.id}/cancel`, {
                  method: "POST",
                })
                  .then(setAttempt)
                  .catch((err) => setError(err.message))
                  .finally(() => {
                    setBusy(false);
                    setRefresh((n) => n + 1);
                  });
              }}
            >
              Cancel batch
            </button>
          ) : (
            <button
              className="button"
              disabled={busy}
              onClick={() => void submit(attempt)}
            >
              Retry with current validation (new attempt)
            </button>
          )}
        </section>
      )}
      <section aria-label="Project batch history">
        <h3>Batch history</h3>
        <button
          className="button small"
          disabled={busy}
          onClick={() => setRefresh((n) => n + 1)}
        >
          Refresh batch history
        </button>
        <div className="table-scroll" tabIndex={0}>
          <table aria-label="Project batch history">
            <thead>
              <tr>
                <th>Attempt</th>
                <th>State</th>
                <th>Created</th>
                <th>Finished</th>
                <th>Inspect</th>
              </tr>
            </thead>
            <tbody>
              {history?.items.map((row) => (
                <tr key={row.id}>
                  <td>{row.id}</td>
                  <td>{row.state}</td>
                  <td>{date(row.created_at)}</td>
                  <td>{row.finished_at ? date(row.finished_at) : "—"}</td>
                  <td>
                    <button
                      className="button small"
                      disabled={busy}
                      onClick={() => void reopen(row.id)}
                    >
                      Open batch attempt
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!history?.total && (
          <p className="inline-note">No batches have been submitted.</p>
        )}
        <div className="project-actions">
          <button
            className="button small"
            disabled={offset === 0 || busy}
            onClick={() => setOffset(Math.max(0, offset - 25))}
          >
            Previous batches
          </button>
          <span>{history?.total ?? 0} attempts</span>
          <button
            className="button small"
            disabled={!history || offset + 25 >= history.total || busy}
            onClick={() => setOffset(offset + 25)}
          >
            Next batches
          </button>
        </div>
      </section>
    </section>
  );
}
