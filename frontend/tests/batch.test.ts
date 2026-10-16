import assert from "node:assert/strict";
import test from "node:test";
import { selectCohortRows, batchActive, stageLabel } from "../src/batch.ts";

test("cohort uses explicit stable identities, distinct from display labels", () => {
  const ids = ["smp_same-name-1"];
  assert.deepEqual(selectCohortRows(ids, ["smp_same-name-2"]), [
    ...ids,
    "smp_same-name-2",
  ]);
  assert.equal(selectCohortRows(ids, [ids[0]]), ids);
  assert.equal(selectCohortRows(ids, []), ids);
  assert.deepEqual(selectCohortRows(["smp_1", "smp_2"], ["smp_2", "smp_3"]), [
    "smp_1",
    "smp_2",
    "smp_3",
  ]);
  const nearLimit = Array.from({ length: 99 }, (_, index) => `smp_${index}`);
  assert.throws(
    () => selectCohortRows(nearLimit, ["new_1", "new_2"]),
    /at most 100/,
  );
  assert.equal(nearLimit.length, 99); // A full page is never silently truncated.

  assert.throws(
    () =>
      selectCohortRows(
        Array.from({ length: 100 }, (_, i) => `smp_${i}`),
        ["smp_new"],
      ),
    /at most 100/,
  );
});
test("batch statuses preserve unknown, skipped, reuse and actual validation result", () => {
  assert.equal(stageLabel({ state: "not_evaluated" }), "not evaluated");
  assert.equal(
    stageLabel({ state: "completed", reused: true, result: "passed" }),
    "completed · reused · passed",
  );
  assert.equal(
    stageLabel({ state: "completed", validation_result: "not_evaluated" }),
    "completed · target not evaluated",
  );
  assert.equal(
    stageLabel({ state: "skipped", reason: "not requested" }),
    "skipped",
  );
  assert(batchActive("running"));
  assert(batchActive("queued"));
  for (const state of [
    "completed",
    "failed",
    "partial",
    "cancelled",
    "interrupted",
  ])
    assert(!batchActive(state));
});
