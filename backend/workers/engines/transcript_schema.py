"""Bounded schema 2 transcript contract, shared by local and remote workers.

Standard library only. Unknown/ambiguous speakers remain null. Alignment scores
are not ASR probabilities. No model or biometric embeddings cross this boundary.
"""
from copy import deepcopy
import json
import math
from numbers import Real
import re

MAX_SPEAKERS = 20
MAX_TURNS = 200_000
MAX_SEGMENTS = 200_000
MAX_WORDS = 1_000_000
MAX_BYTES = 32 * 1024 * 1024
ID = re.compile(r'SPEAKER_\d{2}\Z')


def number(value, name, duration=None, nullable=False):
    if value is None and nullable:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f'INVALID_TRANSCRIPT: {name}')
    if duration is not None and value > duration + 0.001:
        raise ValueError(f'INVALID_TRANSCRIPT: {name} exceeds duration')
    return float(value)


def validate_result(result):
    """Validate and copy schema 2. Legacy results keep their existing reader."""
    if result.get('schema_version') != 2:
        return result
    # allow_nan=False rejects non-finite values in optional metadata too.
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode()) > MAX_BYTES:
        raise ValueError('TRANSCRIPT_TOO_LARGE')
    out = deepcopy(result)
    duration = number(out.get('duration'), 'duration')
    speakers = out.get('speakers')
    if not isinstance(speakers, list) or len(speakers) > MAX_SPEAKERS:
        raise ValueError('SPEAKER_LIMIT_EXCEEDED')
    ids = set()
    for speaker in speakers:
        sid = speaker.get('id')
        if not isinstance(sid, str) or not ID.fullmatch(sid) or sid in ids:
            raise ValueError('INVALID_SPEAKER_ID')
        if not isinstance(speaker.get('label'), str) or len(speaker['label']) > 64:
            raise ValueError('INVALID_SPEAKER_LABEL')
        ids.add(sid)
    alignment = out.get('alignment')
    if not isinstance(alignment, dict) or alignment.get('status') not in ('completed', 'unavailable'):
        raise ValueError('INVALID_ALIGNMENT_STATUS')
    diarization = out.get('diarization', {})
    if not isinstance(diarization, dict):
        raise ValueError('INVALID_DIARIZATION_STATUS')
    if set(diarization) - {'status', 'speaker_count', 'engine', 'model', 'revision', 'turns', 'generation', 'provenance'}:
        raise ValueError('INVALID_DIARIZATION_FIELDS')
    status = diarization.get('status')
    if status not in ('completed', 'disabled'):
        raise ValueError('INVALID_DIARIZATION_STATUS')
    if isinstance(diarization.get('speaker_count'), bool):
        raise ValueError('INVALID_SPEAKER_COUNT')
    expected_count = len(ids) if status == 'completed' else None
    if diarization.get('speaker_count') != expected_count or (status == 'disabled' and ids):
        raise ValueError('INVALID_SPEAKER_COUNT')
    turns = diarization.get('turns', [])
    if not isinstance(turns, list) or len(turns) > MAX_TURNS:
        raise ValueError('SPEAKER_TURN_LIMIT_EXCEEDED')
    def interval(row, nullable=False):
        start = number(row.get('start'), 'start', duration, nullable)
        end = number(row.get('end'), 'end', duration, nullable)
        if (start is None) != (end is None) or (start is not None and start > end):
            raise ValueError('INVALID_TRANSCRIPT_INTERVAL')
    def reference(row):
        if row.get('speaker_id') is not None and row['speaker_id'] not in ids:
            raise ValueError('INVALID_SPEAKER_REFERENCE')
    for turn in turns:
        interval(turn)
        reference(turn)
        if turn.get('speaker_id') is None:
            raise ValueError('INVALID_SPEAKER_REFERENCE')
    segments = out.get('segments')
    if not isinstance(segments, list) or len(segments) > MAX_SEGMENTS:
        raise ValueError('SEGMENT_LIMIT_EXCEEDED')
    word_count = 0
    for segment in segments:
        interval(segment)
        reference(segment)
        if not isinstance(segment.get('text'), str) or len(segment['text']) > 20_000:
            raise ValueError('INVALID_SEGMENT_TEXT')
        words = segment.get('words', [])
        if not isinstance(words, list) or len(words) > 5000:
            raise ValueError('WORD_LIMIT_EXCEEDED')
        word_count += len(words)
        for word in words:
            interval(word, nullable=True)
            reference(word)
            if not isinstance(word.get('word'), str) or len(word['word']) > 512:
                raise ValueError('INVALID_WORD')
            if word.get('start') is None and word.get('speaker_id') is not None:
                raise ValueError('UNTIMED_WORD_SPEAKER')
            for field in ('probability', 'alignment_score'):
                if word.get(field) is not None:
                    number(word[field], field, 1)
    if word_count > MAX_WORDS:
        raise ValueError('WORD_LIMIT_EXCEEDED')
    return out


