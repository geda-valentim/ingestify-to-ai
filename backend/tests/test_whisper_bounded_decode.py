"""
workers.engines.whisper_core.load_bounded_audio: the decoder counts samples as they
come out, so an upload cannot expand past the duration limit in the worker's memory
(security finding: faster-whisper's own decode_audio accumulates the whole file).
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

av = pytest.importorskip("av")
pytest.importorskip("faster_whisper")

from workers.engines import whisper_core  # noqa: E402

RATE = 44100


def _write(path: Path, seconds: float, codec: str, rate: int = RATE) -> Path:
    """A small stereo tone (so the mono mixdown is exercised) in a PyAV-written container"""
    t = np.arange(int(seconds * rate)) / rate
    tone = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    data = np.stack([tone, (tone * 0.5).astype(np.int16)])
    with av.open(str(path), "w") as out:
        stream = out.add_stream(codec, rate=rate)
        stream.layout = "stereo"
        frame_size = 4096
        for start in range(0, data.shape[1], frame_size):
            chunk = np.ascontiguousarray(data[:, start:start + frame_size])
            frame = av.AudioFrame.from_ndarray(chunk, format="s16p", layout="stereo")
            frame.sample_rate = rate
            frame.pts = start
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    return path


@pytest.mark.parametrize("name,codec", [("a.flac", "flac"), ("a.wav", "pcm_s16le")])
def test_a_normal_file_decodes_like_faster_whisper(tmp_path, name, codec):
    from faster_whisper.audio import decode_audio

    path = _write(tmp_path / name, 3.0, codec)
    expected = decode_audio(str(path))
    got = whisper_core.load_bounded_audio(path, 60)

    assert got.dtype == np.float32 and got.ndim == 1
    assert abs(len(got) - len(expected)) <= 1
    n = min(len(got), len(expected))
    np.testing.assert_allclose(got[:n], expected[:n], atol=1e-4)
    assert abs(len(got) / whisper_core.SAMPLE_RATE - 3.0) < 0.1


def test_a_file_at_the_limit_is_accepted(tmp_path):
    path = _write(tmp_path / "a.flac", 2.0, "flac")
    assert len(whisper_core.load_bounded_audio(path, 2)) > 0


_REAL_RESAMPLER = av.audio.resampler.AudioResampler


class _CountingResampler:
    """The real resampler, counting the decoded frames that reach it"""

    calls = 0

    def __init__(self, *args, **kwargs):
        self._real = _REAL_RESAMPLER(*args, **kwargs)

    def resample(self, frame):
        type(self).calls += 1
        return self._real.resample(frame)


def _frames_decoded(monkeypatch, run):
    _CountingResampler.calls = 0
    monkeypatch.setattr(av.audio.resampler, "AudioResampler", _CountingResampler)
    run()
    return _CountingResampler.calls


def test_a_longer_file_is_refused_and_decoding_stops_early(tmp_path, monkeypatch):
    path = _write(tmp_path / "long.flac", 10.0, "flac")
    total_frames = _frames_decoded(monkeypatch, lambda: whisper_core.load_bounded_audio(path, 60))

    def refuse():
        with pytest.raises(whisper_core.AudioDurationExceeded) as caught:
            whisper_core.load_bounded_audio(path, 2)
        assert caught.value.code == "AUDIO_DURATION_LIMIT_EXCEEDED"

    stopped_at = _frames_decoded(monkeypatch, refuse)
    assert total_frames > 90
    # 2 s + the 1 s tolerance of a 10 s file: about a third of the frames, never all
    assert stopped_at < total_frames / 2


def test_container_metadata_that_claims_a_short_duration_is_not_trusted(tmp_path):
    path = _write(tmp_path / "lie.flac", 10.0, "flac")
    raw = bytearray(path.read_bytes())
    # STREAMINFO: 20 bit rate, 3 channels, 5 bps, 36 bit total samples (bytes 18..25)
    head = int.from_bytes(raw[18:26], "big")
    head = (head >> 36 << 36) | RATE  # claims one second
    raw[18:26] = head.to_bytes(8, "big")
    path.write_bytes(bytes(raw))
    with av.open(str(path)) as container:
        assert container.duration / 1_000_000 < 1.5  # the header says ~1 s

    assert len(whisper_core.load_bounded_audio(path, 60)) > 5 * whisper_core.SAMPLE_RATE
    with pytest.raises(whisper_core.AudioDurationExceeded):
        whisper_core.load_bounded_audio(path, 2)


def test_transcribe_hands_the_bounded_array_to_the_model(tmp_path):
    path = _write(tmp_path / "a.flac", 1.0, "flac")
    seen = {}

    def fake_transcribe(audio, **kwargs):
        seen["audio"] = audio
        return iter([]), SimpleNamespace(duration=1.0, language="en", language_probability=1.0)

    model = SimpleNamespace(transcribe=fake_transcribe)
    result = whisper_core.transcribe(model, path, {}, model_name="tiny")
    assert isinstance(seen["audio"], np.ndarray) and seen["audio"].dtype == np.float32
    assert result["text"] == ""


def test_transcribe_refuses_audio_over_the_limit_before_the_model_runs(tmp_path):
    path = _write(tmp_path / "long.flac", 6.0, "flac")
    model = SimpleNamespace(transcribe=lambda *a, **k: pytest.fail("the model must not see the audio"))
    with pytest.raises(whisper_core.AudioDurationExceeded):
        whisper_core.transcribe(model, path, {}, model_name="tiny", max_audio_seconds=2)


def test_the_code_is_in_the_catalog_in_both_languages():
    from shared import error_catalog

    code = whisper_core.AudioDurationExceeded.code
    assert error_catalog.render(code, lang="en") != error_catalog.render(code, lang="pt")


def test_the_job_task_does_not_retry_a_duration_refusal():
    from workers import tasks

    assert tasks._is_duration_limit(whisper_core.AudioDurationExceeded(5))
    assert not tasks._is_duration_limit(RuntimeError("boom"))
