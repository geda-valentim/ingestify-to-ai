// Real TypeScript reducer compiled for Node, against the Python protocol fixture.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const crypto = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../hooks/live-diarization.ts'), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
const scope = { exports: {}, TextEncoder, crypto: crypto.webcrypto };
vm.runInNewContext(compiled, scope);
const { initialDiarization, reduceDiarization, canonicalDiarization, diarizationDigest, labelsForInterval } = scope.exports;
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, '../../backend/tests/fixtures/live-speakers-v2.json')));
(async () => {
  let state = initialDiarization(fixture.generation);
  for (const update of fixture.updates) state = reduceDiarization(state, update, fixture.received_samples);
  assert.equal(JSON.stringify(canonicalDiarization(state)), JSON.stringify(fixture.canonical));
  assert.equal(await diarizationDigest(state), fixture.digest);
  assert.equal(reduceDiarization(state, fixture.updates[0], fixture.received_samples), state);
  assert.throws(() => reduceDiarization(state, { ...fixture.updates[0], turns: [] }, fixture.received_samples));
  assert.throws(() => reduceDiarization(state, { ...fixture.updates[3], generation: 9 }, fixture.received_samples));
  assert.throws(() => reduceDiarization(state, { ...fixture.updates[3], revision: 6 }, fixture.received_samples));
  assert.throws(() => reduceDiarization(initialDiarization(7), { ...fixture.updates[0], horizon_samples: true }, fixture.received_samples));
  assert.equal(labelsForInterval(state, 1, 1.5).labels.join(' + '), 'Falante 1 + Falante 2');
  assert.equal(labelsForInterval(state, 2, 3).labels.length, 0);
  assert.equal(labelsForInterval(state, 6, 7).provisional, true);
  console.log('live diarization: Python/TypeScript canonical state and SHA256 match; replays, gaps, generations, overlap, unknown and watermark passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
// Partial attribution cannot be presented as a known speaker for the whole cue.
let partialState = initialDiarization(8);
partialState = reduceDiarization(partialState, { generation: 8, revision: 1, horizon_samples: 16000,
  replace_from_samples: 0, replace_to_samples: 16000, stable_until_samples: 16000,
  speakers: [{ id: 'SPEAKER_00', label: 'Falante 1' }],
  turns: [{ start_samples: 0, end_samples: 1600, speaker_id: 'SPEAKER_00' }] }, 16000);
assert.equal(labelsForInterval(partialState, 0, 1).unknown, true);
assert.equal(labelsForInterval(partialState, 0, .1).unknown, false);
// Thirty minutes of annotations: compare indexed queries with a simple oracle.
const history = initialDiarization(9);
history.speakers = [{ id: 'SPEAKER_00', label: 'Falante 1' }, { id: 'SPEAKER_01', label: 'Falante 2' }];
history.frozen = Array.from({ length: 3600 }, (_, i) => ({ start_samples: i * 8000, end_samples: i * 8000 + 10000, speaker_id: `SPEAKER_0${i % 2}` }));
history.stable_until_samples = 28800000;
let indexedTurns = 0;
const start = performance.now();
for (let i = 0; i < 3000; i++) indexedTurns += labelsForInterval(history, i * .6, i * .6 + .6).labels.length;
const elapsed = performance.now() - start;
assert(indexedTurns > 3000);
for (let i = 0; i < 3000; i += 67) {
  const a = i * .6, b = a + .6;
  const ids = new Set(history.frozen.filter(t => t.start_samples < b * 16000 && t.end_samples > a * 16000).map(t => t.speaker_id));
  assert.equal(labelsForInterval(history, a, b).labels.join(), history.speakers.filter(s => ids.has(s.id)).map(s => s.label).join());
}
console.log(`live interval index: 3600 turns / 3000 cue queries ${elapsed.toFixed(1)} ms; partial unknown retained`);
