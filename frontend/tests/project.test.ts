import test from "node:test";
import assert from "node:assert/strict";
import { assignmentsFor, declaredMinimum, entityLabel } from "../src/project.ts";
import type { ProjectEntity, ProjectFile } from "../src/project.ts";

test("declared expected yield distinguishes absent and zero, with explicit exact units", () => {
  assert.equal(declaredMinimum("reads", ""), null);
  assert.deepEqual(declaredMinimum("read_pairs", "0"), { metric: "read_pairs", minimum: 0 });
  assert.deepEqual(declaredMinimum("bases", "9007199254740991"), { metric: "bases", minimum: Number.MAX_SAFE_INTEGER });
  for (const value of ["1.5", "1e6", "-1", "9007199254740992", "=1+1"]) assert.throws(() => declaredMinimum("reads", value));
  assert.throws(() => declaredMinimum("Q30", "10"));
});
test("same-named project sample declarations keep distinct stable IDs", () => {
  const first = { id: "smp_aaaaaaaa", declared: { display_name: "S1" } } as ProjectEntity;
  const second = { ...first, id: "smp_bbbbbbbb" };
  assert.notEqual(entityLabel(first), entityLabel(second));
  assert.match(entityLabel(first), /S1.*aaaaaaaa/);
});
test("explicit file assignments preserve lane chunk and read identities without name inference", () => {
  const file: ProjectFile = { file_id: "i_exact", filename: "unusual name ; $(nothing).fastq", report_id: "report-exact", lane: "L002", chunk: "003", read: "R2", input_available: true };
  assert.deepEqual(assignmentsFor([file], "smp_explicit", "seq_explicit"), [{ file_id: "i_exact", sample_id: "smp_explicit", sequencing_run_id: "seq_explicit", lane: "L002", chunk: "003", read: "R2", source: "user_confirmed" }]);
  assert.throws(() => assignmentsFor([file], "", "seq_explicit"));
  assert.throws(() => assignmentsFor([file, file], "smp_explicit", "seq_explicit"));
});
