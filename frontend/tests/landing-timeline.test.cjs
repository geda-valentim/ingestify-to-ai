const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname, '../components/landing/timeline.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const scope = { exports: {} }; vm.runInNewContext(compiled, scope);
const { timelineAt, chapterProgress } = scope.exports;
// The complete forward and reverse walk must be deterministic and monotonic.
let previous = -1;
for (let step = 0; step <= 10000; step++) {
  const current = timelineAt(step / 10000);
  assert(current.time >= previous);
  assert(current.chapter >= 0 && current.chapter < 8);
  previous = current.time;
}
for (let step = 10000; step >= 0; step--) {
  const current = timelineAt(step / 10000);
  assert(current.time <= previous); previous = current.time;
}
for (let chapter = 0; chapter < 8; chapter++) {
  const state = timelineAt(chapterProgress(chapter));
  assert.equal(state.chapter, chapter);
  assert.equal(state.bridge, false);
}
// Future content must remain labeled across both entering and leaving bridges.
assert.equal(timelineAt(10.99 / 15).future, false);
assert.equal(timelineAt(11 / 15).future, true);
assert.equal(timelineAt(13.99 / 15).future, true);
assert.equal(timelineAt(14 / 15).future, false);
assert.equal(timelineAt(-1).time, 0);
assert.equal(timelineAt(2).time, 44.96);
console.log('Landing timeline: forward/reverse, chapter navigation, boundaries and future labels passed.');
