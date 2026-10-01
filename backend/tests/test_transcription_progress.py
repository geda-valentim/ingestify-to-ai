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

    def on_progress(done, total):
        # Reported while decoding, not after: the segment has just been produced
        calls.append((done, total, list(decoded)))

    result = transcriber.transcribe(Path(audio), {}, on_progress=on_progress)

    assert [(d, t) for d, t, _ in calls] == [(0.0, 12.0), (4.0, 12.0), (9.5, 12.0), (12.0, 12.0)]
    assert [seen for _, _, seen in calls][1:] == [[4.0], [4.0, 9.5], [4.0, 9.5, 12.0]]
    assert len(result["segments"]) == 3


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
