"""Version 2 speaker interval reducer; no inference/runtime dependencies.

All offsets are integer PCM samples. Updates replace intervals, never transcript
text. Only the mutable five-second suffix is visited during incremental updates.
"""
import hashlib
import json
from shared.live.protocol import LiveError, RATE

WINDOW = 5 * RATE
MAX_TURNS = 200_000
MAX_SPEAKERS = 20
FIELDS = ('generation', 'revision', 'horizon_samples', 'stable_until_samples', 'speakers', 'turns')


def integer(value):
    return type(value) is int and 0 <= value <= 2**53 - 1


def canonical_turns(turns):
    merged = []
    for turn in sorted(turns, key=lambda t: (t['speaker_id'], t['start_samples'], t['end_samples'])):
        turn = {key: turn[key] for key in ('start_samples', 'end_samples', 'speaker_id')}
        if merged and merged[-1]['speaker_id'] == turn['speaker_id'] and turn['start_samples'] <= merged[-1]['end_samples']:
            merged[-1]['end_samples'] = max(merged[-1]['end_samples'], turn['end_samples'])
        else:
            merged.append(turn)
    return sorted(merged, key=lambda t: (t['start_samples'], t['end_samples'], t['speaker_id']))


class DiarizationState:
    def __init__(self, generation):
        if not integer(generation):
            raise LiveError('LIVE_DIARIZATION_PROTOCOL', 1011)
        self.generation = generation
        self.revision = self.horizon = self.stable = 0
        self.speakers = []
        self.frozen = []
        self.mutable = []
        self.last_event = None
        self.replays = {}

    @property
    def turns(self):
        return self.frozen + self.mutable

    def apply(self, event, received):
        def fail():
            raise LiveError('LIVE_DIARIZATION_PROTOCOL', 1011)
        if len(json.dumps(event, ensure_ascii=False).encode('utf-8')) > 65536:
            fail()
        keys = ('generation', 'revision', 'horizon_samples', 'replace_from_samples', 'replace_to_samples', 'stable_until_samples')
        if any(not integer(event.get(k)) for k in keys) or event['generation'] != self.generation:
            fail()
        body = {k: event.get(k) for k in (*keys, 'speakers', 'turns')}
        revision = event['revision']
        if revision == self.revision:
            if body != self.last_event:
                fail()
            return False
        if revision < self.revision:
            fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if self.replays.get(revision) != fingerprint:
                fail()
            return False
        if revision != self.revision + 1:
            fail()
        horizon, lo, hi, stable = (event[k] for k in ('horizon_samples', 'replace_from_samples', 'replace_to_samples', 'stable_until_samples'))
        floor = max(self.stable, horizon - WINDOW, 0)
        if not self.horizon <= horizon <= received or not floor <= lo <= hi <= horizon or not floor <= stable <= horizon:
            fail()
        speakers, turns = event.get('speakers'), event.get('turns')
        if not isinstance(speakers, list) or len(speakers) > MAX_SPEAKERS or speakers[:len(self.speakers)] != self.speakers:
            fail()
        for i, speaker in enumerate(speakers):
            if speaker != {'id': f'SPEAKER_{i:02d}', 'label': f'Falante {i + 1}'}:
                fail()
        ids = {s['id'] for s in speakers}
        if not isinstance(turns, list) or len(turns) > 64:
            fail()
        for turn in turns:
            if (not isinstance(turn, dict) or set(turn) != {'start_samples', 'end_samples', 'speaker_id'}
                or not integer(turn['start_samples']) or not integer(turn['end_samples'])
                or not lo <= turn['start_samples'] < turn['end_samples'] <= hi or turn['speaker_id'] not in ids):
                fail()
        tail = []
        for turn in self.mutable:
            a, b = turn['start_samples'], turn['end_samples']
            if a < lo:
                tail.append({**turn, 'end_samples': min(b, lo)})
            if b > hi:
                tail.append({**turn, 'start_samples': max(a, hi)})
        tail = canonical_turns(tail + turns)
        frozen, mutable = [], []
        for turn in tail:
            a, b = turn['start_samples'], turn['end_samples']
            if a < stable:
                frozen.append({**turn, 'end_samples': min(b, stable)})
            if b > stable:
                mutable.append({**turn, 'start_samples': max(a, stable)})
        if len(self.frozen) + len(frozen) + len(mutable) > MAX_TURNS:
            raise LiveError('LIVE_DIARIZATION_TURN_LIMIT', 4429)
        self.frozen.extend(frozen)
        self.mutable = mutable
        self.speakers = [dict(s) for s in speakers]
        self.revision, self.horizon, self.stable = revision, horizon, stable
        self.last_event = body
        self.replays[revision] = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return True

    def canonical(self):
        return {'generation': self.generation, 'revision': self.revision, 'horizon_samples': self.horizon,
                'stable_until_samples': self.stable, 'speakers': self.speakers,
                'turns': canonical_turns(self.turns)}

    def digest(self):
        return hashlib.sha256(json.dumps(self.canonical(), ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()

    def finish(self, message, samples):
        expected = {'generation': self.generation, 'revision': self.revision, 'samples': samples,
                    'turn_count': len(canonical_turns(self.turns)), 'digest': self.digest()}
        if self.horizon != samples or self.stable != samples or any(message.get(k) != v or type(message.get(k)) is not type(v) for k, v in expected.items()):
            raise LiveError('LIVE_DIARIZATION_PROTOCOL', 1011)

    def annotate(self, result, provenance):
        result = {**result, 'schema_version': 2, 'speakers': list(self.speakers),
                  'alignment': {'status': 'unavailable', 'reason': 'native_online_asr_timestamps'},
                  'diarization': {'status': 'completed', 'engine': 'diart', 'model': 'diart',
                    'speaker_count': len(self.speakers), 'generation': self.generation,
                    'revision': self.revision, 'provenance': provenance,
                    'turns': [{'start': t['start_samples'] / RATE, 'end': t['end_samples'] / RATE,
                               'speaker_id': t['speaker_id']} for t in canonical_turns(self.turns)]}}
        result['segments'] = []
        # Do not split/retime immutable confirmed text to accommodate turns.
        return result


def annotate_result(state, result, provenance):
    annotated = state.annotate(result, provenance)
    turns = annotated['diarization']['turns']
    for segment in result['segments']:
        overlaps = [t for t in turns if t['start'] < segment['end'] and t['end'] > segment['start']]
        ids = {t['speaker_id'] for t in overlaps}
        # Gaps/unknown remain unknown, even when the only nearby voice is known.
        intervals = sorted((max(t['start'], segment['start']), min(t['end'], segment['end'])) for t in overlaps)
        covered = segment['start']
        for start, end in intervals:
            if start > covered + 1 / RATE:
                break
            covered = max(covered, end)
        speaker = next(iter(ids)) if len(ids) == 1 and covered >= segment['end'] and segment['end'] > segment['start'] else None
        annotated['segments'].append({**segment, 'speaker_id': speaker})
    return annotated
