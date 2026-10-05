import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../public/audio/live-pcm-worklet.js", import.meta.url), "utf8");

function capture(sampleRate) {
  const messages = [];
  let Processor;
  class AudioWorkletProcessor {
    constructor() {
      this.port = {
        postMessage(message) {
          messages.push(typeof message === "string" ? message : new Int16Array(message).slice());
        },
      };
    }
  }
  vm.runInNewContext(source, {
    AudioWorkletProcessor,
    sampleRate,
    registerProcessor(name, implementation) {
      assert.equal(name, "live-pcm");
      Processor = implementation;
    },
  });
  return { processor: new Processor(), messages };
}

function feed(processor, count, values = [0.5]) {
  for (let offset = 0; offset < count; offset += 128) {
    const frames = Math.min(128, count - offset);
    const channels = values.map((value) => new Float32Array(frames).fill(value));
    assert.equal(processor.process([channels]), true);
  }
}

for (const rate of [16000, 44100, 48000]) {
  test(`120 seconds at ${rate} Hz preserve the 16 kHz source clock and flush the tail`, () => {
    const { processor, messages } = capture(rate);
    const sourceSamples = rate * 120 + 37;
    feed(processor, sourceSamples);
    const fullChunks = messages.length;
    assert.ok(fullChunks > 1);
    for (const chunk of messages) assert.equal(chunk.length, 3200);
    processor.port.onmessage({ data: "finish" });
    assert.equal(messages.at(-1), "flushed");
    const pcm = messages.filter((message) => typeof message !== "string");
    const actualSamples = pcm.reduce((sum, chunk) => sum + chunk.length, 0);
    assert.ok(Math.abs(actualSamples - sourceSamples * 16000 / rate) <= 1,
      `${actualSamples} output samples for ${sourceSamples} input samples`);
    assert.ok(pcm.at(-1).length > 0 && pcm.at(-1).length < 3200);
    assert.equal(processor.process([[new Float32Array(128)]]), false);
    assert.equal(messages.length, pcm.length + 1);
  });
}

test("stereo downmix and signed PCM saturation preserve sample values", () => {
  const { processor, messages } = capture(48000);
  feed(processor, 9603, [1, -0.5]);
  processor.port.onmessage({ data: "finish" });
  assert.equal(messages[0].length, 3200);
  assert.ok(messages[0].every((sample) => sample === Math.round(0.25 * 32767)));
  const clipping = capture(16000);
  feed(clipping.processor, 3201, [-2]);
  clipping.processor.port.onmessage({ data: "finish" });
  assert.ok(clipping.messages[0].every((sample) => sample === -32768));
});

test("capture shorter than 200 ms emits its PCM before the flushed marker", () => {
  const { processor, messages } = capture(44100);
  feed(processor, 4410, [0]);
  assert.equal(messages.length, 0);
  processor.port.onmessage({ data: "finish" });
  assert.equal(messages.length, 2);
  assert.equal(messages[1], "flushed");
  assert.ok(messages[0].length >= 1599 && messages[0].length <= 1600);
  assert.ok(messages[0].every((sample) => sample === 0));
});
