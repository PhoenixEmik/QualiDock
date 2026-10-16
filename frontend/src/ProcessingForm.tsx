import { Play } from "lucide-react";
import type {
  Config,
  Entry,
  ProcessingOptions,
  Run,
  SampleConfiguration,
} from "./types";
import {
  defaults,
  processingModes,
  processingTools,
  supportsExactCount,
} from "./processing";
import { modeLabel } from "./api";
import { ReadRelationships } from "./SampleEditor";
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
  const fastp = mode === "fastp";
  const pairs = (samples?.input_pairing || files).filter(
    (row) =>
      row.paired && row.read === "R1" && !!row.mate && selected.has(row.mate),
  ).length;
  const update = (changes: Partial<ProcessingOptions>) =>
    setOptions({ ...options, ...changes });
  const required = processingTools(mode, options, pairs, files.length);
  const missing = required.filter(
    (name) => !config?.tool_details?.[name]?.compatible,
  );
  const exactUnavailable =
    mode === "seqkit-sample" &&
    options.count != null &&
    !supportsExactCount(config?.tool_details?.seqkit?.version);
  const unavailable = missing.length > 0 || exactUnavailable;
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
            : mode === "seqkit-sample"
              ? "Reproducible fraction or exact-count sampling. Confirmed mates stay synchronized and must pass full output checks."
              : mode === "seqkit-stats"
                ? "Inspect original FASTQ statistics without creating derived files."
                : "Filter or extract FASTQ records. Choose whether confirmed mates must stay together; original files remain unchanged."}
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
              Quality and N-base filtering
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
        {["seqkit-filter", "seqkit-extract"].includes(mode) && pairs > 0 && (
          <>
            <label>
              <input
                type="checkbox"
                checked={options.preserve_pairs ?? false}
                onChange={(e) => update({ preserve_pairs: e.target.checked })}
              />{" "}
              Keep R1/R2 pairs together
            </label>
            <p className="inline-note">
              {options.preserve_pairs
                ? mode === "seqkit-filter"
                  ? "Keep a pair only when both reads meet the length limits. Unpaired inputs remain independent."
                  : "Match exact IDs after removing terminal /1 or /2. Ambiguous duplicate source IDs fail; missing IDs are listed."
                : "Process each file independently; outputs are explicitly unpaired."}
            </p>
          </>
        )}
        {mode === "seqkit-sample" && (
          <>
            <label>
              Sampling method{" "}
              <select
                aria-label="Sampling method"
                value={options.count == null ? "fraction" : "count"}
                onChange={(e) =>
                  update({ count: e.target.value === "count" ? 100000 : null })
                }
              >
                <option value="fraction">Fraction</option>
                <option value="count">Exact count</option>
              </select>
            </label>
            {options.count != null ? (
              <label>
                {pairs * 2 === files.length
                  ? "Exact read pairs per dataset"
                  : pairs
                    ? "Exact records per dataset (pairs or reads)"
                    : "Exact reads per file"}
                <input
                  aria-label="Exact count"
                  type="number"
                  min="1"
                  max="9007199254740991"
                  step="1"
                  value={options.count}
                  onChange={(e) => update({ count: Number(e.target.value) })}
                />
              </label>
            ) : (
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
                    onChange={(e) =>
                      update({ fraction: Number(e.target.value) })
                    }
                  />
                </label>
                <p className="inline-note">
                  Fraction sampling is reproducible with a fixed seed and tool
                  version. The requested fraction is a probability, not an exact
                  read count.
                </p>
              </>
            )}
            <label>
              Random seed{" "}
              <input
                type="number"
                min="0"
                max="2147483647"
                value={options.seed ?? 11}
                onChange={(e) => update({ seed: Number(e.target.value) })}
              />
            </label>
            {options.count != null && (
              <p className="inline-note">
                Uniform sampling without replacement, preserving input order.
                The count applies to each pair or single-end dataset; requests
                exceeding available records fail.
              </p>
            )}
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
                Phred+33 input. Quality filtering includes a maximum of 5 N
                bases per read. Poly-G trimming and duplication estimation are
                disabled; no deduplication, merging, or base correction is
                performed.
              </p>
            </>
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
        {mode !== "seqkit-stats" && !!files.length && (
          <ReadRelationships
            value={samples}
            change={setSamples}
            prepare={prepare}
            busy={busy}
          />
        )}
        <p className="inline-note">
          Original FASTQs stay unchanged. A unique analysis directory stores
          reports and separate derived FASTQs. Default output:{" "}
          {outputRoot || config?.default_output}.
        </p>
        {exactUnavailable && (
          <p role="status" className="tool-warning">
            Exact-count sampling requires SeqKit 2.14 or newer. Fraction
            sampling remains available on older compatible versions.
          </p>
        )}
        {!!missing.length && (
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
