const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

// formatApiError takes `unknown` and narrows it: same messages as before.
const source = fs.readFileSync(path.join(__dirname, "../lib/utils.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const scope = { exports: {}, require };
vm.runInNewContext(compiled, scope);
const { formatApiError } = scope.exports;

const withDetail = (detail) => ({ response: { data: { detail } } });

assert.equal(formatApiError(withDetail("Job not found")), "Job not found");
assert.equal(
  formatApiError(
    withDetail([
      { loc: ["body", "email"], msg: "invalid email" },
      { loc: ["body"], msg: "missing field" },
      "not an object",
    ]),
  ),
  "email: invalid email, field: missing field, field: undefined",
);
assert.equal(
  formatApiError(withDetail({ code: "QUOTA", message: "Quota exceeded" })),
  "Quota exceeded",
);
assert.equal(formatApiError(withDetail({ code: "X" })), '{"code":"X"}');
assert.equal(formatApiError(new Error("Network down")), "Network down");
assert.equal(formatApiError({ message: "" }), "An error occurred");
assert.equal(formatApiError(null), "An error occurred");
assert.equal(formatApiError(undefined, "Falhou"), "Falhou");
assert.equal(formatApiError("boom"), "An error occurred");
assert.equal(formatApiError({ response: { data: null } }), "An error occurred");
