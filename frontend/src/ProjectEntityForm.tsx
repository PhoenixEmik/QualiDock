import { useId, useState } from "react";
import type { DeclaredFields, EntityKind, ProjectEntity } from "./project";
import { declaredMinimum } from "./project";

export default function ProjectEntityForm({
  kind,
  entity,
  save,
  cancel,
}: {
  kind: EntityKind;
  entity?: ProjectEntity;
  save: (fields: DeclaredFields) => Promise<void>;
  cancel: () => void;
}) {
  const original = entity?.declared;
  const prefix = useId();
  const [fields, setFields] = useState<DeclaredFields>({
    display_name: "",
    declared_identifier: "",
    notes: "",
    status: "active",
    ...original,
  });
  const [minimum, setMinimum] = useState(
    original?.expected_yield?.minimum?.toString() ?? "",
  );
  const [metric, setMetric] = useState(
    original?.expected_yield?.metric ?? "reads",
  );
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const title =
    kind === "project"
      ? "Project"
      : kind === "sample"
        ? "Sample"
        : "Sequencing run";
  const text = (key: keyof DeclaredFields, label: string, type = "text") => (
    <label className="field-label" htmlFor={prefix + key}>
      {label}
      <input
        id={prefix + key}
        className="wide-input"
        type={type}
        value={String(fields[key] ?? "")}
        maxLength={200}
        required={key === "display_name"}
        onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
      />
    </label>
  );
  return (
    <form
      className="form-section project-form"
      aria-label={`${entity ? "Edit" : "Create"} ${title.toLowerCase()}`}
      onSubmit={(e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        void (async () => {
          try {
            const value = { ...fields };
            if (kind === "sample")
              value.expected_yield = declaredMinimum(metric, minimum);
            await save(value);
          } catch (err) {
            setError(
              err instanceof Error ? err.message : "Unable to save metadata.",
            );
          } finally {
            setBusy(false);
          }
        })();
      }}
    >
      <h3>
        {entity ? "Edit" : "Create"} {title.toLowerCase()}
      </h3>
      <p className="inline-note">
        Declared metadata only. Names do not establish biological identity or QC
        approval.
      </p>
      <fieldset disabled={busy} className="project-fields">
        {text("display_name", `${title} name`)}
        {text("declared_identifier", "Declared identifier")}
        {kind === "sample" && (
          <>
            {text("assay", "Assay / protocol")}
            {text("library_type", "Library type")}
            <label className="field-label">
              Expected yield units
              <select
                aria-label="Expected yield units"
                className="wide-input"
                value={metric}
                onChange={(e) => setMetric(e.target.value as typeof metric)}
              >
                <option value="reads">Read records</option>
                <option value="read_pairs">Read pairs</option>
                <option value="bases">Bases</option>
              </select>
            </label>
            <label className="field-label">
              Expected yield minimum
              <input
                className="wide-input"
                inputMode="numeric"
                value={minimum}
                onChange={(e) => setMinimum(e.target.value)}
              />
            </label>
            <p className="inline-note project-wide">
              Optional expectation; blank means unknown. This does not create a
              release rule or combine yield across runs.
            </p>
          </>
        )}
        {kind === "sequencing_run" && (
          <>
            {text("platform", "Platform (declared)")}
            {text("sequenced_at", "Sequencing date (declared)", "date")}
            <label className="field-label">
              Input stage (declared)
              <select
                aria-label="Input stage (declared)"
                className="wide-input"
                value={fields.input_stage ?? "unknown"}
                onChange={(e) =>
                  setFields({
                    ...fields,
                    input_stage: e.target
                      .value as DeclaredFields["input_stage"],
                  })
                }
              >
                <option value="unknown">Unknown</option>
                <option value="raw_fastq">Raw FASTQ</option>
                <option value="upstream_processed">Upstream processed</option>
              </select>
            </label>
          </>
        )}
        {entity && (
          <label className="field-label">
            Record status
            <select
              aria-label="Record status"
              className="wide-input"
              value={fields.status}
              onChange={(e) =>
                setFields({
                  ...fields,
                  status: e.target.value as "active" | "archived",
                })
              }
            >
              <option value="active">Active</option>
              <option value="archived">Archived (preserve history)</option>
            </select>
          </label>
        )}
        <label className="field-label project-wide">
          Notes
          <textarea
            className="wide-input"
            maxLength={2000}
            value={fields.notes}
            onChange={(e) => setFields({ ...fields, notes: e.target.value })}
          />
        </label>
      </fieldset>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="project-actions">
        <button className="button primary" disabled={busy} type="submit">
          {busy ? "Saving…" : `Save ${title.toLowerCase()}`}
        </button>
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={cancel}
        >
          Cancel metadata edit
        </button>
      </div>
    </form>
  );
}
