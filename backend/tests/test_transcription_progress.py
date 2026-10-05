"""
Live transcription progress.

A transcription used to jump from 30% straight to 70% when it finished, so an
hour-long recording sat at 30% for minutes with no sign of life. faster-whisper
decodes segments lazily; each segment's end time is how far into the media the
transcription is, and that now drives the job's progress in between.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from workers.audio.faster_whisper_transcriber import FasterWhisperTranscriber
from workers.tasks import (
    LIVE_TRANSCRIPT_FLUSH_SECONDS,
    TRANSCRIPTION_PROGRESS_END,
    TRANSCRIPTION_PROGRESS_START,
    _transcription_progress,
)


def _writes(redis_client):
    return [(c.args[1], c.kwargs) for c in redis_client.update_job_progress.call_args_list]


def test_transcribed_share_maps_onto_the_transcription_slice():
    redis_client = MagicMock()
    on_progress = _transcription_progress(redis_client, "job")

    on_progress(0.0, 3600.0)
    on_progress(1800.0, 3600.0)
    on_progress(3600.0, 3600.0)

    progress = [p for p, _ in _writes(redis_client)]
    assert progress == [TRANSCRIPTION_PROGRESS_START, 50, TRANSCRIPTION_PROGRESS_END]


def test_media_position_is_recorded_for_the_job_page():
    redis_client = MagicMock()

    _transcription_progress(redis_client, "job")(754.26, 3447.64)

    _, details = _writes(redis_client)[0]
    assert details == {"transcribed_seconds": 754.3, "media_duration": 3447.6}


def test_writes_only_when_the_percentage_moves():
    redis_client = MagicMock()
    on_progress = _transcription_progress(redis_client, "job")

    # 400 segments across an hour: one write per percentage point, not per segment
    for i in range(401):
        on_progress(i * 9.0, 3600.0)

    progress = [p for p, _ in _writes(redis_client)]
    assert progress == list(range(TRANSCRIPTION_PROGRESS_START, TRANSCRIPTION_PROGRESS_END + 1))


def test_unknown_duration_and_overshoot_are_harmless():
    redis_client = MagicMock()
    on_progress = _transcription_progress(redis_client, "job")

    on_progress(10.0, 0.0)  # no duration: nothing to report
    on_progress(3700.0, 3600.0)  # last segment ending past the reported duration

    assert [p for p, _ in _writes(redis_client)] == [TRANSCRIPTION_PROGRESS_END]


def test_a_failing_progress_write_never_fails_the_transcription():
    redis_client = MagicMock()
    redis_client.update_job_progress.side_effect = ConnectionError("redis down")

    _transcription_progress(redis_client, "job")(100.0, 3600.0)  # no exception


def test_faster_whisper_reports_each_segment_as_it_is_decoded(tmp_path):
    decoded = []

    def segments():
        for start, end in ((0.0, 4.0), (4.0, 9.5), (9.5, 12.0)):
            decoded.append(end)
            yield SimpleNamespace(start=start, end=end, text=" oi ", words=None)

    model = MagicMock()
    model.transcribe.return_value = (
        segments(),
        SimpleNamespace(language="pt", language_probability=0.99, duration=12.0),
    )
    transcriber = FasterWhisperTranscriber.__new__(FasterWhisperTranscriber)
    transcriber.model = model
    transcriber.model_size = "turbo"
    audio = tmp_path / "aula.mp3"
    audio.write_bytes(b"ID3")

    calls = []
    texts = []

    def on_progress(done, total, segment=None):
        # Reported while decoding, not after: the segment has just been produced
        calls.append((done, total, list(decoded)))
        if segment:
            texts.append(segment)

    result = transcriber.transcribe(Path(audio), {}, on_progress=on_progress)

    assert [(d, t) for d, t, _ in calls] == [(0.0, 12.0), (4.0, 12.0), (9.5, 12.0), (12.0, 12.0)]
    assert [seen for _, _, seen in calls][1:] == [[4.0], [4.0, 9.5], [4.0, 9.5, 12.0]]
    assert len(result["segments"]) == 3
    assert texts == [
        {"start": 0.0, "end": 4.0, "text": "oi"},
        {"start": 4.0, "end": 9.5, "text": "oi"},
        {"start": 9.5, "end": 12.0, "text": "oi"},
    ]


def test_faster_whisper_without_a_callback_behaves_as_before(tmp_path):
    model = MagicMock()
    model.transcribe.return_value = (
        iter([SimpleNamespace(start=0.0, end=1.0, text=" oi ", words=None)]),
        SimpleNamespace(language="pt", language_probability=0.99, duration=1.0),
    )
    transcriber = FasterWhisperTranscriber.__new__(FasterWhisperTranscriber)
    transcriber.model = model
    transcriber.model_size = "turbo"
    audio = tmp_path / "aula.mp3"
    audio.write_bytes(b"ID3")

    assert transcriber.transcribe(Path(audio), {})["text"] == "oi"


# --- Live text ---------------------------------------------------------------


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _seg(start, end, text="oi"):
    return {"start": start, "end": end, "text": text}


def _appended(redis_client):
    return [c.args[1] for c in redis_client.append_partial_transcript.call_args_list]


def test_segments_are_pushed_in_batches_as_time_passes():
    redis_client = MagicMock()
    clock = _Clock()
    on_progress = _transcription_progress(redis_client, "job", clock=clock)

    on_progress(4.0, 60.0, segment=_seg(0.0, 4.0))
    on_progress(8.0, 60.0, segment=_seg(4.0, 8.0))
    assert _appended(redis_client) == []  # still within the batching window

    clock.now = LIVE_TRANSCRIPT_FLUSH_SECONDS
    on_progress(12.0, 60.0, segment=_seg(8.0, 12.0))

    assert _appended(redis_client) == [[_seg(0.0, 4.0), _seg(4.0, 8.0), _seg(8.0, 12.0)]]


def test_a_restart_drops_the_text_of_the_failed_attempt():
    redis_client = MagicMock()
    clock = _Clock()
    on_progress = _transcription_progress(redis_client, "job", clock=clock)

    on_progress(0.0, 60.0)
    on_progress(4.0, 60.0, segment=_seg(0.0, 4.0))
    on_progress(0.0, 60.0)  # GPU failed: the CPU retry starts over
    clock.now = LIVE_TRANSCRIPT_FLUSH_SECONDS
    on_progress(5.0, 60.0, segment=_seg(0.0, 5.0, "de novo"))

    assert redis_client.delete_partial_transcript.call_count == 2
    assert _appended(redis_client) == [[_seg(0.0, 5.0, "de novo")]]


def test_a_failing_live_text_write_never_fails_the_transcription():
    redis_client = MagicMock()
    redis_client.append_partial_transcript.side_effect = ConnectionError("redis down")
    clock = _Clock()
    on_progress = _transcription_progress(redis_client, "job", clock=clock)

    clock.now = LIVE_TRANSCRIPT_FLUSH_SECONDS
    on_progress(30.0, 60.0, segment=_seg(0.0, 30.0))  # no exception

    assert [p for p, _ in _writes(redis_client)] == [50]  # progress still recorded


def test_partial_transcript_is_read_from_where_the_client_left_off():
    import fakeredis
    from shared.redis_client import RedisClient

    redis_client = RedisClient(client=fakeredis.FakeRedis(decode_responses=True))
    redis_client.append_partial_transcript("job", [_seg(0.0, 4.0, "olá"), _seg(4.0, 8.0, "mundo")])
    redis_client.append_partial_transcript("job", [_seg(8.0, 9.0, "!")])

    assert redis_client.get_partial_transcript("job") == (
        [_seg(0.0, 4.0, "olá"), _seg(4.0, 8.0, "mundo"), _seg(8.0, 9.0, "!")], 3
    )
    assert redis_client.get_partial_transcript("job", since=2) == ([_seg(8.0, 9.0, "!")], 3)
    assert redis_client.get_partial_transcript("job", since=3) == ([], 3)

    redis_client.delete_partial_transcript("job")
    assert redis_client.get_partial_transcript("job", since=3) == ([], 0)


def test_partial_transcript_endpoint_returns_only_the_new_segments(monkeypatch):
    import asyncio

    import fakeredis

    import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
    from api import routes
    from shared.redis_client import RedisClient

    job_id = "3f1c9a2e-0000-4000-8000-000000000002"
    redis_client = RedisClient(client=fakeredis.FakeRedis(decode_responses=True))
    redis_client.set_job_status(job_id, "main", "processing")
    redis_client.append_partial_transcript(job_id, [_seg(0.0, 4.0, "olá"), _seg(4.0, 8.0, "mundo")])
    monkeypatch.setattr(routes, "get_redis_client", lambda: redis_client)

    def get(since):
        return asyncio.run(routes.get_partial_transcript(job_id, since=since, current_user=None, owned_job=None))

    first = get(0)
    assert first.status == "processing"
    assert [s.text for s in first.segments] == ["olá", "mundo"]
    assert first.next == 2

    redis_client.append_partial_transcript(job_id, [_seg(8.0, 9.0, "!")])
    second = get(first.next)
    assert [s.text for s in second.segments] == ["!"]
    assert second.next == 3


def test_partial_transcript_endpoint_404s_for_an_unknown_job(monkeypatch):
    import asyncio

    import fakeredis
    from fastapi import HTTPException

    import workers.celery_app  # noqa: F401
    from api import routes
    from shared.redis_client import RedisClient

    redis_client = RedisClient(client=fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(routes, "get_redis_client", lambda: redis_client)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.get_partial_transcript("nope", since=0, current_user=None, owned_job=None))
    assert exc.value.status_code == 404
