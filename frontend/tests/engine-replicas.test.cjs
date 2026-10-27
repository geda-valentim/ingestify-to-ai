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
const { featureReplicas, appliedLabel, unattributedBusy } = scope.exports;

// The vm realm has its own Array/Object: round-trip before comparing.
const rows = (s) => JSON.parse(JSON.stringify(featureReplicas(s)));
const rev = (feature, revision, desired_replicas, applied_at = null) => ({
  feature,
  revision,
  profile: { desired_replicas },
  applied_at,
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
  applied: [
    rev("transcription", 4, 1, "2026-10-27T08:00:00"),
    rev("vision", 1, 1, "2026-10-27T07:00:00"),
    rev("transcription", 3, 1, "2026-10-27T06:00:00"),
  ],
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

const one = (status) => rows(status)[0];
const audio = (mode, observed_at = "2026-10-27T12:00:00") =>
  resource(
    "local:h:service:audio",
    { feature: "transcription", feature_modes: { transcription: mode } },
    observed_at,
    { replicas_alive: 0, ready_replicas: 0 },
  );

// Drained on purpose: desired stays the saved count, the mode is applied state.
const stopped = one({
  desired: { transcription: rev("transcription", 4, 3) },
  applied: [rev("transcription", 4, 3, "2026-10-27T11:00:00")],
  resources: [audio("stopped")],
});
assert.equal(stopped.desired, 3);
assert.equal(stopped.appliedRevision, 4);
assert.equal(stopped.mode, "stopped");
assert.equal(stopped.alive, 0);

// A newer revision saved after the stop: the stop stays visible.
const pending = one({
  desired: { transcription: rev("transcription", 5, 3) },
  applied: [rev("transcription", 4, 3, "2026-10-27T11:00:00")],
  resources: [audio("standby")],
});
assert.equal(pending.desired, 3);
assert.equal(pending.appliedRevision, 4);
assert.equal(pending.mode, "standby");

// Rollback: revision 2 applied after revision 3 is the one in force.
const rollback = one({
  desired: { transcription: rev("transcription", 3, 2) },
  applied: [
    rev("transcription", 3, 2, "2026-10-27T09:00:00"),
    rev("transcription", 2, 1, "2026-10-27T10:00:00"),
  ],
  resources: [audio("running")],
});
assert.equal(rollback.appliedRevision, 2);

// The mode of the feature's own resource wins over a stale shared one.
const own = one({
  desired: { transcription: rev("transcription", 1, 1) },
  applied: [rev("transcription", 1, 1, "2026-10-27T09:00:00")],
  resources: [
    audio("running", "2026-10-27T09:00:00"),
    resource(
      "local:old:service:worker",
      { feature: "vision", feature_modes: { transcription: "stopped" } },
      "2026-10-27T13:00:00",
      {},
    ),
  ],
});
assert.equal(own.mode, "running");

// Applied revision hidden by IAM: unknown revision, mode still known.
const hidden = one({
  desired: { transcription: rev("transcription", 1, 1) },
  applied: [],
  resources: [audio("stopped")],
});
assert.equal(hidden.appliedRevision, null);
assert.equal(hidden.mode, "stopped");

// The applied column always says what is in force, including a stop.
assert.equal(appliedLabel(stopped), "revisão 4 (parada)");
assert.equal(appliedLabel(pending), "revisão 4 (standby) · revisão 5 salva, não aplicada");
assert.equal(appliedLabel(rollback), "revisão 2 · revisão 3 salva, não aplicada");
assert.equal(appliedLabel(hidden), "não visível (parada)");
assert.equal(
  appliedLabel(rows({ desired: { vision: rev("vision", 1, 1) }, applied: [], resources: [] })[0]),
  "nenhuma · revisão 1 salva, não aplicada",
);

// First operation of a feature: the locked resource has no applied state, so
// no row can claim it, but the engine-level flag must show it.
const first = {
  desired: { transcription: rev("transcription", 1, 1) },
  applied: [],
  resources: [resource("local:h:service:audio", {}, null, {}, "op-9")],
};
assert.equal(one(first).busy, false);
assert.equal(unattributedBusy(first), true);
assert.equal(unattributedBusy(status), false); // op-1 belongs to vision's resource
assert.equal(unattributedBusy(undefined), false);
assert.equal(
  unattributedBusy({ ...first, resources: [resource("local:h:service:audio", null, null, {})] }),
  false,
);
