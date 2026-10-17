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
import { bytes, modeLabel, isAlignmentQC } from "./api";
import { Empty } from "./Feedback";
import { ReadRelationships } from "./SampleEditor";
import OutputDirectory from "./OutputDirectory";
import type { SampleConfiguration } from "./types";
import type {
  Config,
  Entry,
  Run,
  ScreenOptions,
  NanoPlotOptions,
  AlignmentOptions,
  CoverageOptions,
} from "./types";

interface Props {
  coverageOptions: CoverageOptions;
  setCoverageOptions: (value: CoverageOptions) => void;
  alignmentOptions: AlignmentOptions;
  setAlignmentOptions: (value: AlignmentOptions) => void;
  nanoPlotOptions: NanoPlotOptions;
  setNanoPlotOptions: (value: NanoPlotOptions) => void;
  qcOptions: ScreenOptions;
  setQcOptions: (value: ScreenOptions) => void;
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
  coverageOptions,
  setCoverageOptions,
  alignmentOptions,
  setAlignmentOptions,
  nanoPlotOptions,
  setNanoPlotOptions,
  qcOptions,
  setQcOptions,
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
      : isAlignmentQC(mode)
        ? entry.kind === "alignment"
        : entry.kind === "fastq";
  const configuredPaths = [...selected.values()].filter(suitable);
  const required =
    mode === "mosdepth"
      ? ["samtools", "mosdepth"]
      : mode === "samtools"
        ? ["samtools", ...(alignmentOptions.multiqc ? ["multiqc"] : [])]
        : mode === "nanoplot"
          ? ["nanoplot"]
          : mode === "fastq-screen"
            ? [
                "fastq_screen",
                "bowtie2",
                ...(qcOptions.multiqc ? ["multiqc"] : []),
              ]
            : mode === "nanoq"
              ? ["nanoq"]
              : mode === "fastqc"
                ? ["fastqc"]
                : mode === "multiqc"
                  ? ["multiqc"]
                  : ["fastqc", "multiqc"];
  const unavailable = config
    ? required.filter((tool) => !config.tools[tool as keyof Config["tools"]])
    : [];
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
            {(
              [
                "both",
                "fastqc",
                "multiqc",
                "nanoq",
                "nanoplot",
                "fastq-screen",
                ...([...selected.values()].some(
                  (entry) => entry.kind === "alignment",
                )
                  ? (["samtools", "mosdepth"] as const)
                  : []),
              ] as const
            ).map((value) => (
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
                  {value === "mosdepth"
                    ? "Original depth distribution and approved-region coverage"
                    : value === "samtools"
                      ? "Read-only BAM/CRAM header/EOF, flagstat and stats"
                      : value === "both"
                        ? "Individual read QC and a combined report"
                        : value === "fastqc"
                          ? "Individual read quality assessment"
                          : value === "fastq-screen"
                            ? "Read-source mapping against an approved reference panel"
                            : value === "nanoplot"
                              ? "Original long-read plots and NanoStats"
                              : value === "nanoq"
                                ? "Read-only long-read counts, N50 and quality summaries"
                                : "Combine existing FastQC or fastp JSON reports"}
                </small>
                {mode === value && <Check size={15} />}
              </button>
            ))}
          </div>
          {isAlignmentQC(mode) && (
            <>
              <p className="inline-note">
                BAM/CRAM files are independent alignment inputs. No FASTQ
                pairing, sorting, indexing or editing.{" "}
                {mode === "samtools"
                  ? "quickcheck checks header/EOF only; flagstat and stats scan records separately."
                  : "An existing matching index and coordinate-sorted input are required. A SAMtools stats scan checks actual sorting and CRAM decoding before coverage."}
              </p>
              {configuredPaths.some((entry) => /\.cram$/i.test(entry.name)) && (
                <>
                  <label className="field-label" htmlFor="alignment-reference">
                    Local CRAM reference
                  </label>
                  <select
                    id="alignment-reference"
                    disabled={busy}
                    value={alignmentOptions.reference || ""}
                    onChange={(e) =>
                      setAlignmentOptions({
                        ...alignmentOptions,
                        reference: e.target.value || null,
                      })
                    }
                  >
                    <option value="">Choose an approved existing FASTA</option>
                    {config?.alignment_references?.map((ref) => (
                      <option
                        key={ref.id}
                        value={ref.id}
                        disabled={!ref.available}
                      >
                        {ref.id}
                        {ref.error ? ` · ${ref.error}` : ""}
                      </option>
                    ))}
                  </select>
                  <p className="inline-note">
                    Matching local FASTA and existing .fai required. No
                    automatic reference download or index creation.
                  </p>
                </>
              )}
              {mode === "samtools" && (
                <label>
                  <input
                    type="checkbox"
                    disabled={busy || !config?.tools.multiqc}
                    checked={alignmentOptions.multiqc}
                    onChange={(e) =>
                      setAlignmentOptions({
                        ...alignmentOptions,
                        multiqc: e.target.checked,
                      })
                    }
                  />{" "}
                  Generate MultiQC
                </label>
              )}
            </>
          )}
          {mode === "mosdepth" && (
            <>
              <label className="field-label" htmlFor="coverage-panel">
                Target regions (optional)
              </label>
              <select
                id="coverage-panel"
                disabled={busy}
                value={coverageOptions.panel || ""}
                onChange={(e) =>
                  setCoverageOptions({
                    ...coverageOptions,
                    panel: e.target.value || null,
                  })
                }
              >
                <option value="">Reported global coverage only</option>
                {config?.coverage_panels?.map((p) => (
                  <option key={p.id} value={p.id} disabled={!p.available}>
                    {p.id}
                    {p.error ? ` · ${p.error}` : ` · ${p.intervals} intervals`}
                  </option>
                ))}
              </select>
              <p className="inline-note">
                Approved local BED only. Region outputs include actual counts of
                bases at ≥1×, ≥10×, ≥20× and ≥30×. Per-base output is always
                disabled.
              </p>
              <details className="processing-advanced">
                <summary>Coverage filters (optional)</summary>
                <label htmlFor="coverage-mapq">Minimum alignment MAPQ</label>
                <input
                  id="coverage-mapq"
                  type="number"
                  min={0}
                  max={255}
                  disabled={busy}
                  value={coverageOptions.mapq}
                  onChange={(e) =>
                    setCoverageOptions({
                      ...coverageOptions,
                      mapq: Number(e.target.value),
                    })
                  }
                />
                <label>
                  <input
                    type="checkbox"
                    checked={coverageOptions.exclude_supplementary}
                    disabled={busy}
                    onChange={(e) =>
                      setCoverageOptions({
                        ...coverageOptions,
                        exclude_supplementary: e.target.checked,
                      })
                    }
                  />{" "}
                  Exclude supplementary alignments
                </label>
                <p className="inline-note">
                  Unmapped, secondary, QC-failed and duplicate alignments are
                  excluded. Default mosdepth CIGAR and mate-overlap handling is
                  retained. MAPQ is aligner-specific; 255 can mean unavailable.
                </p>
              </details>
            </>
          )}
          {mode === "nanoplot" && (
            <div>
              <p className="inline-note">
                Each FASTQ receives an independent original NanoPlot report.
                Time, channel activity and yield over time are unavailable from
                ordinary FASTQ. No read filtering or platform identification.
              </p>
              <details className="processing-advanced">
                <summary>Plot settings (optional)</summary>
                <label>
                  <input
                    type="checkbox"
                    checked={nanoPlotOptions.loglength}
                    disabled={busy}
                    onChange={(e) =>
                      setNanoPlotOptions({
                        ...nanoPlotOptions,
                        loglength: e.target.checked,
                      })
                    }
                  />{" "}
                  Additional logarithmic length plots
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={nanoPlotOptions.individual_plots}
                    disabled={busy}
                    onChange={(e) =>
                      setNanoPlotOptions({
                        ...nanoPlotOptions,
                        individual_plots: e.target.checked,
                      })
                    }
                  />{" "}
                  Save individual interactive plot HTML
                </label>
                <p className="inline-note">
                  Input is fully read before plotting; plot sampling does not
                  bound input I/O or initial memory. Plotly static export and
                  automatic Chrome downloads are disabled.
                </p>
              </details>
            </div>
          )}
          {mode === "fastq-screen" && (
            <div>
              <label className="field-label" htmlFor="screen-panel">
                Reference panel
              </label>
              <select
                id="screen-panel"
                value={qcOptions.panel}
                disabled={busy}
                onChange={(e) =>
                  setQcOptions({ ...qcOptions, panel: e.target.value })
                }
              >
                <option value="">Choose an approved panel</option>
                {config?.screen_panels?.map((panel) => (
                  <option
                    key={panel.id}
                    value={panel.id}
                    disabled={!panel.available}
                  >
                    {panel.id}{" "}
                    {panel.error
                      ? `· ${panel.error}`
                      : `· ${panel.references.join(", ")}`}
                  </option>
                ))}
              </select>
              {!config?.screen_panels?.some((p) => p.available) && (
                <p role="status">
                  No usable reference panel. An administrator must configure
                  existing Bowtie2 indexes; QualiDock never downloads genomes or
                  builds references.
                </p>
              )}
              <p className="inline-note">
                Each FASTQ is screened independently, including R1 and R2. No
                paired alignments or definitive contamination judgments.
                Alignment assumes Phred+33 qualities.
              </p>
              <details className="processing-advanced">
                <summary>Screening settings (optional)</summary>
                <label>
                  Target subset size (reads per file){" "}
                  <input
                    type="number"
                    min={1}
                    max={1000000}
                    value={qcOptions.subset}
                    disabled={busy}
                    onChange={(e) =>
                      setQcOptions({
                        ...qcOptions,
                        subset: Number(e.target.value),
                      })
                    }
                  />
                </label>
                <p className="inline-note">
                  Systematic subsampling, not exact random sampling. FastQ
                  Screen may process up to twice this target; actual counts are
                  reported.
                </p>
                <label>
                  <input
                    type="checkbox"
                    checked={qcOptions.multiqc}
                    disabled={busy || !config?.tools.multiqc}
                    onChange={(e) =>
                      setQcOptions({ ...qcOptions, multiqc: e.target.checked })
                    }
                  />{" "}
                  Generate MultiQC
                </label>
              </details>
            </div>
          )}
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
                {isAlignmentQC(mode)
                  ? "Alignment files are evaluated independently; read-pair metadata does not apply."
                  : mode === "multiqc"
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
          !isAlignmentQC(mode) &&
          configuredPaths.length > 0 && (
            <ReadRelationships
              value={sampleConfiguration}
              change={setSampleConfiguration}
              prepare={prepareSamples}
              busy={busy}
            />
          )}
        <details className="processing-advanced">
          <summary>Output and resource settings (optional)</summary>
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
        </details>
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
        {unavailable.length > 0 && (
          <p className="tool-warning">
            {Object.values(config?.tool_details || {})
              .filter((tool) => unavailable.includes(tool.name) && tool.error)
              .map((tool) => tool.error)
              .join(" ") ||
              "A required QC tool is unavailable on this host. Configure it before starting."}
          </p>
        )}
        <button
          className="button primary"
          disabled={
            busy ||
            (isAlignmentQC(mode) &&
              configuredPaths.some((entry) => /\.cram$/i.test(entry.name)) &&
              !alignmentOptions.reference) ||
            (!configuredPaths.length &&
              !(mode === "multiqc" && multiqcDirectory.trim())) ||
            unavailable.length > 0 ||
            (mode === "fastq-screen" &&
              !config?.screen_panels?.some(
                (panel) => panel.id === qcOptions.panel && panel.available,
              ))
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
