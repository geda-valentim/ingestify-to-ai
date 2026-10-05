/* Streaming mono resampler; bounded worklet buffers, exactly 200 ms PCM frames.
 * The source clock advances across render quanta; no per-quantum rounding drift.
 */
class LivePcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.input = [];
    this.position = 0;
    this.step = sampleRate / 16000;
    this.chunk = new Int16Array(3200);
    this.filled = 0;
    this.stopped = false;
    this.port.onmessage = ({ data }) => {
      if (data === 'finish') {
        if (this.filled) this.port.postMessage(this.chunk.slice(0, this.filled).buffer);
        this.filled = 0;
        this.stopped = true;
        this.port.postMessage('flushed');
      }
    };
  }
  process(inputs) {
    if (this.stopped) return false;
    const channels = inputs[0];
    if (!channels || !channels.length) return true;
    for (let i = 0; i < channels[0].length; i++) {
      let mono = 0;
      for (const channel of channels) mono += channel[i] / channels.length;
      this.input.push(mono);
    }
    while (this.position + 1 < this.input.length) {
      const index = Math.floor(this.position), frac = this.position - index;
      const sample = this.input[index] * (1 - frac) + this.input[index + 1] * frac;
      this.chunk[this.filled++] = Math.round(Math.max(-1, Math.min(1, sample)) * (sample < 0 ? 32768 : 32767));
      this.position += this.step;
      if (this.filled === 3200) {
        this.port.postMessage(this.chunk.buffer, [this.chunk.buffer]);
        this.chunk = new Int16Array(3200);
        this.filled = 0;
      }
    }
    const consumed = Math.min(Math.floor(this.position), this.input.length);
    this.input.splice(0, consumed);
    this.position -= consumed;
    return true;
  }
}
registerProcessor('live-pcm', LivePcmProcessor);
