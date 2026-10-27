const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

// Spec 0007 CA2: desired / applied / observed replicas per feature.
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
const resource = (key, applied, observed_at, observed, operation_id = null) => ({
  key,
  maintenance: false,
  operation_id,
  applied,
  observed_at,
  observed,
});

assert.deepEqual(rows(undefined), []);
assert.deepEqual(rows({ desired: {}, applied: [], resources: [] }), []);

// Profile saved, never applied nor observed: counts unknown (not 0).
assert.deepEqual(
  rows({ desired: { transcription: rev("transcription", 2, 3) }, applied: [], resources: [] }),
  [
    {
      feature: "transcription",
      desiredRevision: 2,
      desired: 3,
      appliedRevision: null,
      mode: null,
      busy: false,
      alive: null,
      ready: null,
      observedAt: null,
    },
  ],
);

// Shared worker: each feature takes only the resources last applied for it,
// the newest observation wins, and applied is the newest applied revision.
const status = {
  desired: {
    transcription: rev("transcription", 5, 3),
    vision: rev("vision", 1, 1),
  },
  // Ordered by revision, newest first, as the API returns it.
  applied: [rev("transcription", 4, 1), rev("vision", 1, 1), rev("transcription", 3, 1)],
  resources: [
    resource(
      "local:h:service:audio",
      { feature: "transcription", feature_modes: { transcription: "running" } },
      "2026-10-27T10:00:00",
      { replicas_alive: 1, ready_replicas: 0 },
    ),
    resource(
      "local:h:service:worker",
      { feature: "transcription", feature_modes: { transcription: "running", vision: "running" } },
      "2026-10-27T11:00:00",
      { replicas_alive: 2, ready_replicas: 1 },
    ),
    resource(
      "local:h:gpu:x",
      { feature: "vision", feature_modes: { vision: "running" } },
      "2026-10-27T09:00:00",
      { replicas_alive: "?" },
      "op-1",
    ),
    resource("modal:x", null, null, {}),
  ],
};
assert.deepEqual(rows(status), [
  {
    feature: "transcription",
    desiredRevision: 5,
    desired: 3,
    appliedRevision: 4,
    mode: "running",
    busy: false,
    alive: 2,
    ready: 1,
    observedAt: "2026-10-27T11:00:00",
  },
  {
    feature: "vision",
    desiredRevision: 1,
    desired: 1,
    appliedRevision: 1,
    mode: "running",
    busy: true,
    alive: null,
    ready: null,
    observedAt: "2026-10-27T09:00:00",
  },
]);

// Drained on purpose: the applied revision is current and its mode is
// stopped, so desired is not the profile's count.
const stopped = rows({
  desired: { transcription: rev("transcription", 4, 3) },
  applied: [rev("transcription", 4, 3)],
  resources: [
    resource(
      "local:h:service:audio",
      { feature: "transcription", feature_modes: { transcription: "stopped" } },
      "2026-10-27T12:00:00",
      { replicas_alive: 0, ready_replicas: 0 },
    ),
  ],
})[0];
assert.equal(stopped.desired, null);
assert.equal(stopped.mode, "stopped");
assert.equal(stopped.alive, 0);

// A newer revision saved after the stop is a pending desire, not "stopped".
const pending = rows({
  desired: { transcription: rev("transcription", 5, 3) },
  applied: [rev("transcription", 4, 3)],
  resources: [
    resource(
      "local:h:service:audio",
      { feature: "transcription", feature_modes: { transcription: "standby" } },
      "2026-10-27T12:00:00",
      { replicas_alive: 0, ready_replicas: 0 },
    ),
  ],
})[0];
assert.equal(pending.desired, 3);
assert.equal(pending.appliedRevision, 4);
