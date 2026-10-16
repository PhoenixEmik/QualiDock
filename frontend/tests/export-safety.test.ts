import test from "node:test";
import assert from "node:assert/strict";
import { exportModule } from "../src/rawExport.ts";
import { statsExport, sourceExport } from "../src/analytics.ts";

test("spreadsheet exports quote and prefix formula-like or control-obfuscated text", () => {
  const texts = [
    '=HYPERLINK("https://example.invalid","click")',
    "+SUM(1,2)",
    "-cmd|value",
    "@SUM(A1:A2)",
    " \t\r\n=1+1",
    "\u200b＝1+1",
    "\tplain",
    "\n+SUM(1,2)",
    "＝SUM(1,2)",
    "＠A1",
    '"quoted",text',
  ];
  const module = {
    name: "Safety",
    status: "",
    columns: ["=unsafe header"],
    rows: texts.map((value) => [value]),
  };
  for (const delimiter of [",", "\t"] as const) {
    const safe = exportModule(module, delimiter, "spreadsheet");
    for (const value of texts.slice(0, -1))
      assert.ok(
        safe.includes('"\t' + value.replaceAll('"', '""') + '"'),
        value,
      );
    assert.ok(safe.startsWith('"\t=unsafe header"\r\n'));
    assert.ok(
      exportModule(module, delimiter, "verbatim").includes(
        '"' + texts[0].replaceAll('"', '""') + '"',
      ),
    );
  }
});
test("spreadsheet export preserves zero, blanks, negatives, exponents and precision exactly", () => {
  const values = [
    "0",
    "",
    "-0.0000000000001234",
    "+1.25",
    "-1e-12",
    "35.115500000000004",
  ];
  const module = {
    name: "Numbers",
    status: "",
    columns: ["Value"],
    rows: values.map((v) => [v]),
  };
  assert.equal(
    exportModule(module, ",", "spreadsheet"),
    exportModule(module, ",", "verbatim"),
  );
});
test("analytics exports apply the same explicit mode to sample names without changing metrics", () => {
  const rows = [{ sample: '=HYPERLINK("bad")', values: { count: -12.5 } }];
  const columns = [
    {
      key: "count",
      raw_key: "count",
      title: "Count",
      namespace: "FastQC",
      unit: "",
      description: "",
    },
  ];
  assert.ok(
    statsExport(rows, columns, ",", "spreadsheet").includes(
      '"\t=HYPERLINK(""bad"")",-12.5',
    ),
  );
  assert.ok(!statsExport(rows, columns, ",", "verbatim").includes("\t="));
  const entity = {
    analysisId: "analysis",
    id: "report",
    name: "@sample",
    source: "/data/read.fastq",
    tool: "FastQC",
    version: "0.13.0",
    fastqc: {
      modules: [
        {
          name: "Per base N content",
          status: "pass",
          columns: ["Base", "N-Count"],
          rows: [["1", "-0.001"]],
        },
      ],
    },
  };
  assert.ok(
    sourceExport(
      [entity as never],
      "Per base N content",
      "\t",
      "spreadsheet",
    ).includes('"\t@sample"'),
  );
  assert.ok(
    sourceExport(
      [entity as never],
      "Per base N content",
      "\t",
      "spreadsheet",
    ).includes("-0.001"),
  );
});
