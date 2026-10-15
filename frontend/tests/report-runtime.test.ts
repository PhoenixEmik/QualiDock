import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

// Test the exact bootstrap served by Python, not a parallel JS implementation.
const source = readFileSync(
  new URL("../../backend/qualidock/preview.py", import.meta.url),
  "utf8",
);
const bootstrap = source.match(
  /MEMORY_STORAGE_BOOTSTRAP = b'''<script[^>]*>([\s\S]*?)<\/script>'''/,
)![1];
function isolatedFrame() {
  const window: Record<string, any> = {},
    document: Record<string, any> = {};
  const denied = () => {
    throw new DOMException("Opaque origin", "SecurityError");
  };
  for (const name of ["localStorage", "sessionStorage"])
    Object.defineProperty(window, name, { get: denied, configurable: true });
  Object.defineProperty(document, "cookie", {
    get: denied,
    set: denied,
    configurable: true,
  });
  runInNewContext(bootstrap, { window, document, DOMException });
  return { window, document };
}
test("sandbox compatibility gives MultiQC private temporary storage without browser storage or cookies", () => {
  const { window, document } = isolatedFrame();
  const local = window.localStorage,
    session = window.sessionStorage;
  assert.equal(local.getItem("qualidock-cookie-canary"), null);
  local.setItem("mqc-theme", "dark");
  assert.equal(local.getItem("mqc-theme"), "dark");
  assert.equal(local.length, 1);
  assert.equal(local.key(0), "mqc-theme");
  assert.equal(local.key(-1), null);
  assert.equal(session.getItem("mqc-theme"), null);
  local.setItem("zero", 0);
  assert.equal(local.getItem("zero"), "0");
  local.removeItem("zero");
  assert.equal(local.length, 1);
  assert.equal(document.cookie, "");
  document.cookie = "qualidock=must-not-persist";
  assert.equal(document.cookie, "");
  local.clear();
  assert.equal(local.length, 0);
});
test("report state is not shared with another frame or retained after reload", () => {
  const first = isolatedFrame(),
    reloaded = isolatedFrame();
  first.window.localStorage.setItem("mqc-theme", "dark");
  first.window.sessionStorage.setItem("sample", "R1");
  assert.equal(reloaded.window.localStorage.getItem("mqc-theme"), null);
  assert.equal(reloaded.window.sessionStorage.getItem("sample"), null);
});
test("temporary report storage has a bounded quota and does not overwrite an existing browser API", () => {
  const { window } = isolatedFrame();
  assert.throws(
    () => window.localStorage.setItem("too-large", "x".repeat(1024 * 1024)),
    { name: "QuotaExceededError" },
  );
  assert.equal(window.localStorage.length, 0);
  const local = {},
    session = {},
    document = { cookie: "test-only" };
  const normal = { localStorage: local, sessionStorage: session };
  runInNewContext(bootstrap, { window: normal, document, DOMException });
  assert.equal(normal.localStorage, local);
  assert.equal(normal.sessionStorage, session);
  assert.equal(document.cookie, "test-only");
});
