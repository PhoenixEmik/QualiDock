import test from "node:test";
import assert from "node:assert/strict";
import * as echarts from "echarts";
import type { Sample, Run, InputPairing, Module } from "../src/types.ts";
import { fixture } from "./fastqcFixture.ts";
import { confirmedPairs } from "../src/pairing.ts";
import {
  alignBins,
  compareModules,
  comparisonTooltip,
} from "../src/comparison.ts";
import { comparisonChartOptions } from "../src/comparisonChart.ts";
import { chartOptions } from "../src/chartOptions.ts";
import { exportModule, exportFilename } from "../src/rawExport.ts";
import {
  findModule,
  moduleStatus,
  supportedModules,
  rowTooltip,
} from "../src/qc.ts";
import { moduleHelp } from "../src/moduleNotes.ts";

const r1 = fixture("R1"),
  r2 = fixture("R2");
const metric = "Per base sequence quality";
const records: InputPairing[] = [r1, r2].map((sample, i) => ({
  path: `/reads/${sample.name}`,
  name: sample.name,
  read: i === 0 ? "R1" : "R2",
  paired: true,
  mate: `/reads/${i === 0 ? r2.name : r1.name}`,
  pair_key: "/reads/coverage",
}));
const run = {
  inputs: records.map((record) => record.path),
  input_pairing: records,
} as Run;
const changeModule = (
  sample: Sample,
  name: string,
  update: (module: Module) => Module,
): Sample => ({
  ...sample,
  modules: sample.modules.map((module) =>
    module.name === name ? update(module) : module,
  ),
});

