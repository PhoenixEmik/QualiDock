import test from "node:test";
import assert from "node:assert/strict";
import { policyDefinition } from "../src/release.ts";

test("release policy requires explicit assay/version and cannot omit source integrity", () => {
  assert.throws(() => policyDefinition("1", "", [], {}), /explicit/);
  const policy = policyDefinition(
    "Contract 2",
    "RNA-seq project",
    ["quantity"],
    { "Per sequence GC content": "pass,warn", "Adapter Content": "" },
  );
  assert.deepEqual(policy.required_checks, ["integrity", "quantity"]);
  assert.deepEqual(policy.fastqc_rules, [
    { module: "Per sequence GC content", allowed_statuses: ["pass", "warn"] },
  ]);
  assert.equal(policy.version, "Contract 2");
});
