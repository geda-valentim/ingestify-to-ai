"""Protocol 1: sequential, bounded PCM frames on the original 16 kHz clock."""
import json
import struct
import time
from dataclasses import dataclass

RATE = 16000
HEADER = struct.Struct('<IQ')
TERMINAL = {'completed', 'failed', 'cancelled'}


class LiveError(Exception):
    def __init__(self, code, close=4400):
        self.code, self.close = code, close
        super().__init__(code)


def control(text, limit=8192):
    if not isinstance(text, str) or len(text.encode('utf-8')) > limit:
        raise LiveError('LIVE_INVALID_CONTROL')
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise LiveError('LIVE_INVALID_CONTROL') from None
    if not isinstance(value, dict):
        raise LiveError('LIVE_INVALID_CONTROL')
    return value


@dataclass
class AudioClock:
    max_seconds: int = 1800
    seq: int = 0
    samples: int = 0
    tokens: float = 10
    tick: float = 0

    def accept(self, frame, now=None):
        now = time.monotonic() if now is None else now
        if not isinstance(frame, bytes) or not 14 <= len(frame) <= HEADER.size + RATE:
            raise LiveError('LIVE_INVALID_FRAME')
        seq, offset = HEADER.unpack_from(frame)
        pcm = frame[HEADER.size:]
        if len(pcm) % 2 or seq != self.seq or offset != self.samples:
            raise LiveError('LIVE_INVALID_SEQUENCE')
        if self.samples + len(pcm) // 2 > self.max_seconds * RATE:
            raise LiveError('LIVE_DURATION_LIMIT')
        if self.tick:
            self.tokens = min(10, self.tokens + max(0, now - self.tick) * 20)
        self.tick = now
        if self.tokens < 1:
            raise LiveError('LIVE_FRAME_RATE', 4429)
        self.tokens -= 1
        self.seq += 1
        self.samples += len(pcm) // 2
        return pcm

    def finish(self, message):
        if message.get('type') != 'finish' or type(message.get('last_seq')) is not int or message['last_seq'] != self.seq - 1:
            raise LiveError('LIVE_INVALID_FINISH')