test("confirmed mutual server pairing associates exact FastQC input filenames", () => {
  const pairs = confirmedPairs(run, [r2, r1]);
  assert.equal(pairs.length, 1);
  assert.equal(pairs[0].r1, r1);
  assert.equal(pairs[0].r2, r2);
  assert.equal(pairs[0].id, "/reads/coverage");
});
test("historical, single-end, missing, ambiguous, non-mutual and wrong-input pairs are not guessed", () => {
  assert.deepEqual(confirmedPairs({ inputs: run.inputs } as Run, [r1, r2]), []);
  assert.deepEqual(confirmedPairs(run, [r1]), []);
  for (const bad of [
    records.slice(0, 1),
    [...records, records[0]],
    records.map((record) => ({ ...record, paired: false })),
    records.map((record) => ({ ...record, read: "R1" })),
    records.map((record) => ({ ...record, mate: "/wrong/mate" })),
    records.map((record) => ({ ...record, path: "/different/" + record.name })),
  ])
    assert.deepEqual(
      confirmedPairs({ ...run, input_pairing: bad }, [r1, r2]),
      [],
    );
  assert.deepEqual(
    confirmedPairs(run, [r1, r2, { ...r2, id: "ambiguous-report.zip" }]),
    [],
  );
});
test("multiple sample/lane keys remain distinct, without combining statistical data", () => {
  const more = [r1, r2].map((sample) => ({
    ...sample,
    id: "lane2/" + sample.id,
    name: "lane2_" + sample.name,
    modules: sample.modules.map((module) =>
      module.name === "Basic Statistics"
        ? {
            ...module,
            rows: module.rows.map((row) =>
              row[0] === "Filename" ? [row[0], "lane2_" + sample.name] : row,
            ),
          }
        : module,
    ),
  }));
  const metadata = more.map((sample, i) => ({
    ...records[i],
    name: sample.name,
    path: "/reads/" + sample.name,
    mate: "/reads/" + more[1 - i].name,
    pair_key: "/reads/coverage_L002",
  }));
  const pairs = confirmedPairs(
    {
      ...run,
      inputs: [...run.inputs, ...metadata.map((record) => record.path)],
      input_pairing: [...records, ...metadata],
    },
    [r1, r2, ...more],
  );
  assert.equal(pairs.length, 2);
  assert.notEqual(pairs[0].id, pairs[1].id);
  assert.equal(pairs[1].r1, more[0]);
});
test("comparison means, optional medians and tooltip percentiles exactly match both actual reports", () => {
  const data = compareModules(r1, r2, metric, true);
  assert.equal(data.mode, "overlay");
  assert.equal(data.series.length, 4);
  for (const [index, sample] of [r1, r2].entries()) {
    const module = findModule(sample, metric)!;
    assert.deepEqual(
      data.series[index * 2].data,
      module.rows.map((row) => Number(row[1])),
    );
    assert.deepEqual(
      data.series[index * 2 + 1].data,
      module.rows.map((row) => Number(row[2])),
    );
    const bin = module.rows.findIndex((row) => row[0] === "20-24");
    for (const value of module.rows[bin])
      assert.ok(
        comparisonTooltip(data, bin, [r1.name, r2.name]).includes(value),
      );
  }
  assert.ok(data.categories.includes("10-14"));
  assert.ok(!data.categories.includes("10"));
});
test("single-read boxes use exact FastQC quantiles and omit incomplete boxes without inventing values", () => {
  const module = findModule(r1, metric)!;
  const series = chartOptions(r1, metric).series as { data: unknown[] }[];
  assert.deepEqual(
    series[0].data,
    module.rows.map((row) =>
      [row[5], row[3], row[2], row[4], row[6]].map(Number),
    ),
  );
  assert.deepEqual(
    series[1].data,
    module.rows.map((row) => Number(row[1])),
  );
  const missing = {
    ...r1,
    per_base_quality: r1.per_base_quality.map((bin, i) =>
      i === 0 ? { ...bin, percentile_10: null } : bin,
    ),
  };
  const data = chartOptions(missing, metric).series as { data: unknown[] }[];
  assert.ok((data[0].data[0] as number[]).every(Number.isNaN));
  assert.equal(data[1].data[0], Number(module.rows[0][1]));
  const chart = echarts.init(null, undefined, {
    renderer: "svg",
    ssr: true,
    width: 900,
    height: 400,
  });
  try {
    chart.setOption(chartOptions(missing, metric));
    assert.ok(!chart.renderToSVGString().includes("NaN"));
  } finally {
    chart.dispose();
  }
});
test("shorter reads retain exact unmatched bins with gaps, not zeros", () => {
  const short = changeModule(r2, metric, (module) => ({
    ...module,
    rows: module.rows.slice(0, -3),
  }));
  const data = compareModules(r1, short, metric);
  assert.equal(data.mode, "overlay");
  assert.deepEqual(
    data.categories,
    findModule(r1, metric)!.rows.map((row) => row[0]),
  );
  assert.deepEqual(data.series[1].data.slice(-3), [null, null, null]);
  assert.match(
    comparisonTooltip(data, data.categories.length - 1, [r1.name, r2.name]),
    /not reported/,
  );
});
test("overlapping different bins, repeated labels and incompatible axes never overlay", () => {
  assert.equal(alignBins(["1", "10-14"], ["1", "10-15"], true), null);
  assert.equal(alignBins(["1", "1"], ["1"], true), null);
  assert.equal(
    alignBins(["10-14"], ["10", "11", "12", "13", "14"], true),
    null,
  );
  const different = changeModule(r2, metric, (module) => ({
    ...module,
    rows: module.rows.map((row) =>
      row[0] === "10-14" ? ["10-15", ...row.slice(1)] : row,
    ),
  }));
  assert.equal(compareModules(r1, different, metric).mode, "separate");
  assert.equal(
    compareModules(r1, { ...r2, encoding: "different encoding" }, metric).mode,
    "separate",
  );
});
test("missing module/value/status remain unavailable without changing official WARN/FAIL", () => {
  const absent = {
    ...r2,
    modules: r2.modules.filter((module) => module.name !== metric),
  };
  assert.equal(compareModules(r1, absent, metric).mode, "separate");
  assert.equal(moduleStatus(absent, metric), "unavailable");
  const disabled = changeModule(r2, metric, (module) => ({
    ...module,
    available: false,
  }));
  assert.equal(moduleStatus(disabled, metric), "unavailable");
  const missing = changeModule(r2, metric, (module) => ({
    ...module,
    rows: module.rows.map((row, i) =>
      i === 0 ? [row[0], "", ...row.slice(2)] : row,
    ),
  }));
  assert.equal(compareModules(r1, missing, metric).series[1].data[0], null);
  assert.ok(
    rowTooltip(findModule(missing, metric)!, 0).includes(
      "Mean: Unavailable (blank)",
    ),
  );
  for (const module of r1.modules)
    assert.equal(moduleStatus(r1, module.name), module.summary_status);
  assert.ok(r1.modules.some((module) => module.status === "fail"));
  assert.ok(r1.modules.some((module) => module.status === "warn"));
});
test("adapter categories compare only shared names; incompatible sets are separate", () => {
  const adapter = "Adapter Content",
    module = findModule(r2, adapter)!;
  const subset = changeModule(r2, adapter, (module) => ({
    ...module,
    columns: module.columns.slice(0, -1),
    rows: module.rows.map((row) => row.slice(0, -1)),
  }));
  const data = compareModules(r1, subset, adapter);
  assert.equal(data.mode, "overlay");
  assert.ok(data.reason.includes(module.columns.at(-1)!));
  assert.ok(
    !data.series.some((series) => series.column === module.columns.at(-1)),
  );
  const incompatible = changeModule(r2, adapter, (module) => ({
    ...module,
    columns: module.columns.map((column, i) =>
      i ? "other-" + column : column,
    ),
  }));
  assert.equal(compareModules(r1, incompatible, adapter).mode, "separate");
});
test("non-comparable modules retain individual inspection with a reason", () => {
  for (const name of [
    "Basic Statistics",
    "Overrepresented sequences",
    "Per tile sequence quality",
    "Kmer Content",
  ])
    assert.ok(compareModules(r1, r2, name).reason);
});
test("every supported module has a reviewed, conservative explanatory note", () => {
  for (const name of supportedModules) {
    const help = moduleHelp(name)!;
    assert.ok(
      help.measures && help.classification && help.context && help.caution,
    );
    assert.ok(
      help.source.startsWith("https://www.bioinformatics.babraham.ac.uk/"),
    );
  }
  assert.equal(moduleHelp("New unreviewed module"), undefined);
});
for (const sample of [r1, r2])
  for (const module of sample.modules)
    test(`verbatim raw CSV/TSV fidelity: ${sample.name}: ${module.name}`, () => {
      assert.equal(
        exportModule(module, "\t"),
        [module.columns, ...module.rows]
          .map((row) => row.join("\t"))
          .join("\r\n") + "\r\n",
      );
      const quoted = (value: string) =>
        /[",\r\n]/.test(value)
          ? '"' + value.replaceAll('"', '""') + '"'
          : value;
      assert.equal(
        exportModule(module, ","),
        [module.columns, ...module.rows]
          .map((row) => row.map(quoted).join(","))
          .join("\r\n") + "\r\n",
      );
    });
test("exports preserve zero, blank, precision and escaped delimiters without formula rewriting", () => {
  const module = {
    name: "Unit edge cases",
    columns: ["Name", "Value"],
    status: "pass",
    rows: [
      ['a,"b"', "35.115500000000004"],
      ["tab\tnewline\n", "0"],
      ["=literal", ""],
    ],
  };
  assert.equal(
    exportModule(module, ","),
    'Name,Value\r\n"a,""b""",35.115500000000004\r\n"tab\tnewline\n",0\r\n=literal,\r\n',
  );
  assert.ok(exportModule(module, "\t").includes('"tab\tnewline\n"\t0'));
  assert.ok(
    !exportFilename("../../sample", "Adapter Content", "tsv").includes("/"),
  );
});
for (const name of [
  metric,
  "Per base sequence content",
  "Per base N content",
  "Adapter Content",
  "Per sequence GC content",
  "Per sequence quality scores",
  "Sequence Length Distribution",
  "Sequence Duplication Levels",
])
  test(`real paired chart data, units and finite SVG: ${name}`, () => {
    const option = comparisonChartOptions(r1, r2, name);
    const data = compareModules(r1, r2, name);
    assert.equal(data.mode, "overlay");
    assert.deepEqual(
      (option.series as { name: string; data: (number | null)[] }[])
        .filter((series) => series.name !== "Quality regions")
        .map((series) => series.data),
      data.series.map((series) => series.data),
    );
    for (const width of [350, 900]) {
      const chart = echarts.init(null, undefined, {
        renderer: "svg",
        ssr: true,
        width,
        height: 400,
      });
      try {
        chart.setOption(option);
        assert.ok(!chart.renderToSVGString().includes("NaN"));
        chart.dispatchAction({
          type: "legendUnSelect",
          name: data.series[0].name,
        });
        assert.equal(
          (
            chart.getOption().legend as { selected: Record<string, boolean> }[]
          )[0].selected[data.series[0].name],
          false,
        );
      } finally {
        chart.dispose();
      }
    }
  });
