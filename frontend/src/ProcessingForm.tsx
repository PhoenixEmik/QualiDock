import { Play } from "lucide-react";
import type {
  Config,
  Entry,
  ProcessingOptions,
  Run,
  SampleConfiguration,
} from "./types";
import { defaults, processingModes } from "./processing";
import { modeLabel } from "./api";
import SampleEditor from "./SampleEditor";
import OutputDirectory from "./OutputDirectory";
export default function ProcessingForm({
  config,
  selected,
  busy,
  mode,
  setMode,
  options,
  setOptions,
  name,
  setName,
  threads,
  setThreads,
  outputRoot,
  setOutputRoot,
  samples,
  setSamples,
  prepare,
  browse,
  submit,
}: {
  config: Config | null;
  selected: Map<string, Entry>;
  busy: boolean;
  mode: Run["mode"];
  setMode: (mode: Run["mode"]) => void;
  options: ProcessingOptions;
  setOptions: (options: ProcessingOptions) => void;
  name: string;
  setName: (name: string) => void;
  threads: number;
  setThreads: (n: number) => void;
  outputRoot: string;
  setOutputRoot: (s: string) => void;
  samples: SampleConfiguration | null;
  setSamples: (s: SampleConfiguration) => void;
  prepare: () => Promise<unknown>;
  browse: () => void;
  submit: () => Promise<void>;
}) {
  const files = [...selected.values()].filter(
    (entry) => entry.kind === "fastq",
  );
  const fastp = mode === "fastp",
    tool = fastp ? "fastp" : "seqkit";
  const update = (changes: Partial<ProcessingOptions>) =>
    setOptions({ ...options, ...changes });
  const required = [
    tool,
    ...(fastp && options.compare_qc ? ["fastqc"] : []),
    ...(fastp && options.multiqc ? ["multiqc"] : []),
  ];
  const missing = required.filter(
    (name) => !config?.tool_details?.[name]?.compatible,
  );
  const unavailable = missing.length > 0;
  return (
    <section className="processing-setup" aria-label="Read processing setup">
      <div className="form-section">
        <label htmlFor="processing-operation">Operation</label>
        <select
          id="processing-operation"
          value={mode}
          disabled={busy}
          onChange={(e) => {
            setMode(e.target.value as Run["mode"]);
            setOptions(defaults(e.target.value));
          }}
        >
          {processingModes.map((item) => (
            <option key={item} value={item}>
              {modeLabel(item)}
            </option>
          ))}
        </select>
        <p>
          {fastp
            ? "Trim adapters and filter reads with fastp. Each confirmed pair or single read is processed separately."
            : "Run a focused SeqKit utility on each selected file. Derived reads remain independent files; mates are not silently repaired or relabeled as synchronized pairs."}
        </p>
        <div className="processing-selection">
          <strong>{files.length} FASTQ files selected</strong>
          <button className="button small" onClick={browse}>
            Browse & select FASTQs
          </button>
        </div>
        {!!files.length && (
          <details>
            <summary>Selected input files</summary>
            <ul>
              {files.map((file) => (
                <li key={file.path} className="mono">
                  {file.path}
                </li>
              ))}
            </ul>
          </details>
        )}
        {fastp && (
          <>
            <label>
              <input
                type="checkbox"
                checked={options.adapter_trimming ?? true}
                onChange={(e) => update({ adapter_trimming: e.target.checked })}
              />{" "}
              Adapter detection and trimming
            </label>
            <label>
              <input
                type="checkbox"
                checked={options.quality_filtering ?? true}
                onChange={(e) =>
                  update({ quality_filtering: e.target.checked })
                }
              />{" "}
              Quality filtering
            </label>
            <label>
              <input
                type="checkbox"
                checked={options.compare_qc ?? true}
                onChange={(e) => update({ compare_qc: e.target.checked })}
              />{" "}
              FastQC before and after processing
            </label>
          </>
        )}
        {mode === "seqkit-sample" && (
          <>
            <label>
              Sampling fraction (0–1)
              <input
                aria-label="Sampling fraction"
                type="number"
                min="0.000001"
                max="1"
                step="0.01"
                value={options.fraction ?? 0.1}
                onChange={(e) => update({ fraction: Number(e.target.value) })}
              />
            </label>
            <p className="inline-note">
              Fraction sampling is reproducible with a fixed seed and tool
              version. The requested fraction is a probability, not an exact
              read count.
            </p>
          </>
        )}
        {(fastp || mode === "seqkit-filter") && (
          <label>
            Minimum read length (bp)
            <input
              type="number"
              min="1"
              max="1000000"
              value={options.min_length ?? 15}
              onChange={(e) => update({ min_length: Number(e.target.value) })}
            />
          </label>
        )}
        {mode === "seqkit-extract" && (
          <label>
            Exact read identifiers (one per line)
            <textarea
              rows={5}
              value={options.identifiers?.join("\n") || ""}
              onChange={(e) =>
                update({
                  identifiers: e.target.value.split(/\r?\n/).filter(Boolean),
                })
              }
            />
          </label>
        )}
        <details className="processing-advanced">
          <summary>Advanced settings</summary>
          <label>
            Analysis name (optional)
            <input
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          {mode !== "seqkit-stats" && (
            <label>
              <input
                type="checkbox"
                checked={options.gzip ?? true}
                onChange={(e) => update({ gzip: e.target.checked })}
              />{" "}
              Gzip-compressed output
            </label>
          )}
          {fastp && (
            <>
              <label>
                Qualified Phred score
                <input
                  type="number"
                  min="0"
                  max="93"
                  value={options.qualified_quality ?? 15}
                  onChange={(e) =>
                    update({ qualified_quality: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Maximum unqualified bases (%)
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={options.unqualified_percent ?? 40}
                  onChange={(e) =>
                    update({ unqualified_percent: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={options.multiqc ?? false}
                  onChange={(e) => update({ multiqc: e.target.checked })}
                />{" "}
                Generate combined MultiQC report
              </label>
              <p className="inline-note">
                Phred+33 input. Poly-G trimming and duplication estimation are
                disabled; no deduplication, merging, or base correction is
                performed.
              </p>
            </>
          )}
          {mode === "seqkit-sample" && (
            <label>
              Random seed
              <input
                type="number"
                min="0"
                max="2147483647"
                value={options.seed ?? 11}
                onChange={(e) => update({ seed: Number(e.target.value) })}
              />
            </label>
          )}
          {mode === "seqkit-filter" && (
            <label>
              Maximum read length (optional)
              <input
                type="number"
                min="1"
                max="1000000"
                value={options.max_length ?? ""}
                onChange={(e) =>
                  update({
                    max_length: e.target.value ? Number(e.target.value) : null,
                  })
                }
              />
            </label>
          )}
          <label>
            CPU threads
            <select
              value={threads}
              onChange={(e) => setThreads(Number(e.target.value))}
            >
              {Array.from({ length: config?.max_threads || 1 }, (_, i) => (
                <option key={i + 1}>{i + 1}</option>
              ))}
            </select>
          </label>
          <OutputDirectory
            config={config}
            value={outputRoot}
            change={setOutputRoot}
            busy={busy}
          />
        </details>
        {fastp && !!files.length && (
          <details>
            <summary>Review read pairs and sample groups</summary>
            {samples ? (
              <SampleEditor value={samples} change={setSamples} busy={busy} />
            ) : (
              <button className="button" onClick={() => void prepare()}>
                Detect and review pairs
              </button>
            )}
          </details>
        )}
        <p className="inline-note">
          Original FASTQs stay unchanged. A unique analysis directory stores
          reports and separate derived FASTQs. Default output:{" "}
          {outputRoot || config?.default_output}.
        </p>
        {unavailable && (
          <p role="status" className="tool-warning">
            {missing
              .map(
                (name) =>
                  config?.tool_details?.[name]?.error ||
                  `${name} is unavailable; configure its executable path.`,
              )
              .join(" ")}
          </p>
        )}
        <button
          className="button primary"
          disabled={busy || !files.length || !!unavailable}
          onClick={() => void submit()}
        >
          <Play size={15} />
          {busy ? "Starting…" : "Run processing"}
        </button>
      </div>
    </section>
  );
}
