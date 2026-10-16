import { useEffect, useRef, useState } from "react";
import type { Run } from "./types";
import type { DeliveryData } from "./delivery";
import type { ReleaseEvaluation } from "./release";
import type { ExportMode } from "./rawExport";
import { policyDefinition } from "./release";
import { api, url, date, bytes } from "./api";
import { supportedModules } from "./qc";
import ExportModeSelect from "./ExportModeSelect";

export default function ReleaseReview({
  run,
  data,
  refresh,
}: {
  run: Run;
  data: DeliveryData;
  refresh: () => void;
}) {
  const [open, setOpen] = useState(false),
    [selection, setSelection] = useState<Set<string> | null>(null);
  const ids = data.yields
    .map((row) => row.sample_id)
    .filter((id) => selection === null || selection.has(id));
  const scopeKey = ids.join(",");
  const [result, setResult] = useState<ReleaseEvaluation | null>(null),
    [bump, setBump] = useState(0);
  const [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [version, setVersion] = useState("1"),
    [assay, setAssay] = useState("");
  const [checks, setChecks] = useState([
      "integrity",
      "expected_delivery",
      "quantity",
    ]),
    [modules, setModules] = useState<Record<string, string>>({});
  const dirty = useRef(false);
  const [action, setAction] = useState("needs_review"),
    [reason, setReason] = useState(""),
    [rule, setRule] = useState(""),
    [reviewer, setReviewer] = useState("");
  const [includeReports, setIncludeReports] = useState(false),
    [includePaths, setIncludePaths] = useState(false),
    [mode, setMode] = useState<ExportMode>("spreadsheet");
  useEffect(() => {
    if (!open || !ids.length) {
      setResult(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      api<ReleaseEvaluation>(`api/runs/${run.id}/release-review/evaluate`, {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({ sample_ids: scopeKey.split(",") }),
      })
        .then((value) => {
          if (cancelled) return;
          setResult(value);
          setError("");
          if (!dirty.current) {
            const policy = value.policy?.definition;
            setVersion(policy?.version || "1");
            setAssay(
              policy?.assay || (data.assay === "Unspecified" ? "" : data.assay),
            );
            setChecks(
              policy?.required_checks || [
                "integrity",
                "expected_delivery",
                "quantity",
              ],
            );
            setModules(
              Object.fromEntries(
                policy?.fastqc_rules.map((rule) => [
                  rule.module,
                  rule.allowed_statuses.join(","),
                ]) || [],
              ),
            );
          }
        })
        .catch((error) => {
          if (!cancelled) setError((error as Error).message);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [open, scopeKey, run.id, run.updated_at, bump]);
  const perform = async (task: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      setNotice(message);
      setBump((value) => value + 1);
      refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const savePolicy = () =>
    perform(async () => {
      await api(`api/runs/${run.id}/release-policy`, {
        method: "POST",
        body: JSON.stringify(policyDefinition(version, assay, checks, modules)),
      });
      dirty.current = false;
    }, "Versioned release policy saved; prior reviews must be reevaluated.");
  const review = () =>
    perform(async () => {
      if (!result) throw new Error("Refresh the current evidence first.");
      await api(`api/runs/${run.id}/release-review`, {
        method: "POST",
        body: JSON.stringify({
          sample_ids: ids,
          fingerprint: result.fingerprint,
          action,
          reason,
          rule_id: action === "waive" ? rule : null,
          reviewer_label: reviewer,
        }),
      });
      setReason("");
    }, "Review action recorded with its evidence fingerprint.");
  const startExport = () =>
    perform(async () => {
      if (!result) throw new Error("Refresh the current evidence first.");
      await api(`api/runs/${run.id}/release-exports`, {
        method: "POST",
        body: JSON.stringify({
          sample_ids: ids,
          fingerprint: result.fingerprint,
          include_reports: includeReports,
          acknowledge_report_paths: includeReports,
          include_paths: includePaths,
          mode,
        }),
      });
    }, "Reference bundle queued; original FASTQs remain unchanged.");
  const active =
    !!run.release_export &&
    ["queued", "running"].includes(run.release_export.state);
  const waivable =
    result?.checks.filter(
      (check) =>
        check.mandatory && check.id !== "integrity" && check.state !== "pass",
    ) || [];
  const record = run.release_export;
  return (
    <details
      className="release-review"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Release review &amp; reference bundle</summary>
      {open && (
        <section aria-label="Release review and export">
          <p className="inline-note">
            Configure an explicit assay/project contract, inspect original QC
            evidence and record a reasoned review. FastQC module classifications
            remain unchanged. No universal yield or Q30 threshold is applied.
            Full source integrity is mandatory and cannot be waived.
          </p>
          <button
            className="button small"
            disabled={loading}
            onClick={() => setBump((value) => value + 1)}
          >
            Refresh release evidence
          </button>
          {!data.yields.length ? (
            <p>
              Source FASTQs are unavailable for release review. Imported report
              names alone cannot establish a delivery.
            </p>
          ) : (
            <>
              <details>
                <summary>
                  Selected whole sample groups ({ids.length} of{" "}
                  {data.yields.length})
                </summary>
                <div className="analytics-actions">
                  <button
                    className="button small"
                    onClick={() => setSelection(null)}
                  >
                    Select all release groups
                  </button>
                  <button
                    className="button small"
                    onClick={() => setSelection(new Set())}
                  >
                    Clear release selection
                  </button>
                </div>
                <div className="analytics-selection-list">
                  {data.yields.map((sample) => (
                    <label key={sample.sample_id}>
                      <input
                        type="checkbox"
                        checked={ids.includes(sample.sample_id)}
                        onChange={(event) =>
                          setSelection((value) => {
                            const next = new Set(
                              value || data.yields.map((row) => row.sample_id),
                            );
                            event.target.checked
                              ? next.add(sample.sample_id)
                              : next.delete(sample.sample_id);
                            return next;
                          })
                        }
                      />
                      {sample.sample_name} · {sample.file_ids.length} FASTQs{" "}
                      <small className="mono">{sample.sample_id}</small>
                    </label>
                  ))}
                </div>
              </details>
              {!ids.length && (
                <p>
                  Select at least one complete sample group. A lane/read is not
                  silently dropped from its saved group.
                </p>
              )}
              {loading && (
                <p role="status">
                  Evaluating saved evidence and current source metadata…
                </p>
              )}
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
              {notice && <p role="status">{notice}</p>}
              <details>
                <summary>Versioned assay / project policy</summary>
                <div className="analytics-actions">
                  <label>
                    Policy version{" "}
                    <input
                      aria-label="Release policy version"
                      value={version}
                      maxLength={120}
                      onChange={(event) => {
                        dirty.current = true;
                        setVersion(event.target.value);
                      }}
                    />
                  </label>
                  <label>
                    Assay / project contract{" "}
                    <input
                      aria-label="Release policy assay"
                      value={assay}
                      maxLength={120}
                      placeholder="e.g. RNA-seq project contract"
                      onChange={(event) => {
                        dirty.current = true;
                        setAssay(event.target.value);
                      }}
                    />
                  </label>
                </div>
                <fieldset>
                  <legend>Required release checks</legend>
                  {[
                    [
                      "integrity",
                      "Full current source and mate integrity (cannot waive)",
                    ],
                    ["expected_delivery", "Independent expected delivery"],
                    ["quantity", "Explicit per-sample quantity minima"],
                    [
                      "demultiplex",
                      "Supported Illumina sample/index reconciliation",
                    ],
                  ].map(([id, label]) => (
                    <label key={id}>
                      <input
                        type="checkbox"
                        checked={checks.includes(id)}
                        disabled={id === "integrity"}
                        onChange={(event) => {
                          dirty.current = true;
                          setChecks((value) =>
                            event.target.checked
                              ? [...value, id]
                              : value.filter((key) => key !== id),
                          );
                        }}
                      />
                      {label}
                    </label>
                  ))}
                </fieldset>
                <details>
                  <summary>Optional explicit FastQC status rules</summary>
                  <p className="inline-note">
                    Default classifications are informational. Only add a
                    required status rule when justified by the assay contract;
                    unusual RNA-seq, amplicon, targeted or methylation-related
                    profiles do not imply automatic sequencing failure.
                  </p>
                  <div className="table-scroll" tabIndex={0}>
                    <table>
                      <thead>
                        <tr>
                          <th>Original FastQC module</th>
                          <th>Permitted original statuses in this contract</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          ...new Set([
                            ...supportedModules,
                            ...Object.keys(modules),
                          ]),
                        ].map((name) => (
                          <tr key={name}>
                            <td>{name}</td>
                            <td>
                              <select
                                aria-label={`Release policy for ${name}`}
                                value={modules[name] || ""}
                                onChange={(event) => {
                                  dirty.current = true;
                                  setModules((value) => ({
                                    ...value,
                                    [name]: event.target.value,
                                  }));
                                }}
                              >
                                <option value="">
                                  Informational (no required rule)
                                </option>
                                <option value="pass">PASS</option>
                                <option value="pass,warn">PASS / WARN</option>
                                <option value="pass,warn,fail">
                                  PASS / WARN / FAIL (explicitly permitted)
                                </option>
                              </select>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
                <button
                  className="button small"
                  disabled={busy || active || !assay.trim() || !ids.length}
                  onClick={() => void savePolicy()}
                >
                  Save release policy
                </button>
              </details>
              {result && (
                <>
                  <p className="release-verdict" role="status">
                    <strong>
                      Readiness: {result.readiness.replaceAll("_", " ")} ·
                      review: {result.review_state.replaceAll("_", " ")}
                    </strong>
                    <small>
                      Policy{" "}
                      {result.policy?.definition.version || "not configured"} ·
                      evidence{" "}
                      <span className="mono">
                        {result.fingerprint.slice(0, 16)}
                      </span>
                    </small>
                  </p>
                  <div className="table-scroll" tabIndex={0}>
                    <table>
                      <thead>
                        <tr>
                          <th>Check</th>
                          <th>Policy evaluation</th>
                          <th>Definition / original evidence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.checks.map((check) => (
                          <tr key={check.id}>
                            <td>
                              {check.name}
                              <small>
                                {check.mandatory ? "Required" : "Informational"}
                              </small>
                            </td>
                            <td>
                              {check.state.replaceAll("_", " ")}
                              {check.waiver && (
                                <small>Waived: {check.waiver.reason}</small>
                              )}
                            </td>
                            <td>
                              {check.explanation}
                              {!!(check.evidence || check.source_statuses) && (
                                <details>
                                  <summary>Original evidence</summary>
                                  <pre
                                    className="release-evidence"
                                    tabIndex={0}
                                  >
                                    {JSON.stringify(
                                      check.evidence || check.source_statuses,
                                      null,
                                      2,
                                    )}
                                  </pre>
                                </details>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <details>
                    <summary>Record reviewer decision / exception</summary>
                    <div className="analytics-actions">
                      <label>
                        Action{" "}
                        <select
                          aria-label="Release review action"
                          value={action}
                          onChange={(event) => setAction(event.target.value)}
                        >
                          <option value="needs_review">Needs review</option>
                          <option value="approve">
                            Approve current selected evidence
                          </option>
                          <option value="block">Block</option>
                          <option value="waive">
                            Waive one required rule (reason required)
                          </option>
                        </select>
                      </label>
                      {action === "waive" && (
                        <label>
                          Rule{" "}
                          <select
                            aria-label="Release waiver rule"
                            value={rule}
                            onChange={(event) => setRule(event.target.value)}
                          >
                            <option value="">Choose a nonpassing rule</option>
                            {waivable.map((check) => (
                              <option key={check.id} value={check.id}>
                                {check.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}
                      <label>
                        Self-declared reviewer label (optional){" "}
                        <input
                          maxLength={120}
                          value={reviewer}
                          onChange={(event) => setReviewer(event.target.value)}
                        />
                      </label>
                    </div>
                    <label className="delivery-notes">
                      Reason{" "}
                      <textarea
                        aria-label="Release review reason"
                        maxLength={2000}
                        value={reason}
                        onChange={(event) => setReason(event.target.value)}
                      />
                    </label>
                    <p className="inline-note">
                      The audit actor is the current Unix user; this label does
                      not provide a separate authenticated personal identity.
                      Changes to inputs, metrics, policy or targets make
                      previous decisions stale.
                    </p>
                    <button
                      className="button small"
                      disabled={
                        busy ||
                        loading ||
                        active ||
                        !reason.trim() ||
                        (action === "approve" &&
                          result.readiness !== "ready") ||
                        (action === "waive" && !rule)
                      }
                      onClick={() => void review()}
                    >
                      Record release review
                    </button>
                  </details>
                  <details>
                    <summary>Export selected reference bundle</summary>
                    <p className="inline-note">
                      FASTQs are referenced, never copied. Checksums cover the
                      fully validated source bytes and bundled metadata.
                      Receiving systems must verify again after transfer. Only a
                      current explicit approval produces an approved bundle;
                      other complete-hash exports are labeled review required.
                    </p>
                    <div className="analytics-actions">
                      <ExportModeSelect value={mode} change={setMode} />
                      <label>
                        <input
                          type="checkbox"
                          checked={includeReports}
                          onChange={(event) =>
                            setIncludeReports(event.target.checked)
                          }
                        />
                        Include original reports; I understand they may contain
                        private paths and excluded samples
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={includePaths}
                          onChange={(event) =>
                            setIncludePaths(event.target.checked)
                          }
                        />
                        Include private absolute input paths in this bundle
                      </label>
                    </div>
                    <button
                      className="button small"
                      disabled={
                        busy ||
                        loading ||
                        active ||
                        result.checks.find((check) => check.id === "integrity")
                          ?.state !== "pass"
                      }
                      onClick={() => void startExport()}
                    >
                      Export reference bundle (
                      {result.review_state === "approved" &&
                      result.readiness === "ready"
                        ? "approved"
                        : "review required"}
                      )
                    </button>
                  </details>
                  <details>
                    <summary>Review history ({result.history.length})</summary>
                    {result.history.map((event) => (
                      <p key={event.id}>
                        {date(event.created_at)} · {event.actor.unix_user} (uid{" "}
                        {event.actor.uid})
                        {event.reviewer_label &&
                          ` · self-declared ${event.reviewer_label}`}{" "}
                        · {event.action} {event.rule_id} · {event.reason}
                        <small className="mono">
                          {event.fingerprint === result.fingerprint
                            ? "Current evidence"
                            : "Historical / stale evidence"}{" "}
                          · {event.fingerprint.slice(0, 16)} ·{" "}
                          {event.sample_ids.length} groups
                        </small>
                      </p>
                    ))}
                  </details>
                </>
              )}
              {record && (
                <div className="release-export-status">
                  <p role="status">
                    Reference export: {record.state} ·{" "}
                    {record.release_status.replaceAll("_", " ")}{" "}
                    {record.bytes !== undefined && `· ${bytes(record.bytes)}`}
                  </p>
                  {record.error && <p role="alert">{record.error}</p>}
                  {active && (
                    <button
                      className="button small danger"
                      disabled={busy}
                      onClick={() =>
                        void perform(
                          () =>
                            api(`api/runs/${run.id}/release-exports/cancel`, {
                              method: "POST",
                              body: "{}",
                            }),
                          "Incomplete export cancelled.",
                        )
                      }
                    >
                      Cancel reference export
                    </button>
                  )}
                  {record.state === "completed" &&
                    (run.reports.some(
                      (report) => report.path === record.artifact,
                    ) ? (
                      <>
                        <a
                          className="button small"
                          download
                          href={url(
                            `api/runs/${run.id}/download?${new URLSearchParams({ path: record.artifact! })}`,
                          )}
                        >
                          Download {record.release_status.replaceAll("_", " ")}{" "}
                          reference bundle
                        </a>
                        <p className="mono">ZIP SHA-256: {record.sha256}</p>
                      </>
                    ) : (
                      <p>
                        Completed bundle artifact is missing or no longer
                        registered.
                      </p>
                    ))}
                </div>
              )}
            </>
          )}
        </section>
      )}
    </details>
  );
}
