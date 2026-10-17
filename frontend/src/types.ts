export type View = "workspace" | "new" | "processing" | "analyses" | "analysis";
export type DetailTab = "overview" | "metrics" | "reports";
export type RunState =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "partial"
  | "cancelled"
  | "interrupted";
export type RunSummary = Pick<
  Run,
  | "id"
  | "name"
  | "mode"
  | "state"
  | "stage"
  | "created_at"
  | "updated_at"
  | "started_at"
  | "finished_at"
  | "threads"
  | "sample_count"
  | "error"
> & { input_count: number };
export interface HistoryPage {
  items: RunSummary[];
  offset: number;
  limit: number;
  total: number;
  overall_total: number;
  revision: number;
}
export interface DatasetReference {
  run_id: string;
  dataset_id: string;
  path?: string;
}
export interface Run {
  input_datasets?: DatasetReference[];
  input_provenance?: (DerivedDataset & {
    run_id: string;
    dataset_id: string;
    absolute_path: string;
  })[];
  id: string;
  name: string;
  mode:
    | "both"
    | "fastqc"
    | "multiqc"
    | "mosdepth"
    | "samtools"
    | "rseqc-infer"
    | "rseqc-distribution"
    | "picard"
    | "nanoplot"
    | "nanoq"
    | "fastq-screen"
    | "fastp"
    | "seqkit-stats"
    | "seqkit-sample"
    | "seqkit-filter"
    | "seqkit-extract";
  state: RunState;
  stage: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  threads: number;
  inputs: string[];
  input_pairing?: InputPairing[];
  sample_groups?: SampleGroup[];
  sample_input_paths?: string[];
  output_root?: string;
  output_directory?: string;
  rerun_of?: string | null;
  pairing_note?: string | null;
  import_summary?: {
    supported_reports?: number;
    unsupported_files: number;
    exclusions: { filename: string; reason: string }[];
  };
  report_inputs?: {
    path: string;
    kind?: string;
    tool?: string;
    version?: string | null;
    schema?: string;
    snapshot_sha256?: string;
    snapshot_artifact?: string;
  }[];
  processing?: ProcessingResult;
  qc?: {
    tool:
      | "nanoq"
      | "nanoplot"
      | "fastq_screen"
      | "samtools"
      | "mosdepth"
      | "rseqc-infer"
      | "rseqc-distribution"
      | "picard";
    options: Record<string, unknown>;
    annotation?: { id: string; path: string; sha256: string; identity: string };
    reference?: {
      id: string;
      path: string;
      identity: string;
      fai_sha256: string;
    };
    reference_panel?: {
      id: string;
      sha256: string;
      index_identity: string;
      references: { name: string; prefix: string }[];
    };
    results: {
      id: string;
      path: string;
      name: string;
      state: string;
      error: string | null;
      report: string;
      source_sha256?: string;
      picard?: {
        status: string;
        mapped_pairs_reported?: string;
        metrics: ReportedTable;
        histogram: ReportedTable;
        reports: Record<string, string>;
        heap_mb: number;
        minimum_orientation_fraction: string;
        deviations: string;
        rscript_version: string | null;
      };
      rseqc?: {
        operation: string;
        columns: string[];
        rows: string[][];
        reports: Record<string, string>;
        sampled_alignments?: string;
        layout?: string;
        status?: string;
        totals?: string[][];
      };
      mosdepth?: CoverageMetrics;
      alignment?: {
        format: string;
        quickcheck: string;
        reports: Record<string, string>;
        flagstat: { columns: string[]; rows: string[][] };
        stats: { columns: string[]; rows: string[][] };
      };
      nanoplot?: {
        columns: string[];
        rows: string[][];
        html: string;
        plots: string[];
      };
      screen?: {
        columns: string[];
        rows: string[][];
        no_genome_percent: string;
        processed_reads: number;
      };
      summary: Record<
        string,
        number | Record<string, number> | number[]
      > | null;
    }[];
  };
  derived_datasets?: DerivedDataset[];
  integrity?: IntegrityResult;
  report_input_map?: Record<
    string,
    {
      path?: string;
      source_report?: string;
      id: string;
      multiqc_name?: string;
      processing_stage?: "raw" | "processed";
    }
  >;
  input_outcomes?: {
    id: string;
    path: string;
    name: string;
    state: string;
    error: string | null;
    report: string;
    html: string;
    exit_code: number | null;
    finished_at: string | null;
  }[];
  progress: number;
  error: string | null;
  reports: { path: string; size: number }[];
  sample_count: number;
  tools?: Record<string, ToolInfo>;
  warnings?: string[];
  executions?: {
    tool: string;
    argv: string[];
    exit_code: number | null;
    started_at: string;
    finished_at: string | null;
  }[];
}
export interface IntegrityResult {
  task_id: string;
  state: string;
  result: string;
  mode: "full" | "quick";
  version: string;
  total_files: number;
  configured_pairs: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  artifact: string;
  current_file?: {
    path: string;
    records_scanned: number;
    state: string;
  } | null;
  files: {
    id: string;
    path: string;
    state: string;
    coverage: string;
    records_scanned: number;
    bases_scanned: number;
    gzip_crc: string;
    sha256: string | null;
    q20_bases: number | null;
    q30_bases: number | null;
    quality_bases: number | null;
    encoding_source?: string | null;
    source_snapshot?: {
      size: number;
      mtime_ns: number;
      device: number;
      inode: number;
    };
    error: string | null;
  }[];
  pairs: {
    id: string;
    r1: string;
    r2: string;
    state: string;
    error: string | null;
    method: string;
  }[];
}
export type MetadataSource = "auto" | "confirmed" | "manual";
export interface SampleGroup {
  id: string;
  display_name: string;
  files: string[];
  source: MetadataSource;
}
export interface SampleConfiguration {
  input_pairing: InputPairing[];
  sample_groups: SampleGroup[];
  pairing_note?: string | null;
  import_summary?: {
    supported_reports?: number;
    unsupported_files: number;
    exclusions: { filename: string; reason: string }[];
  };
  report_inputs?: {
    path: string;
    kind?: string;
    tool?: string;
    version?: string | null;
    schema?: string;
    snapshot_sha256?: string;
    snapshot_artifact?: string;
  }[];
}
export interface OutputLocation {
  path: string;
  default: boolean;
  available: boolean;
  free_bytes: number | null;
  error: string | null;
}
export interface RerunConfiguration extends SampleConfiguration {
  qc_options?:
    | PicardOptions
    | Partial<RnaOptions>
    | ScreenOptions
    | NanoPlotOptions
    | AlignmentOptions
    | (CoverageOptions & { reference: string | null });
  input_datasets?: DatasetReference[];
  name: string;
  mode: Run["mode"];
  paths: string[];
  entries: Entry[];
  threads: number;
  output_root: string;
  rerun_of: string | null;
  processing_options?: ProcessingOptions;
}
export interface InputPairing {
  path: string;
  name: string;
  read: string | null;
  pair_key: string | null;
  paired: boolean;
  mate: string | null;
  source?: MetadataSource;
  ambiguous?: boolean;
  assignment?: "paired" | "single" | "unpaired";
  lane?: string | null;
  chunk?: string | null;
}
export interface Entry {
  name: string;
  path: string;
  kind: "directory" | "fastq" | "fastqc" | "qcreport" | "alignment" | "file";
  size: number | null;
  modified: number;
  read: string | null;
  pair_key: string | null;
  paired: boolean;
  mate: string | null;
  sample_key?: string | null;
  sample_name?: string;
  lane?: string | null;
  chunk?: string | null;
  ambiguous?: boolean;
}
export interface Listing {
  path: string;
  parent: string | null;
  entries: Entry[];
  total: number;
  sample_groups?: Record<string, { paths: string[]; total: number }>;
  snapshot?: string;
  next_offset?: number | null;
}
export interface ToolInfo {
  rscript_executable?: string | null;
  java_executable?: string;
  version_probe_exit_code?: number;
  suite_version?: string;
  name: string;
  executable: string;
  available: boolean;
  compatible: boolean;
  version: string | null;
  error: string | null;
}
export interface MultiQCSummary {
  tool?: string;
  version?: string | null;
  status?: "available" | "empty" | "missing" | "unsupported" | "invalid";
  message?: string | null;
  columns: {
    key: string;
    title: string;
    description: string;
    namespace: string;
    unit: string;
    raw_key: string;
    raw_unit?: string;
    section?: string;
    hidden?: boolean;
  }[];
  rows: { sample: string; values: Record<string, string | number> }[];
}
export interface PicardOptions {
  multiqc?: boolean;
  by_library: boolean;
  include_duplicates: boolean;
  histogram_pdf: boolean;
}
export interface RnaOptions {
  multiqc?: boolean;
  annotation: string;
  sample_size: number;
  mapq: number;
}
export interface Config {
  rna_annotations?: {
    id: string;
    available: boolean;
    transcripts?: number;
    error: string | null;
  }[];
  coverage_panels?: {
    id: string;
    available: boolean;
    intervals?: number;
    error: string | null;
  }[];
  alignment_references?: {
    id: string;
    available: boolean;
    error: string | null;
  }[];
  screen_panels?: {
    id: string;
    available: boolean;
    references: string[];
    error: string | null;
  }[];
  roots: string[];
  default_output?: string;
  output_locations?: OutputLocation[];
  cpus: number;
  memory_mb: number;
  max_threads: number;
  tools: {
    fastqc: boolean;
    multiqc: boolean;
    fastp?: boolean;
    seqkit?: boolean;
    nanoq?: boolean;
    nanoplot?: boolean;
    samtools?: boolean;
    mosdepth?: boolean;
    java?: boolean;
    picard?: boolean;
    rseqc_infer?: boolean;
    rseqc_distribution?: boolean;
    fastq_screen?: boolean;
    bowtie2?: boolean;
  };
  prefix: string;
  tool_details?: Record<string, ToolInfo>;
}
export interface AlignmentOptions {
  reference: string | null;
  multiqc: boolean;
}
export interface NanoPlotOptions {
  loglength: boolean;
  individual_plots: boolean;
}
export interface ScreenOptions {
  panel: string;
  subset: number;
  multiqc: boolean;
}
export interface Module {
  name: string;
  status: string;
  columns: string[];
  rows: string[][];
  metadata?: string[][];
  comments?: string[];
  summary_status?: string;
  available?: boolean;
}
export interface BaseQuality {
  base: string;
  mean: number | null;
  median: number | null;
  lower_quartile: number | null;
  upper_quartile: number | null;
  percentile_10: number | null;
  percentile_90: number | null;
}
export interface Sample {
  id: string;
  name: string;
  fastqc_version: string;
  total_sequences: number | null;
  gc_percent: number | null;
  sequence_length: string;
  encoding: string;
  status: string;
  modules: Module[];
  per_base_quality: BaseQuality[];
}

