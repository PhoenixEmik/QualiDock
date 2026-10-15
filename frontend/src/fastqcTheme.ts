import { moduleKey } from "./qc.ts";
import type { Module } from "./types";

/** Scientific meanings are independent of the application's CSS accent. */
export const fastqcColors = {
  quality: {
    poor: "#F9DEDE",
    reasonable: "#FFF0C9",
    good: "#DDF2DF",
    box: "#F0F000",
    median: "#C80000",
    whisker: "#333333",
    mean: "#0000C8",
  },
  bases: { A: "#2CA02C", C: "#1F77B4", G: "#444444", T: "#D62728" } as Record<
    string,
    string
  >,
  observed: "#D62728",
  theoretical: "#1F77B4",
  reads: ["#1F77B4", "#D97706"],
  // FastQC 0.13.0's general line palette (Tol). Nucleotides/GC use explicit semantics.
  profiles: [
    "#882255",
    "#332288",
    "#117733",
    "#DDCC77",
    "#44AA99",
    "#AA4499",
    "#CC6677",
    "#88CCEE",
  ],
  // Negative tile deviations are warm; no decrease is blue, as in FastQC.
  tile: ["#C80000", "#C8C800", "#00C800", "#00C8C8", "#0000C8"],
  chrome: {
    text: "#475467",
    grid: "#E2E5E9",
    axis: "#98A2B3",
    zoomBackground: "#F1F3F6",
    zoomFill: "#DFE5ED",
    zoomLine: "#8292A7",
    zoomArea: "#D6DEE8",
  },
};

export const isTheoretical = (column: string) => /theoretical/i.test(column);
export const gcReferenceUnavailable = (module: Module) =>
  moduleKey(module.name) === "persequencegccontent" &&
  !module.columns.some(isTheoretical);
export const gcReferenceNote =
  "Only the observed GC distribution was reported in the saved data. The theoretical distribution is unavailable here; use the official report as a reference. No model is calculated.";

export function scientificColor(metric: string, column: string, index: number) {
  const key = moduleKey(metric);
  if (key === "perbasesequencecontent" && fastqcColors.bases[column])
    return fastqcColors.bases[column];
  if (key === "persequencegccontent") {
    if (isTheoretical(column)) return fastqcColors.theoretical;
    if (/^(count|observed(?: distribution| gc count)?)$/i.test(column))
      return fastqcColors.observed;
  }
  return fastqcColors.profiles[index % fastqcColors.profiles.length];
}

export function scientificLabel(metric: string, column: string) {
  return moduleKey(metric) === "persequencegccontent" && column === "Count"
    ? "Observed GC count"
    : column;
}
