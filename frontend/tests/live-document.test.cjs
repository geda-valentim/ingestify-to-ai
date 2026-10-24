const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const source = fs.readFileSync(path.join(__dirname, "../lib/live-document.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const scope = { exports: {}, Promise, Math, Map, Array };
vm.runInNewContext(compiled, scope);
const { pageState, buildSlots, countStates, isFetchable, createLimiter, trailSegments } = scope.exports;

assert.equal(pageState("completed"), "done");
assert.equal(pageState("processing"), "converting");
assert.equal(pageState("failed"), "failed");
assert.equal(pageState("pending"), "queued");
assert.equal(pageState(undefined), "queued");

// Slots follow page order, fill pages the API has not listed, keep the last duplicate
const slots = buildSlots(
  [
    { page_number: 3, job_id: "p3", status: "completed" },
    { page_number: 1, job_id: "p1", status: "completed" },
    { page_number: 3, job_id: "p3b", status: "processing" },
    { page_number: 2, job_id: null, status: "pending" },
  ],
  5,
);
assert.deepEqual(Array.from(slots, (s) => s.page_number), [1, 2, 3, 4, 5]);
assert.deepEqual(Array.from(slots, (s) => s.state), ["done", "queued", "converting", "queued", "queued"]);
assert.equal(slots[2].job_id, "p3b");
assert.equal(buildSlots([], 0).length, 0);
assert.equal(buildSlots([{ page_number: 7, job_id: "x", status: "completed" }], 3).length, 7);
assert.deepEqual({ ...countStates(slots) }, { done: 1, converting: 1, queued: 3, failed: 0 });
assert.equal(isFetchable(slots[0]), true);
assert.equal(isFetchable(slots[2]), false);
assert.equal(isFetchable({ state: "done", job_id: null }), false);

// Trail buckets
const many = buildSlots([], 1000);
assert.equal(trailSegments(many, 100).length, 100);
assert.equal(trailSegments(many, 100)[0].to, 10);
assert.equal(trailSegments(slots, 100).length, 5);
const mixed = buildSlots(
  [
    { page_number: 1, job_id: "a", status: "completed" },
    { page_number: 2, job_id: "b", status: "completed" },
    { page_number: 3, job_id: "c", status: "failed" },
    { page_number: 4, job_id: "d", status: "completed" },
  ],
  6,
);
assert.deepEqual(Array.from(trailSegments(mixed, 3), (s) => s.state), ["done", "failed", "queued"]);

// Limiter: never more than `limit` running, all tasks finish in order queued
(async () => {
  const run = createLimiter(4);
  let active = 0;
  let peak = 0;
  const results = await Promise.all(
    Array.from({ length: 20 }, (_, i) =>
      run(async () => {
        active += 1;
        peak = Math.max(peak, active);
        await new Promise((r) => setTimeout(r, 5));
        active -= 1;
        return i;
      }),
    ),
  );
  assert.equal(peak, 4);
  assert.deepEqual(results, Array.from({ length: 20 }, (_, i) => i));
  const failing = createLimiter(1);
  await assert.rejects(failing(() => Promise.reject(new Error("x"))));
  assert.equal(await failing(async () => 1), 1);
  console.log("live-document tests passed");
})();
