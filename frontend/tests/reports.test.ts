import assert from "node:assert/strict";
import test from "node:test";
import { htmlReports, previewPath } from "../src/reports.ts";

test("only HTML reports are previewed and MultiQC is preferred without mutating history", () => {
  const paths = [
    "fastqc/pilot_fastqc.html",
    "analysis.log",
    "multiqc/multiqc_report.html",
    "inputs/0/fastqc_report.html",
    "metrics.json",
    "fastqc/pilot_fastqc.zip",
  ];
  const reports = paths.map((path) => ({ path, size: 123 }));
  assert.deepEqual(
    htmlReports(reports).map((report) => report.path),
    [paths[2], paths[0], paths[3]],
  );
  assert.deepEqual(
    reports.map((report) => report.path),
    paths,
  );
  assert.deepEqual(htmlReports([]), []);
  assert.deepEqual(htmlReports([{ path: "only.zip", size: 1 }]), []);
});

test("preview query escapes paths and names and stays relative to the proxy prefix", () => {
  const path = "fastqc/<img onerror=alert(1)> #&?_fastqc.html";
  const relative = previewPath("id&other=run", path);
  const target = new URL(relative, "https://qc.example/node/compute/8765/");
  assert.equal(target.pathname, "/node/compute/8765/api/report-preview");
  assert.equal(target.searchParams.get("run_id"), "id&other=run");
  assert.equal(target.searchParams.get("path"), path);
  assert.equal([...target.searchParams].length, 2);
  assert.ok(!relative.includes("<img"));
});

test("NanoPlot combined report precedes individual original plot HTML", () => {
  const paths = [
    "qc/id/LengthvsQualityScatterPlot_dot.html",
    "qc/id/NanoPlot-report.html",
    "qc/id/NanoStats.txt",
  ];
  assert.deepEqual(
    htmlReports(paths.map((path) => ({ path, size: 100 }))).map((r) => r.path),
    [paths[1], paths[0]],
  );
  assert.equal(
    htmlReports([
      ...paths.map((path) => ({ path, size: 100 })),
      { path: "multiqc/multiqc_report.html", size: 100 },
    ])[0].path,
    "multiqc/multiqc_report.html",
  );
});