export interface ProcessingOptions {
  adapter_trimming?: boolean;
  quality_filtering?: boolean;
  qualified_quality?: number;
  unqualified_percent?: number;
  min_length?: number;
  gzip?: boolean;
  compare_qc?: boolean;
  multiqc?: boolean;
  preserve_pairs?: boolean;
  count?: number | null;
  fraction?: number;
  seed?: number;
  max_length?: number | null;
  identifiers?: string[];
}
export interface ProcessingResult {
  schema_version: number;
  options: ProcessingOptions;
  quality_encoding?: string;
  units: {
    id: string;
    inputs: string[];
    outputs: string[];
    state: string;
    error: string | null;
    lane?: string | null;
    chunk?: string | null;
    raw_qc?: { report: string; state: string }[];
    processed_qc?: { report: string; state: string }[];
    fastp?: {
      summary: {
        before_filtering: Record<string, number>;
        after_filtering: Record<string, number>;
      };
      filtering_result?: Record<string, number>;
      adapter_cutting?: Record<string, unknown>;
    } | null;
    processor?: { name: string; version: string };
    selection?: {
      processor: string;
      version: string;
      operation: string;
      record_unit: "reads" | "read_pairs";
      input_records: number;
      retained_records: number;
      removed_records: number;
      requested_identifiers?: number;
      matched_identifiers?: number;
      missing_identifiers?: string[];
    };
    statistics?: Record<string, string>[];
  }[];
}
export interface DerivedDataset {
  id: string;
  unit_id: string;
  path: string;
  source: string;
  stage: string;
  paired: boolean;
  read: string | null;
  sha256: string;
  records: number;
  bases: number;
}

export interface CoverageOptions {
  panel: string | null;
  mapq: number;
  exclude_supplementary: boolean;
}
export interface ReportedTable {
  columns: string[];
  rows: string[][];
  total_rows: number;
}
export interface CoverageMetrics {
  summary: ReportedTable;
  total: string[];
  distribution: ReportedTable;
  regions?: ReportedTable;
  thresholds?: ReportedTable;
  requested_region_bases?: number;
  reported_region_bases?: number | null;
  reported_reference_bases: number;
  header_reference_bases: number;
  omitted_reference_count: number;
  omitted_references: string[];
  reports: Record<string, string>;
  index: { path: string; identity: string };
  mapq: number;
  exclude_flags: number;
  precision: number;
}
