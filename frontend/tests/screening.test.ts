import test from "node:test";
import assert from "node:assert/strict";
import { taxonomyIds } from "../src/screening.ts";
import { exportModule } from "../src/rawExport.ts";

test("screening taxonomy annotations are explicit IDs, not inferred sample identities", () => {
  assert.deepEqual(taxonomyIds("4932, 9606 4932"), ["4932", "9606"]);
  assert.deepEqual(taxonomyIds(""), []);
  for (const text of ["human", "-1", "1;touch marker", "0.5"])
    assert.throws(() => taxonomyIds(text), /explicit decimal/);
});
test("generic source-table export keeps Kraken2 lexical values and spreadsheet protection", () => {
  const table = {
    columns: ["Reported percent", "Taxon"],
    rows: [
      ["  4.77", "=untrusted taxon"],
      ["0.00", "unclassified"],
    ],
  };
  assert.match(
    exportModule(table, "\t", "verbatim"),
    /  4\.77\t=untrusted taxon/,
  );
  assert.match(
    exportModule(table, "\t", "spreadsheet"),
    /"\t=untrusted taxon"/,
  );
  assert.match(exportModule(table, "\t", "spreadsheet"), /0\.00\tunclassified/);
});
