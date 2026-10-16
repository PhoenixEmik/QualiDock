import test from "node:test";
import assert from "node:assert/strict";
import { configuredTargets, quantity } from "../src/delivery.ts";

test("delivery targets preserve zero, distinguish absent values and retain explicit units", () => {
  assert.deepEqual(
    configuredTargets({
      a: { metric: "read_pairs", minimum: "0" },
      b: { metric: "bases", minimum: "" },
    }),
    [{ sample_id: "a", metric: "read_pairs", minimum: 0 }],
  );
  assert.equal(quantity(null), "Not evaluated");
  assert.equal(quantity(0), "0");
  for (const minimum of ["-1", "1.5", "1e6", "9007199254740992", "=1+1"])
    assert.throws(
      () => configuredTargets({ a: { metric: "reads", minimum } }),
      /whole numbers/,
    );
});
