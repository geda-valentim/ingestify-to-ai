"""Bounded-context LocalAgreement-2 over faster-whisper's timestamped words.

Independent implementation of the online policy described by WhisperStreaming:
https://github.com/ufal/whisper_streaming . The loaded model is shared; hypotheses,
audio, prompt and the source clock are private to each session. No file decoding.
"""
import time
from dataclasses import dataclass
import numpy as np
from shared.live.protocol import LiveError, RATE


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


class OnlineWhisper:
    def __init__(self, model, language='pt', interval=0.6, max_context=8):
        self.model, self.language = model, language
        self.interval, self.max_context = interval, max_context
        self.audio = np.empty(0, dtype=np.float32)
        self.offset = 0.0
        self.received = 0
        self.last_decode = 0
        self.previous = []
        self.confirmed_words = []
        self.segments = []
        self.committed_end = 0.0
        self.revision = 0
        self.utterance = 0
        self.inference_seconds = 0.0

    def push(self, pcm):
        samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.0
        self.audio = np.concatenate((self.audio, samples))
        self.received += len(samples)
        if len(self.audio) > (self.max_context + 2) * RATE:
            raise LiveError('LIVE_UNSTABLE_CONTEXT', 4429)
        if self.received - self.last_decode < self.interval * RATE:
            return []
        return self.decode()

    def _hypothesis(self):
        prompt_words = [w for w in self.confirmed_words if w.end <= self.offset][-80:]
        prompt = ''.join(w.text for w in prompt_words).strip() or None
        started = time.monotonic()
        segments, _ = self.model.transcribe(
            self.audio, language=self.language, beam_size=1, temperature=0,
            word_timestamps=True, vad_filter=True,
            vad_parameters={'min_silence_duration_ms': 300},
            initial_prompt=prompt, condition_on_previous_text=False, max_new_tokens=128,
        )
        words, boundaries = [], []
        for segment in segments:
            boundaries.append(self.offset + segment.end)
            if segment.no_speech_prob > .9 or getattr(segment, 'compression_ratio', 0) > 2.4:
                continue
            for word in segment.words or []:
                start, end = self.offset + word.start, self.offset + word.end
                if end > self.committed_end + .02 and start >= self.committed_end - .15:
                    words.append(Word(start, end, word.word))
        self.inference_seconds += time.monotonic() - started
        # Temporal overlap, not an n-gram text match, removes confirmed words.
        # A legitimate repetition starting at/after the boundary ("sim, sim")
        # must survive even when it equals the previous committed suffix.
        if self.confirmed_words:
            last = self.confirmed_words[-1]
            words = [w for w in words if not (w.start < self.committed_end - .01
                     and w.text.strip() == last.text.strip())]
        return words, boundaries

    def _commit(self, words):
        if not words:
            return []
        text = ''.join(w.text for w in words).strip()
        if not text:
            return []
        start = max(self.committed_end, words[0].start)
        end = min(self.received / RATE, max(start, words[-1].end))
        segment = {'start': start, 'end': end, 'text': text}
        event = {'type': 'transcript.final', 'segment_id': len(self.segments),
                 'utterance_id': self.utterance, **segment}
        self.segments.append(segment)
        self.confirmed_words.extend(words)
        self.confirmed_words = self.confirmed_words[-160:]
        self.committed_end = end
        self.utterance += 1
        return [event]

    def decode(self, finish=False):
        self.last_decode = self.received
        if len(self.audio) == 0:
            return []
        words, boundaries = self._hypothesis()
        common = 0
        if finish:
            common = len(words)
        else:
            # Only an identical prefix in two consecutive overlapping decodes
            # can become immutable. Require 200 ms of lookahead as well.
            for old, new in zip(self.previous, words):
                if old.text.strip() != new.text.strip() or new.end > self.received / RATE - .2:
                    break
                common += 1
        events = self._commit(words[:common])
        self.previous = words[common:]
        self.revision += 1
        events.append({'type': 'transcript.partial', 'utterance_id': self.utterance,
                       'revision': self.revision, 'text': ''.join(w.text for w in self.previous).strip()})
        # Trim at a fully confirmed decoder segment boundary, retaining 1 s of
        # overlap. Never discard unconfirmed words to meet a memory limit.
        cuts = [b for b in boundaries if self.offset + 1 < b <= self.committed_end - 1]
        # Stable word boundaries allow trimming long utterances too; all audio
        # after this cut remains, and the committed prefix becomes a prompt.
        cuts += [w.end for w in self.confirmed_words if self.offset + 1 < w.end <= self.committed_end - 1]
        if len(self.audio) > self.max_context * RATE:
            cut = max(cuts) if cuts else None
            if cut is None and not words and not self.previous:
                cut = self.received / RATE - 1  # VAD-confirmed silence only
            if cut is not None:
                n = int((cut - self.offset) * RATE)
                self.audio = self.audio[n:]
                self.offset += n / RATE
        return events

    def finish(self):
        return self.decode(finish=True)

    def result(self, model_name):
        text = ' '.join(s['text'] for s in self.segments)
        return {'text': text, 'segments': self.segments, 'language': self.language,
                'duration': self.received / RATE, 'word_count': len(text.split()),
                'char_count': len(text), 'model': model_name, 'provider': 'faster-whisper',
                'device': 'cuda', 'input_mode': 'live', 'protocol': 1}


class WhisperXOnlineASR:
    """Timestamp adapter for WhisperX's resident faster-whisper subclass.

    File batching/alignment cannot supply OnlineWhisper's native word timestamps.
    Keep the qualified WhisperX weights, call their inherited timestamp decoder,
    and preserve LocalAgreement's existing immutable-text policy.
    """
    provider = 'whisperx'

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.model = pipeline.model
        if not callable(getattr(self.model, 'transcribe', None)):
            raise RuntimeError('WhisperX live ASR does not expose native timestamps')

    def transcribe(self, audio, **options):
        return self.model.transcribe(audio, **options)
