// Relative URLs keep API, SSE, and downloads under both /node and /rnode proxies.
const base = new URL("./", window.location.href);
export const url = (path: string) =>
  new URL(path.replace(/^\//, ""), base).toString();
export class AuthError extends Error {}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(url(path), {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-QualiDock-Request": "1",
      ...options.headers,
    },
  });
  if (response.status === 401)
    throw new AuthError("Your session needs authentication.");
  if (!response.ok) {
    const text = await response.text();
    try {
      const data = JSON.parse(text);
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Check the analysis settings and try again.",
      );
    } catch (error) {
      if (error instanceof SyntaxError) throw new Error(text);
      throw error;
    }
  }
  return response.json();
}
export const isRnaQC = (mode: string) =>
  mode === "rseqc-infer" || mode === "rseqc-distribution" || mode === "rseqc-genebody";
export const isBamOnlyQC = (mode: string) => isRnaQC(mode) || mode === "picard" || mode === "picard-rna";
export const isAlignmentQC = (mode: string) =>
  mode === "samtools" || mode === "mosdepth" || isBamOnlyQC(mode);
export const modeLabel = (mode: string) =>
  mode === "bcftools"
    ? "BCFtools variant QC"
    : mode === "picard-rna"
    ? "Picard RNA-seq metrics"
    : mode === "rseqc-genebody"
    ? "RSeQC gene-body coverage"
    : mode === "picard"
    ? "Picard insert-size QC"
    : mode === "rseqc-infer"
      ? "RSeQC strandedness"
      : mode === "rseqc-distribution"
        ? "RSeQC read distribution"
        : mode === "mosdepth"
          ? "mosdepth coverage QC"
          : mode === "samtools"
            ? "SAMtools alignment QC"
            : mode === "nanoplot"
              ? "NanoPlot long-read QC"
              : mode === "fastq-screen"
                ? "FastQ Screen"
                : mode === "nanoq"
                  ? "nanoq long-read QC"
                  : mode === "fastp"
                    ? "fastp processing"
                    : mode === "seqkit-filter"
                      ? "Length filtering"
                      : mode === "seqkit-extract"
                        ? "Extract read identifiers"
                        : mode.startsWith("seqkit-")
                          ? `SeqKit ${mode.slice(7)}`
                          : mode === "both"
                            ? "FastQC + MultiQC"
                            : mode === "fastqc"
                              ? "FastQC only"
                              : "MultiQC only";
export const bytes = (value: number | null) =>
  value === null
    ? "—"
    : value < 1024
      ? `${value} B`
      : value < 1024 ** 2
        ? `${(value / 1024).toFixed(1)} KB`
        : value < 1024 ** 3
          ? `${(value / 1024 ** 2).toFixed(1)} MB`
          : `${(value / 1024 ** 3).toFixed(2)} GB`;
export const date = (value: string) =>
  new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
