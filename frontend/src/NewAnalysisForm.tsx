import {
  Check,
  Dna,
  FileText,
  Files,
  LoaderCircle,
  Play,
  Server,
  ShieldCheck,
  X,
} from "lucide-react";
import { bytes, modeLabel } from "./api";
import { Empty } from "./Feedback";
import SampleEditor from "./SampleEditor";
import OutputDirectory from "./OutputDirectory";
import type { SampleConfiguration } from "./types";
import type { Config, Entry, Run } from "./types";

interface Props {
  config: Config | null;
  sampleConfiguration: SampleConfiguration | null;
  setSampleConfiguration: (value: SampleConfiguration) => void;
  prepareSamples: () => Promise<unknown>;
  outputRoot: string;
  setOutputRoot: (value: string) => void;
  multiqcDirectory: string;
  setMultiqcDirectory: (value: string) => void;
  selected: Map<string, Entry>;
  busy: boolean;
  name: string;
  mode: Run["mode"];
  threads: number;
  pairCount: number;
  setName: (value: string) => void;
  setMode: (value: Run["mode"]) => void;
  setThreads: (value: number) => void;
  toggle: (entry: Entry) => void;
  submit: () => Promise<void>;
}
export default function NewAnalysisForm({
  config,
  sampleConfiguration,
  setSampleConfiguration,
  prepareSamples,
  outputRoot,
  setOutputRoot,
  multiqcDirectory,
  setMultiqcDirectory,
  selected,
  busy,
  name,
  mode,
  threads,
  pairCount,
  setName,
  setMode,
  setThreads,
  toggle,
  submit,
}: Props) {
  const suitable = (entry: Entry) =>
    mode === "multiqc"
      ? ["fastqc", "qcreport"].includes(entry.kind)
      : entry.kind === "fastq";
  const configuredPaths = [...selected.values()].filter(suitable);
  return (
    <div className="setup-layout">
      <div className="setup-main">
        <section className="form-section">
          <div className="form-heading">
            <span>01</span>
            <h2>Analysis details</h2>
          </div>
          <label className="field-label" htmlFor="analysis-name">
            Analysis name
          </label>
          <input
            id="analysis-name"
            className="wide-input"
            placeholder="e.g. RNA-seq · pilot cohort"
            maxLength={120}
            disabled={busy}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <div className="field-label">QC workflow</div>
          <div className="mode-options" role="group" aria-label="QC workflow">
            {(["both", "fastqc", "multiqc"] as const)
              .map((value) => (
                <button
                  key={value}
                  className={`mode-option ${mode === value ? "chosen" : ""}`}
                  aria-pressed={mode === value}
                  disabled={busy}
                  onClick={() => setMode(value)}
                >
                  <span className="radio-dot" />
                  <strong>{modeLabel(value)}</strong>
                  <small>
                    {value === "both"
                      ? "Individual read QC and a combined report"
                      : value === "fastqc"
                        ? "Individual read quality assessment"
                        : "Combine existing FastQC or fastp JSON reports"}
                  </small>
                  {mode === value && <Check size={15} />}
                </button>
              ))}
          </div>
        </section>
        <section className="form-section">
          <div className="form-heading">
            <span>02</span>
            <h2>Input files</h2>
            <small>{configuredPaths.length} selected</small>
          </div>
          {mode === "multiqc" && (
            <div>
              <label className="field-label" htmlFor="multiqc-directory">
                Existing QC results directory (optional)
              </label>
              <input
                id="multiqc-directory"
                className="wide-input"
                value={multiqcDirectory}
                disabled={busy}
                onChange={(event) => setMultiqcDirectory(event.target.value)}
                placeholder="/absolute/path/to/fastqc-results"
              />
              <p className="inline-note">
                Use a directory within a configured storage root, or select
                individual FastQC / fastp JSON reports below. A directory
                overrides the file selection; FASTQ files are never copied or
                rerun.
              </p>
            </div>
          )}
          {selected.size ? (
            <>
              <div className="selected-files">
                {[...selected.values()].map((entry) => (
                  <div
                    key={entry.path}
                    className={suitable(entry) ? "" : "incompatible"}
                  >
                    <FileText size={17} />
                    <div>
                      <strong>{entry.name}</strong>
                      <small title={entry.path}>{entry.path}</small>
                    </div>
                    <span className="subtle">{bytes(entry.size)}</span>
                    <button
                      aria-label={`Remove ${entry.name}`}
                      disabled={busy}
                      onClick={() => toggle(entry)}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
              {configuredPaths.length < selected.size && (
                <p className="inline-note">
                  {selected.size - configuredPaths.length} incompatible files
                  will be excluded from this workflow.
                </p>
              )}
              <div className="pair-summary">
                <Dna size={17} />
                {mode === "multiqc"
                  ? "Supported QC reports will be snapshotted into this run."
                  : `${sampleConfiguration ? sampleConfiguration.input_pairing.filter((record) => record.paired && record.read === "R1").length : pairCount} complete read pairs detected. Both reads are analyzed independently.`}
              </div>
            </>
          ) : (
            <Empty icon={Files} title="Choose your input files">
              {mode === "multiqc"
                ? "Enter a QC results directory, or select FastQC ZIPs, fastqc_data.txt or fastp.json reports in the workspace."
                : "Select FASTQ files in the workspace. No upload is needed."}
            </Empty>
          )}
        </section>
        {mode !== "multiqc" &&
          configuredPaths.length > 0 &&
          (sampleConfiguration ? (
            <SampleEditor
              value={sampleConfiguration}
              change={setSampleConfiguration}
              busy={busy}
            />
          ) : (
            <button
              className="button"
              disabled={busy}
              onClick={() => void prepareSamples()}
            >
              Review sample relationships
            </button>
          ))}
        <OutputDirectory
          config={config}
          value={outputRoot}
          change={setOutputRoot}
          busy={busy}
        />
        <section className="form-section">
          <div className="form-heading">
            <span>03</span>
            <h2>Execution resources</h2>
          </div>
          <div className="resource-field">
            <div>
              <label htmlFor="threads">CPU threads</label>
              <p>Limited to your session’s available resources.</p>
            </div>
            <select
              id="threads"
              disabled={busy}
              value={threads}
              onChange={(e) => setThreads(Number(e.target.value))}
            >
              {Array.from({ length: config?.max_threads || 1 }, (_, i) => (
                <option key={i + 1} value={i + 1}>
                  {i + 1} {i === 0 ? "thread" : "threads"}
                </option>
              ))}
            </select>
          </div>
          <div className="inline-note">
            <Server size={14} />
            Runs locally on this host. Analyses execute one at a time.
          </div>
        </section>
      </div>
      <aside className="analysis-summary">
        <div className="summary-label">RUN SUMMARY</div>

        <h3>{name || "Untitled analysis"}</h3>
        <dl>
          <div>
            <dt>Workflow</dt>
            <dd>{modeLabel(mode)}</dd>
          </div>
          <div>
            <dt>Input files</dt>
            <dd>
              {mode === "multiqc" && multiqcDirectory.trim()
                ? "Directory import"
                : configuredPaths.length}
            </dd>
          </div>
          <div>
            <dt>CPU threads</dt>
            <dd>{threads}</dd>
          </div>
          <div>
            <dt>Output root</dt>
            <dd className="output-destination">
              {outputRoot ||
                config?.default_output ||
                "Default results directory"}
            </dd>
          </div>
          <div>
            <dt>Executor</dt>
            <dd>Local</dd>
          </div>
        </dl>
        {config &&
          ((!config.tools.fastqc && mode !== "multiqc") ||
            (!config.tools.multiqc && mode !== "fastqc")) && (
            <p className="tool-warning">
              {Object.values(config.tool_details || {})
                .filter(
                  (tool) =>
                    ((tool.name === "fastqc" && mode !== "multiqc") ||
                      (tool.name === "multiqc" && mode !== "fastqc")) &&
                    tool.error,
                )
                .map((tool) => tool.error)
                .join(" ") ||
                "A required QC tool is unavailable on this host. Configure it before starting."}
            </p>
          )}
        <button
          className="button primary"
          disabled={
            busy ||
            (!configuredPaths.length &&
              !(mode === "multiqc" && multiqcDirectory.trim())) ||
            (!!config &&
              ((!config.tools.fastqc && mode !== "multiqc") ||
                (!config.tools.multiqc && mode !== "fastqc")))
          }
          onClick={() => void submit()}
        >
          {busy ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <Play size={15} />
          )}
          Run analysis
        </button>
        <p>
          <ShieldCheck size={13} />
          Your original files stay unchanged.
        </p>
      </aside>
    </div>
  );
}
