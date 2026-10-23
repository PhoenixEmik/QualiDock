import type { VariantMetrics } from "./types";
import type { NativePlotView } from "./AnalyticsChart";
import { overlayColors } from "./fastqcTheme.ts";

// Exact strings remain in tables/downloads. Do not graph rounded unsafe counts.
function bars(title: string, rows: string[][], columns: [string, number][]): NativePlotView | null {
  if (!rows.length || rows.some(r => columns.some(([, i]) => !/^[0-9]+$/.test(r[i] ?? "") || !Number.isSafeInteger(Number(r[i]))))) return null;
  const series = columns.map(([name]) => ({name, label: name}));
  return {description: title, summary: "Original BCFtools counts; categories are not combined", series,
    options: {animation: false, grid: {left: 65, right: 25, top: 50, bottom: 120},
      tooltip: {trigger: "axis", renderMode: "richText", confine: true},
      legend: {bottom: 0}, xAxis: {type: "category", data: rows.map(r => r[0]), name: "Reported category / bin", nameLocation: "middle", nameGap: 30},
      yAxis: {type: "value", min: 0, minInterval: 1, name: "Reported count"},
      dataZoom: [{type: "inside", filterMode: "none"}, {type: "slider", bottom: 45, height: 18, filterMode: "none"}],
      series: columns.map(([name, i], j) => ({name, type: "bar", data: rows.map(r => Number(r[i])), itemStyle: {color: overlayColors[j % overlayColors.length]}})),
    }};
}

export function variantViews(data: VariantMetrics) {
  const summary = new Map(data.summary.rows.map(([k, v]) => [k, v] as const));
  const composition = bars("Reported SNP / indel composition: overlapping record categories, not a partition of all records", ["SNPs", "MNPs", "indels", "others", "no-ALTs"].map(k => [k, summary.get(`number of ${k}:`) ?? ""]), [["Records in category", 1]]);
  const quality = data.quality_available && data.quality.chart_rows
    ? bars("Original QUAL distribution: first-ALT SNP substitutions and indels; missing QUAL is separate", data.quality.chart_rows.map(r => [r[0] === "." ? "Missing QUAL" : r[0], ...r.slice(1)]), [["SNPs (first ALT)", 1], ["Indels", 4]]) : null;
  const depthRows = data.depth.chart_rows?.filter(r => !r[0].startsWith("<"));
  const depthColumns: [string, number][] = [
    ...(data.site_depth_available ? [["Sites with reported INFO/DP", 3] as [string, number]] : []),
    ...(data.genotype_depth_available ? [["Genotypes with reported sample depth", 1] as [string, number]] : []),
  ];
  const depth = depthRows && depthColumns.length ? bars("Original depth bins: site and genotype observations have separate counting units", depthRows, depthColumns) : null;
  const tstv = bars("Original transition / transversion counts", [["Transitions", data.tstv.rows[0][0]], ["Transversions", data.tstv.rows[0][1]]], [["Substitutions", 1]]);
  return {composition, quality, depth, tstv};
}
