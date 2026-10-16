import { useEffect, useRef, useState } from "react";
import { api, bytes, date, url } from "./api";
import type { Run } from "./types";
import type { ExportMode } from "./rawExport";
import type { DeliveryData, QuantityMetric, TargetDraft } from "./delivery";
import { configuredTargets, quantity } from "./delivery";
import ExportModeSelect from "./ExportModeSelect";
import DemultiplexReview from "./DemultiplexReview";

export default function DeliveryReview({
  run,
  refresh,
  inspect,
}: {
  run: Run;
  refresh: () => void;
  inspect: (reportId: string) => void;
}) {
  const [open, setOpen] = useState(false),
    [data, setData] = useState<DeliveryData | null>(null);
  const [reload, setReload] = useState(0),
    [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState("");
  const [format, setFormat] = useState<ExportMode>("spreadsheet"),
    [privatePaths, setPrivatePaths] = useState(false);
  const [upload, setUpload] = useState<File | null>(null);
  const [drafts, setDrafts] = useState<Record<string, TargetDraft>>({});
  const [assay, setAssay] = useState(""),
    [stage, setStage] = useState("unknown"),
    [notes, setNotes] = useState("");
  const dirty = useRef(false);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    api<DeliveryData>(`api/runs/${run.id}/delivery`)
      .then((value) => {
        if (cancelled) return;
        setData(value);
        setError("");
        if (!dirty.current) {
          setDrafts(
            Object.fromEntries(
              value.yields.map((sample) => [
                sample.sample_id,
                {
                  metric: sample.target?.metric || "reads",
                  minimum: sample.target ? String(sample.target.minimum) : "",
                },
              ]),
            ),
          );
          setAssay(value.assay);
          setStage(value.input_stage);
          setNotes(value.processing_notes);
        }
      })
      .catch((error) => {
        if (!cancelled) setError((error as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, run.id, run.updated_at, reload]);
  const perform = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setError("");
    setSaved("");
    try {
      await action();
      setSaved(message);
      setReload((value) => value + 1);
      refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const saveTargets = () =>
    perform(async () => {
      const targets = configuredTargets(drafts);
      await api(`api/runs/${run.id}/yield-targets`, {
        method: "POST",
        body: JSON.stringify({
          assay,
          input_stage: stage,
          processing_notes: notes,
          targets,
        }),
      });
      dirty.current = false;
    }, "Quantity targets saved.");
  const importExpected = () =>
    perform(async () => {
      if (
        !upload ||
        upload.size > 1024 * 1024 ||
        !/\.(csv|json)$/i.test(upload.name)
      )
        throw new Error(
          "Choose a CSV or JSON expected manifest of at most 1 MiB.",
        );
      await api(`api/runs/${run.id}/expected-delivery`, {
        method: "POST",
        body: JSON.stringify({
          format: upload.name.toLowerCase().endsWith(".json") ? "json" : "csv",
          content: await upload.text(),
        }),
      });
    }, "Expected delivery manifest saved.");
  const exportUrl = (extension: string) =>
    url(
      `api/runs/${run.id}/delivery-manifest?${new URLSearchParams({ format: extension, mode: format, include_paths: String(privatePaths) })}`,
    );
  const reason = data?.reconciliation;
  return (
    <details
      className="sample-table-section delivery-review"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Delivery manifest &amp; yield</summary>
      {open && (
        <div role="region" aria-label="Delivery manifest and yield">
          <p className="inline-note">
            File-level inventory and explicit quantity targets for this
            analysis. R1 and R2 are separate reads; lanes are never merged.
            Missing evidence is not evaluated. A FastQC warning alone does not
            reject a delivery.
          </p>
          {loading && <p role="status">Refreshing source metadata…</p>}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {saved && <p role="status">{saved}</p>}
          {data && (
            <>
              {data.source_kind === "reports_only" && (
                <p>
                  Imported reports have no proven source FASTQs. Delivery
                  quantities and integrity cannot be established from report
                  names.
                </p>
              )}
              <div className="analytics-actions">
                <ExportModeSelect value={format} change={setFormat} />
                <label>
                  <input
                    type="checkbox"
                    checked={privatePaths}
                    onChange={(event) => setPrivatePaths(event.target.checked)}
                  />{" "}
                  Include private absolute input paths
                </label>
                <a className="button small" download href={exportUrl("json")}>
                  Manifest JSON
                </a>
                <a className="button small" download href={exportUrl("csv")}>
                  Manifest CSV
                </a>
              </div>
              <p className="inline-note">
                Default exports use logical relative references; source FASTQs
                are not copied. Review free-text names and notes before sharing.
                Checksums are source computations, not verification after
                transfer.
              </p>
              <details>
                <summary>File inventory ({data.files.length})</summary>
                <div className="table-scroll" tabIndex={0}>
                  <table>
                    <thead>
                      <tr>
                        <th>Sample / lane / read</th>
                        <th>Original input</th>
                        <th>Size / length</th>
                        <th>Read records / bases</th>
                        <th>Evidence / SHA-256</th>
                        <th>QC</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.files.map((file) => (
                        <tr key={file.file_id}>
                          <td>
                            {file.sample_name}
                            <small className="mono">{file.sample_id}</small>
                            <small>
                              {[file.lane, file.chunk, file.read]
                                .filter(Boolean)
                                .join(" · ")}{" "}
                              · {file.pair_source || "unassigned"}
                            </small>
                          </td>
                          <td className="mono">
                            {file.path}
                            <small>{file.file_id}</small>
                            <small>
                              {file.input_available
                                ? "Source available"
                                : file.availability_error ||
                                  "Source unavailable"}
                            </small>
                          </td>
                          <td>
                            {bytes(file.size_bytes)}
                            <small>{file.size_source}</small>
                            <small>
                              {file.sequence_length || "Length unavailable"}{" "}
                              {file.sequence_length && "bp"}
                            </small>
                          </td>
                          <td>
                            {quantity(file.reads)} reads
                            <small>{quantity(file.bases)} bases</small>
                            <small>{file.counts_source}</small>
                          </td>
                          <td>
                            {file.integrity_state.replaceAll("_", " ")}
                            <small className="mono">
                              {file.sha256 || "Checksum not evaluated"}
                            </small>
                          </td>
                          <td>
                            {file.report_id && (
                              <button
                                className="button small"
                                onClick={() => inspect(file.report_id!)}
                              >
                                Inspect QC
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {data.notices.map((notice, index) => (
                  <p className="inline-note" key={index}>
                    {notice.message}
                  </p>
                ))}
              </details>
              <details>
                <summary>
                  Expected delivery reconciliation ·{" "}
                  {reason?.status.replaceAll("_", " ")}
                </summary>
                <p>
                  Supply an independently agreed file manifest. The editable
                  identity template lists currently selected files; it does not
                  establish which files should have been delivered. CSV columns:
                  filename (or file_id / exact path), optional sample_id,
                  sample_name, lane, chunk, read, expected_reads,
                  expected_bases, sha256.
                </p>
                <div className="analytics-actions">
                  <a
                    className="button small"
                    download
                    href={url(`api/runs/${run.id}/expected-template`)}
                  >
                    Editable identity template (JSON)
                  </a>
                  <label>
                    Expected manifest{" "}
                    <input
                      type="file"
                      accept=".csv,.json"
                      aria-label="Expected delivery manifest file"
                      onChange={(event) =>
                        setUpload(event.target.files?.[0] || null)
                      }
                    />
                  </label>
                  <button
                    className="button small"
                    disabled={busy || !upload}
                    onClick={() => void importExpected()}
                  >
                    Import expected manifest
                  </button>
                </div>
                {data.expected_manifest && (
                  <p className="inline-note">
                    {data.expected_manifest.files.length} expected file rows ·{" "}
                    {data.expected_manifest.format} · saved{" "}
                    {date(data.expected_manifest.updated_at)}
                  </p>
                )}
                {reason && (
                  <>
                    <p role="status">
                      {reason.message ||
                        `${reason.matched.length} matched · ${reason.missing.length} missing · ${reason.extra.length} extra · ${reason.ambiguous.length} ambiguous · ${reason.duplicates.length} duplicate rows · ${reason.mismatches.length} mismatches · ${reason.unavailable.length} unavailable checks`}
                    </p>
                    {(
                      [
                        "missing",
                        "ambiguous",
                        "duplicates",
                        "mismatches",
                        "unavailable",
                      ] as const
                    ).flatMap((key) =>
                      reason[key].map((entry, index) => (
                        <p key={key + index}>
                          <strong>{key}:</strong> expected row{" "}
                          {entry.expected_row} ·{" "}
                          {Object.values(entry.identity || {}).join(" · ")}{" "}
                          {entry.metric && `· ${entry.metric}`}{" "}
                          {entry.expected !== undefined &&
                            `· expected ${entry.expected}, observed ${entry.observed}`}{" "}
                          {entry.message}
                        </p>
                      )),
                    )}
                    {reason.extra.map((id) => (
                      <p key={id}>
                        Extra file:{" "}
                        {data.files.find((file) => file.file_id === id)
                          ?.filename || id}{" "}
                        <span className="mono">{id}</span>
                      </p>
                    ))}
                  </>
                )}
              </details>
              <DemultiplexReview
                runId={run.id}
                evidence={data.demultiplex}
                refresh={() => {
                  setReload((value) => value + 1);
                  refresh();
                }}
              />
              {!!data.yields.length && (
                <details open>
                  <summary>Sample quantity targets</summary>
                  <p className="inline-note">
                    Read pairs require full synchronized-mate validation for
                    every contributing file. Base totals use a full scan or
                    records × an explicitly fixed FastQC read length. Q20/Q30
                    use actual qualities with a known encoding; per-base mean
                    quality cannot supply these percentages. An empty minimum
                    leaves the target unconfigured.
                  </p>
                  <div className="analytics-actions">
                    <label>
                      Assay / project label{" "}
                      <input
                        aria-label="Assay or project label"
                        maxLength={120}
                        value={assay}
                        onChange={(event) => {
                          dirty.current = true;
                          setAssay(event.target.value);
                        }}
                      />
                    </label>
                    <label>
                      Input stage{" "}
                      <select
                        aria-label="Declared input stage"
                        value={stage}
                        onChange={(event) => {
                          dirty.current = true;
                          setStage(event.target.value);
                        }}
                      >
                        <option value="unknown">Unknown / not declared</option>
                        <option value="raw_fastq">
                          Raw FASTQ as delivered
                        </option>
                        <option value="upstream_processed">
                          Processed upstream (describe below)
                        </option>
                      </select>
                    </label>
                  </div>
                  <label className="delivery-notes">
                    Upstream processing notes (adapter / UMI / filtering, if
                    known)
                    <textarea
                      maxLength={2000}
                      value={notes}
                      onChange={(event) => {
                        dirty.current = true;
                        setNotes(event.target.value);
                      }}
                    />
                  </label>
                  <div className="table-scroll" tabIndex={0}>
                    <table>
                      <thead>
                        <tr>
                          <th>Sample</th>
                          <th>Observed quantity</th>
                          <th>Q20 / Q30</th>
                          <th>Explicit minimum</th>
                          <th>Evaluation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.yields.map((sample) => (
                          <tr key={sample.sample_id}>
                            <td>
                              {sample.sample_name}
                              <small className="mono">{sample.sample_id}</small>
                              <small>
                                {sample.file_ids.length} individual FASTQs
                              </small>
                            </td>
                            <td>
                              {quantity(sample.totals.reads)} reads
                              <small>
                                {quantity(sample.totals.read_pairs)} read pairs
                              </small>
                              <small>
                                {quantity(sample.totals.bases)} bases
                              </small>
                              <small>{sample.provenance.join("; ")}</small>
                            </td>
                            <td>
                              {quantity(sample.totals.q20_percent)}
                              {sample.totals.q20_percent !== null && "%"} /{" "}
                              {quantity(sample.totals.q30_percent)}
                              {sample.totals.q30_percent !== null && "%"}
                              <small>
                                {quantity(sample.totals.q20_bases)} Q20 bases /{" "}
                                {quantity(sample.totals.q30_bases)} Q30 bases
                              </small>
                              <small>
                                Denominator:{" "}
                                {quantity(sample.totals.quality_bases)} quality
                                bases
                              </small>
                            </td>
                            <td>
                              <select
                                aria-label={`Target unit for ${sample.sample_name}`}
                                value={
                                  drafts[sample.sample_id]?.metric || "reads"
                                }
                                onChange={(event) => {
                                  dirty.current = true;
                                  setDrafts((value) => ({
                                    ...value,
                                    [sample.sample_id]: {
                                      ...(value[sample.sample_id] || {
                                        minimum: "",
                                        metric: "reads",
                                      }),
                                      metric: event.target
                                        .value as QuantityMetric,
                                    },
                                  }));
                                }}
                              >
                                <option value="reads">
                                  Read records (R1 + R2)
                                </option>
                                <option value="read_pairs">
                                  Synchronized read pairs
                                </option>
                                <option value="bases">Total bases</option>
                              </select>
                              <input
                                aria-label={`Minimum quantity for ${sample.sample_name}`}
                                inputMode="numeric"
                                placeholder="Not configured"
                                value={drafts[sample.sample_id]?.minimum || ""}
                                onChange={(event) => {
                                  dirty.current = true;
                                  setDrafts((value) => ({
                                    ...value,
                                    [sample.sample_id]: {
                                      ...(value[sample.sample_id] || {
                                        minimum: "",
                                        metric: "reads",
                                      }),
                                      minimum: event.target.value,
                                    },
                                  }));
                                }}
                              />
                            </td>
                            <td>
                              <strong>
                                {sample.target_state.replaceAll("_", " ")}
                              </strong>
                              <small>{sample.explanation}</small>
                              <small>{sample.denominator}</small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="analytics-actions">
                    <button
                      className="button small"
                      disabled={busy}
                      onClick={() => void saveTargets()}
                    >
                      Save quantity targets
                    </button>
                    <button
                      className="button small"
                      disabled={busy}
                      onClick={() => {
                        dirty.current = false;
                        setReload((value) => value + 1);
                      }}
                    >
                      Discard target edits
                    </button>
                  </div>
                </details>
              )}
            </>
          )}
        </div>
      )}
    </details>
  );
}
