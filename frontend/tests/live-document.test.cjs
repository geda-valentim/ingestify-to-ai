const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const source = fs.readFileSync(path.join(__dirname, "../lib/live-document.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const scope = { exports: {}, Promise, Math, Map, Array, Error };
vm.runInNewContext(compiled, scope);
const { pageState, buildSlots, countStates, isFetchable, createLimiter, trailSegments, reuseSlots } = scope.exports;

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
assert.deepEqual({ ...countStates(slots) }, { done: 1, converting: 1, queued: 3, failed: 0, skipped: 0 });
assert.equal(isFetchable(slots[0]), true);
assert.equal(isFetchable(slots[2]), false);
assert.equal(isFetchable({ state: "done", job_id: null }), true); // fetched by page number

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

// Settled jobs: pages the poll left behind
const lag = [
  { page_number: 1, job_id: "a", status: "completed" },
  { page_number: 2, job_id: "b", status: "processing" },
  { page_number: 3, job_id: "c", status: "failed" },
  { page_number: 4, job_id: "d", status: "pending" },
];
assert.deepEqual(Array.from(buildSlots(lag, 4, "completed"), (x) => x.state), ["done", "done", "failed", "done"]);
assert.deepEqual(Array.from(buildSlots(lag, 4, "partial"), (x) => x.state), ["done", "skipped", "failed", "skipped"]);
assert.deepEqual(Array.from(buildSlots(lag, 4, "cancelled"), (x) => x.state), ["done", "skipped", "failed", "skipped"]);
assert.deepEqual(Array.from(buildSlots(lag, 4, "processing"), (x) => x.state), ["done", "converting", "failed", "queued"]);
assert.equal(pageState("processing", "failed"), "skipped");
assert.equal(isFetchable(buildSlots([], 2, "completed")[0]), true);
assert.deepEqual(Array.from(trailSegments(buildSlots(lag, 4, "partial"), 10), (x) => x.state), ["done", "skipped", "failed", "skipped"]);
assert.equal(countStates(buildSlots(lag, 4, "partial")).skipped, 2);
// Slots beyond total are kept (total 2, page 4 listed)
assert.equal(buildSlots(lag, 2).length, 4);

// reuseSlots keeps identity of unchanged slots
const a1 = buildSlots(lag, 4);
const a2 = buildSlots(lag, 4);
assert.equal(reuseSlots(a1, a2), a1);
const changed = buildSlots([{ ...lag[0] }, { ...lag[1], status: "completed" }, lag[2], lag[3]], 4);
const mergedSlots = reuseSlots(a1, changed);
assert.notEqual(mergedSlots, a1);
assert.equal(mergedSlots[0], a1[0]);
assert.notEqual(mergedSlots[1], a1[1]);

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

  // Start order: FIFO by default, newest first with lifo; one slot makes it visible
  async function order(options) {
    const run = createLimiter(1, options);
    const started = [];
    let release;
    const gate = new Promise((r) => (release = r));
    const all = [run(() => gate)];
    for (const n of [1, 2, 3]) all.push(run(async () => started.push(n)));
    release();
    await Promise.all(all);
    return started;
  }
  assert.deepEqual(await order({}), [1, 2, 3]);
  assert.deepEqual(await order({ lifo: true }), [3, 2, 1]);

  // An aborted task leaves the queue and never runs; one aborted before queueing rejects
  const run2 = createLimiter(1);
  let release2;
  const gate2 = new Promise((r) => (release2 = r));
  const first = run2(() => gate2);
  const ctl = new AbortController();
  let ran = false;
  const waiting = run2(async () => (ran = true), ctl.signal);
  ctl.abort();
  await assert.rejects(waiting, { name: "AbortError" });
  release2();
  await first;
  assert.equal(ran, false);
  await assert.rejects(run2(async () => 1, ctl.signal), { name: "AbortError" });
  assert.equal(await run2(async () => 2), 2);
  console.log("live-document tests passed");
})();
