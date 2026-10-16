import { useState } from "react";
import { api, url } from "./api";
import { quantity } from "./delivery";
import type { EvidenceTable, DemultiplexEvidence } from "./demultiplex";
import { evidenceDocuments } from "./demultiplex";

function RawEvidence({
  title,
  table,
}: {
  title: string;
  table?: EvidenceTable | null;
}) {
  const [limit, setLimit] = useState(200);
  return (
    <details>
      <summary>
        {title} · {table ? `${table.rows.length} rows` : "Not evaluated"}
      </summary>
      {table ? (
        <>
          <p className="inline-note">
            {table.schema}. Original column labels and text values; blank values
            are not reported.
          </p>
          <div className="table-scroll" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  {table.columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.slice(0, limit).map((row, index) => (
                  <tr key={index}>
                    {table.columns.map((column) => (
                      <td key={column}>
                        {row[column] === "" ? "Not reported" : row[column]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {limit < table.rows.length && (
            <button
              className="button small"
              onClick={() => setLimit((value) => value + 500)}
            >
              Show more evidence rows
            </button>
          )}
        </>
      ) : (
        <p>This source report was not imported.</p>
      )}
    </details>
  );
}
export default function DemultiplexReview({
  runId,
  evidence,
  refresh,
}: {
  runId: string;
  evidence?: DemultiplexEvidence | null;
  refresh: () => void;
}) {
  const [files, setFiles] = useState<File[]>([]),
    [version, setVersion] = useState(""),
    [run, setRun] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      await api(`api/runs/${runId}/demultiplex`, {
        method: "POST",
        body: JSON.stringify({
          documents: await evidenceDocuments(files),
          declared_tool_version: version,
          declared_run_id: run,
        }),
      });
      refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <details>
      <summary>
        Illumina demultiplexing evidence ·{" "}
        {evidence?.state.replaceAll("_", " ") || "Not evaluated"}
      </summary>
      <section aria-label="Illumina demultiplexing evidence">
        <p className="inline-note">
          Read-only SampleSheet / BCL Convert CSV import. This does not run
          demultiplexing or change source FASTQs. Reported PF-read counts are
          kept separate from the sum of R1 and R2 FASTQ records. Missing
          versions and blank index-hopping measurements remain unavailable.
        </p>
        <div className="analytics-actions">
          <label>
            Evidence CSV files{" "}
            <input
              type="file"
              multiple
              accept=".csv"
              aria-label="Illumina evidence CSV files"
              onChange={(event) => setFiles([...(event.target.files || [])])}
            />
          </label>
          <label>
            Declared BCL Convert version (optional){" "}
            <input
              maxLength={120}
              value={version}
              onChange={(event) => setVersion(event.target.value)}
            />
          </label>
          <label>
            Declared run ID (optional){" "}
            <input
              maxLength={200}
              value={run}
              onChange={(event) => setRun(event.target.value)}
            />
          </label>
          <button
            className="button small"
            disabled={busy || !files.length}
            onClick={() => void submit()}
          >
            Import Illumina evidence
          </button>
        </div>
        <p className="inline-note">
          Supported filenames: SampleSheet.csv, Demultiplex_Stats.csv,
          Quality_Metrics.csv, Index_Hopping_Counts.csv and fastq_list.csv.
          Strict verified CSV schemas; maximum 2 MiB/file, 4 MiB total. A
          rejected import retains the previous evidence.
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {evidence ? (
          <>
            <p role="status">
              {evidence.message ||
                `Sample-sheet reconciliation: ${evidence.reconciliation_state?.replaceAll("_", " ") || "not evaluated"}`}
            </p>
            <p>
              Reported tool version:{" "}
              {evidence.reported_tool_version || "Not reported"} · declared
              version: {evidence.declared_tool_version || "None"} · run ID from
              SampleSheet: {evidence.run_id || "Not reported"} · declared run
              ID: {evidence.declared_run_id || "None"}
            </p>
            <p className="inline-note">
              {evidence.version_source} Index sequences are compared without
              reverse-complement inference. These observations cannot establish
              contamination, index misassignment or a sample swap.
            </p>
            {evidence.discrepancies?.slice(0, 100).map((item, index) => (
              <p key={index}>
                <strong>{item.code.replaceAll("_", " ")}:</strong>{" "}
                {item.message}
              </p>
            ))}
            <div className="table-scroll" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th>Lane</th>
                    <th>Sum of imported # Reads</th>
                    <th>Undetermined # Reads</th>
                    <th>Undetermined share of imported rows</th>
                    <th>Denominator</th>
                  </tr>
                </thead>
                <tbody>
                  {evidence.lane_totals?.map((lane) => (
                    <tr key={lane.lane}>
                      <td>{lane.lane}</td>
                      <td>{quantity(lane.reported_pf_reads)}</td>
                      <td>{quantity(lane.undetermined_pf_reads)}</td>
                      <td>
                        {quantity(lane.undetermined_percent_of_imported_rows)}
                        {lane.undetermined_percent_of_imported_rows !== null &&
                          "%"}
                      </td>
                      <td>{lane.denominator}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <RawEvidence title="Sample sheet" table={evidence.sample_sheet} />
            <RawEvidence
              title="Demultiplex statistics"
              table={evidence.demultiplex}
            />
            <RawEvidence
              title="Per-read quality metrics"
              table={evidence.quality}
            />
            <RawEvidence
              title="Reported index-hopping metrics"
              table={evidence.index_hopping}
            />
            <RawEvidence
              title="FASTQ list (explicit source references)"
              table={evidence.fastq_list}
            />
            {!!evidence.file_mappings?.length && (
              <details>
                <summary>
                  Selected FASTQ mapping (exact filename / lane / read)
                </summary>
                {evidence.file_mappings.map((item, index) => (
                  <p key={index}>
                    {item.reported_filename}: {item.state.replaceAll("_", " ")}{" "}
                    · {item.file_id || "No unique selected input"}
                  </p>
                ))}
              </details>
            )}
            <div className="analytics-actions">
              {evidence.documents?.map((document) => (
                <a
                  className="button small"
                  download
                  key={document.name}
                  title={`Original bytes · SHA-256 ${document.sha256}`}
                  href={url(
                    `api/runs/${runId}/download?${new URLSearchParams({ path: document.artifact })}`,
                  )}
                >
                  Original {document.name}
                </a>
              ))}
            </div>
          </>
        ) : (
          <p>
            No imported demultiplexing evidence. This optional check is not
            evaluated.
          </p>
        )}
      </section>
    </details>
  );
}
