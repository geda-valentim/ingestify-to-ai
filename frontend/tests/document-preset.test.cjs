const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const source = fs.readFileSync(path.join(__dirname, "../lib/document-preset.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const scope = { exports: {} };
vm.runInNewContext(compiled, scope);
const { effectiveDoclingPreset } = scope.exports;

// an untouched form and an explicit "Fast" both send "fast"; never an absent preset
assert.equal(effectiveDoclingPreset(undefined), "fast");
assert.equal(effectiveDoclingPreset("fast"), "fast");
assert.equal(effectiveDoclingPreset("balanced"), "balanced");
assert.equal(effectiveDoclingPreset("quality"), "quality");
console.log("document-preset ok");
