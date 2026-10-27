const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

// Spec 0007 CA2: desired / alive / model-ready replicas per feature.
const source = fs.readFileSync(path.join(__dirname, "../lib/engine-replicas.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const scope = { exports: {} };
vm.runInNewContext(compiled, scope);
const { featureReplicas } = scope.exports;

// The vm realm has its own Array/Object: round-trip before comparing.
const rows = (s) => JSON.parse(JSON.stringify(featureReplicas(s)));
const rev = (feature, revision, desired_replicas) => ({
  feature,
  revision,
  profile: { desired_replicas },
});

assert.deepEqual(rows(undefined), []);
assert.deepEqual(rows({ desired: {}, applied: [], resources: [] }), []);

// Profile saved, nothing observed yet: desired shown, counts unknown (not 0).
assert.deepEqual(
  rows({ desired: { transcription: rev("transcription", 2, 3) }, applied: [], resources: [] }),
  [
    {
      feature: "transcription",
      desiredRevision: 2,
      desired: 3,
      alive: null,
      ready: null,
      observedAt: null,
    },
  ],
);

// Shared worker: each feature takes only the resources last applied for it,
// and the newest observation wins.
const status = {
  desired: {
    transcription: rev("transcription", 4, 3),
    vision: rev("vision", 1, 1),
  },
  applied: [],
  resources: [
    {
      key: "local:h:service:audio",
      applied: { feature: "transcription" },
      observed_at: "2026-10-27T10:00:00",
      observed: { replicas_alive: 1, ready_replicas: 0 },
    },
    {
      key: "local:h:service:worker",
      applied: { feature: "transcription" },
      observed_at: "2026-10-27T11:00:00",
      observed: { replicas_alive: 2, ready_replicas: 1 },
    },
    {
      key: "local:h:gpu:x",
      applied: { feature: "vision" },
      observed_at: "2026-10-27T09:00:00",
      observed: { replicas_alive: "?" },
    },
    { key: "modal:x", applied: null, observed_at: null, observed: {} },
  ],
};
assert.deepEqual(rows(status), [
  {
    feature: "transcription",
    desiredRevision: 4,
    desired: 3,
    alive: 2,
    ready: 1,
    observedAt: "2026-10-27T11:00:00",
  },
  {
    feature: "vision",
    desiredRevision: 1,
    desired: 1,
    alive: null,
    ready: null,
    observedAt: "2026-10-27T09:00:00",
  },
]);
