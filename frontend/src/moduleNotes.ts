import { moduleKey } from "./qc.ts";

interface Help {
  measures: string;
  classification: string;
  context: string;
  caution: string;
  page: string;
}
/** Static notes checked against upstream FastQC help. The run's reported status
 * remains authoritative: limits/configuration/version can change classification.
 */
const help: Record<string, Help> = {
  basicstatistics: {
    measures:
      "File identity, sequence count, length range, quality encoding and overall GC percentage.",
    classification:
      "Basic Statistics normally has no warning or failure test. PASS records the module outcome, not overall library suitability.",
    context:
      "Length and GC expectations depend on the organism, library and sequencing protocol.",
    caution:
      "Totals describe this FASTQ file. They are not counts of unique molecules or paired fragments.",
    page: "1 Basic Statistics",
  },
  perbasesequencequality: {
    measures:
      "Reported mean, median, quartiles and 10th/90th percentiles of quality at each base or grouped base bin.",
    classification:
      "WARN and FAIL flag FastQC's configured lower-quartile or median quality criteria. PASS means these criteria were not triggered.",
    context:
      "Cycle-dependent signal loss and base-calling conditions can affect the profile. R1 and R2 may differ.",
    caution:
      "Grouped bins remain grouped. Aggregate quality summaries cannot determine exact Q20/Q30 base percentages; those statistics are unavailable here.",
    page: "2 Per Base Sequence Quality",
  },
  persequencequalityscores: {
    measures: "Read counts at each reported mean per-read quality score.",
    classification:
      "WARN and FAIL reflect FastQC's criteria for the most frequent mean read quality. PASS means that criterion was not triggered.",
    context:
      "A lower-quality read population can be investigated alongside per-base and per-tile quality.",
    caution:
      "This is a distribution of read averages, not individual base qualities. Counts are not automatically normalized between files.",
    page: "3 Per Sequence Quality Scores",
  },
  perbasesequencecontent: {
    measures:
      "The percentage of A, C, G and T reported at each base or base bin.",
    classification:
      "WARN and FAIL flag FastQC's configured imbalance criteria for base composition. PASS means those criteria were not triggered.",
    context:
      "Random priming, tagmentation, RNA-seq, amplicons and targeted enrichment can produce protocol-dependent composition patterns.",
    caution:
      "A composition flag alone does not establish sequencing failure. Methylation-assay expectations depend on the actual chemistry.",
    page: "4 Per Base Sequence Content",
  },
  persequencegccontent: {
    measures: "The observed read-count distribution over per-read GC content.",
    classification:
      "WARN and FAIL reflect FastQC's configured deviation from its GC reference model. PASS does not prove the organism or library is correct.",
    context:
      "Library composition, enrichment and mixed sequence populations can affect the distribution.",
    caution:
      "RNA-seq, amplicon and targeted libraries need not match a random genomic-library model. A nonstandard shape alone is not a biological conclusion.",
    page: "5 Per Sequence GC Content",
  },
  perbasencontent: {
    measures:
      "The percentage of ambiguous N base calls at each position or grouped bin.",
    classification:
      "WARN and FAIL reflect FastQC's configured N-percentage limits. PASS means those limits were not triggered.",
    context:
      "Uncertain base calls can accompany reduced signal or cycle-specific quality changes.",
    caution:
      "Inspect the quality modules and protocol context together. Zero means FastQC reported zero; absent cells are unavailable.",
    page: "6 Per Base N Content",
  },
  sequencelengthdistribution: {
    measures: "Counts of reads at each reported length or length interval.",
    classification:
      "FastQC normally warns about variable lengths and fails on zero-length reads; the saved status reflects the actual run configuration.",
    context:
      "Variable lengths may be expected from the platform, library or earlier processing.",
    caution:
      "These are read lengths, not insert sizes. Differing bins are never expanded into invented individual lengths.",
    page: "7 Sequence Length Distribution",
  },
  sequenceduplicationlevels: {
    measures:
      "FastQC's reported duplication-level percentages and deduplicated-percentage metadata, where present.",
    classification:
      "WARN and FAIL reflect FastQC's configured duplication criteria. PASS means those criteria were not triggered.",
    context:
      "Depth, library complexity, amplification and biological enrichment can all contribute to repeated sequences.",
    caution:
      "RNA-seq, amplicon and targeted libraries may have expected repeats. FastQC sequence duplication is not alignment-based or UMI-aware molecular duplication.",
    page: "8 Duplicate Sequences",
  },
  overrepresentedsequences: {
    measures:
      "Reported frequent sequences, their counts and percentages, and possible source matches.",
    classification:
      "WARN and FAIL reflect FastQC's configured sequence-abundance limits. An empty list can legitimately accompany PASS.",
    context:
      "Biological enrichment, small-RNA libraries, adapters or other repeated sequence sources may contribute.",
    caution:
      "A possible source is a sequence similarity clue, not proof of contamination. Tracking and read-length limits can affect detection.",
    page: "9 Overrepresented Sequences",
  },
  adaptercontent: {
    measures:
      "Cumulative percentages of reads in which configured adapter sequences have been seen by each position.",
    classification:
      "WARN and FAIL reflect FastQC's configured adapter-content limits. PASS only concerns the adapters FastQC searched for.",
    context:
      "Short inserts and library-specific adapter sequences can affect these profiles.",
    caution:
      "Different adapter lists are not equivalent. Only shared named categories are overlaid; no trimming action is inferred from a flag.",
    page: "10 Adapter Content",
  },
  pertilesequencequality: {
    measures: "Reported quality deviations by flowcell tile and base bin.",
    classification:
      "WARN and FAIL reflect configured deviations below the mean quality for a base position. PASS means those criteria were not triggered.",
    context:
      "Localized flowcell effects or broader loading conditions can change tile profiles.",
    caution:
      "Tile information may be absent from read identifiers or this module may be disabled. A shared tile label alone is insufficient for a paired overlay.",
    page: "12 Per Tile Sequence Quality",
  },
  kmercontent: {
    measures:
      "Reported enriched k-mers, significance fields and observed/expected enrichment values, where available.",
    classification:
      "WARN and FAIL reflect FastQC's configured positional k-mer bias tests. PASS does not establish an absence of all sequence bias.",
    context:
      "Random priming or individual enriched sequences may create positional patterns.",
    caution:
      "This optional module may be disabled or unavailable. The chart shows reported maximum enrichment, not a reconstructed positional profile.",
    page: "11 Kmer Content",
  },
};

export function moduleHelp(name: string) {
  const entry = help[moduleKey(name)];
  return (
    entry && {
      ...entry,
      source: `https://www.bioinformatics.babraham.ac.uk/projects/fastqc/Help/3%20Analysis%20Modules/${encodeURIComponent(entry.page)}.html`,
    }
  );
}