def speaker_for_interval(start, end, turns):
    """Greatest temporal intersection; no nearest speaker and no tie breaking."""
    if start is None or end is None or end <= start:
        return None
    overlap = {}
    for turn in turns:
        amount = max(0, min(end, turn['end']) - max(start, turn['start']))
        if amount:
            overlap[turn['speaker_id']] = overlap.get(turn['speaker_id'], 0) + amount
    if not overlap:
        return None
    ordered = sorted(overlap, key=overlap.get, reverse=True)
    if len(ordered) > 1 and math.isclose(overlap[ordered[0]], overlap[ordered[1]], abs_tol=1e-8):
        return None
    return ordered[0]


def normalize_aligned_segments(segments, turns, *, expose_words=False):
    """Split only when aligned words prove a speaker change; retain untimed text."""
    def scalar(value):
        # WhisperX alignment emits NumPy scalars. Convert at the inference
        # boundary; keep the remote JSON validator strict about primitive types.
        if (isinstance(value, bool) or not isinstance(value, Real)
                or not math.isfinite(value) or value < 0):
            raise ValueError('INVALID_ALIGNMENT_NUMBER')
        return float(value)

    result = []
    for segment in segments:
        words = []
        for raw in segment.get('words', []):
            start, end = raw.get('start'), raw.get('end')
            if start is None or end is None:
                start = end = None
            else:
                start, end = scalar(start), scalar(end)
            word = {'word': raw['word'], 'start': start, 'end': end,
                    'speaker_id': speaker_for_interval(start, end, turns)}
            if raw.get('score') is not None:
                word['alignment_score'] = scalar(raw['score'])
            if raw.get('probability') is not None:
                word['probability'] = scalar(raw['probability'])
            words.append(word)
        # Never recreate text from incompletely aligned tokens: punctuation,
        # numeric strings and unaligned words are part of the user's transcript.
        consistent = words and all(w['start'] is not None for w in words)
        token_text = ' '.join(w['word'].strip() for w in words)
        consistent = consistent and ''.join(token_text.split()) == ''.join(segment['text'].split())
        groups = []
        if consistent:
            for word in words:
                if not groups or groups[-1][0]['speaker_id'] != word['speaker_id']:
                    groups.append([])
                groups[-1].append(word)
        if len(groups) > 1:
            for group in groups:
                entry = {'start': group[0]['start'], 'end': group[-1]['end'],
                         'text': ' '.join(w['word'].strip() for w in group), 'speaker_id': group[0]['speaker_id']}
                if expose_words:
                    entry['words'] = group
                result.append(entry)
        else:
            labels = {w['speaker_id'] for w in words}
            label = next(iter(labels)) if words and len(labels) == 1 else None
            entry = {'start': scalar(segment['start']), 'end': scalar(segment['end']),
                     'text': segment['text'], 'speaker_id': label}
            if expose_words:
                entry['words'] = words
            result.append(entry)
    return result
