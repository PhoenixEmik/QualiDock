import test from "node:test";
import assert from "node:assert/strict";
import { cohortMetrics, cohortPlot, pointLabel } from "../src/cohort.ts";
import type { CohortPoint, CohortResult } from "../src/cohort.ts";
import { selectCohortRows } from "../src/batch.ts";
import { overlayColors } from "../src/fastqcTheme.ts";

// Explicitly synthetic API records for chart/UI contracts, not scientific fixtures.
const point: CohortPoint = {
  id: "file-a",
  file_id: "i_a",
  filename: "A_L001_R1.fastq.gz",
  metric: "q30_percent",
  unit: "%",
  value: 0,
  raw_value: "0/60000",
  numerator: 0,
  denominator: 60000,
  reason: null,
  rule_result: "review",
  context: {
    project_id: "project-a",
    project_name: "Project A",
    sample_id: "sample-a",
    sample_name: "A",
    sequencing_run_id: "run-a",
    run_name: "Run A",
    platform: "Illumina",
    assay: "RNA-seq",
    library_type: "Declared",
    input_stage: "raw_fastq",
    sequenced_at: "2026-10-16",
    read: "R1",
    lane: "L001",
    chunk: "001",
  },
  sources: [
    {
      analysis_id: "analysis-a",
      file_id: "i_a",
      filename: "A_L001_R1.fastq.gz",
      report_id: "report-a",
      tools: { fastqc: "0.13.0" },
    },
  ],
};
const result = {
  metric: {
    id: "q30_percent",
    name: "Q30 bases",
    unit: "%",
    description: "Actual counted quality bases",
  },
  group_by: "file",
  points: [point],
  excluded: [],
  total: 1,
} as unknown as CohortResult;
test("cross-run charts preserve true zero, exact fraction, source identities and stage", () => {
  const view = cohortPlot(result);
  const options = view.options as any;
  assert.deepEqual(options.series[0].data, [0]);
  assert.equal(options.series[0].color, overlayColors[0]);
  assert.equal(options.yAxis.max, 100);
  assert.match(pointLabel(point), /Run A · A · L001 · 001 · R1 · A_L001_R1/);
  const tooltip = options.tooltip.formatter([{ dataIndex: 0, value: 0 }]);
  assert.match(tooltip, /0 \/ 60000 quality bases/);
  assert.match(tooltip, /raw_fastq/);
  assert.match(tooltip, /Review: below user-declared reference/);
  assert.equal(options.series[0].markArea, undefined); // No Phred bands on Q30 base percentages.
  assert.equal(options.tooltip.renderMode, "richText");
});
test("missing values excluded from chart, different run identities preserved despite same names", () => {
  const missing = { ...point, id: "missing", value: null };
  const mate = {
    ...point,
    id: "mate",
    value: 70,
    context: { ...point.context, sequencing_run_id: "run-b", read: "R2" },
  };
  const options = cohortPlot({ ...result, points: [point, mate, missing] })
    .options as any;
  assert.equal(options.xAxis.data.length, 2);
  assert.equal(options.series.length, 2);
  assert.deepEqual(options.series[0].data, [0, null]);
  assert.deepEqual(options.series[1].data, [null, 70]);
  assert.notEqual(options.series[0].name, options.series[1].name);
  assert.equal(
    (cohortPlot(result, new Set([point.id])).options as any).series.length,
    0,
  );
});
test("count charts have explicit units and bounded initial zoom for 100 synthetic records", () => {
  const points = Array.from({ length: 100 }, (_, i) => ({
    ...point,
    id: `synthetic-${i}`,
    value: i,
    unit: "reads",
  }));
  const options = cohortPlot({
    ...result,
    metric: { ...result.metric, id: "reads", unit: "reads" },
    points,
  }).options as any;
  assert.equal(options.yAxis.max, undefined);
  assert.equal(options.yAxis.name, "reads");
  assert.equal(options.dataZoom[0].end, 16);
  assert.equal(options.series[0].data.length, 100);
  assert.equal(cohortMetrics.length, 9);
});
test("shared checkbox selection supports bounded cross-project selection and deduplication", () => {
  assert.deepEqual(selectCohortRows(["p1"], ["p1", "p2"], 5), ["p1", "p2"]);
  assert.throws(
    () => selectCohortRows(["p1"], ["p2", "p3", "p4", "p5", "p6"], 5),
    /at most 5/,
  );
});
