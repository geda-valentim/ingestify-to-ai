"""
workers.engines.whisper_core: the decoding loop shared by local and remote engines.

It must import without Ingestify's settings (the Modal image has none), behave
like the transcriber it came out of, and stop between segments when asked to.
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from workers.engines import whisper_core

BACKEND = Path(__file__).resolve().parents[1]


def test_imports_without_ingestify_settings():
    # A fresh interpreter, so modules other tests already imported don't hide a dependency
    code = (
        "import sys\n"
        "import workers.engines.whisper_core\n"
        "import workers.audio.feature_extractor\n"
        "loaded = [m for m in sys.modules if m == 'shared' or m.startswith('shared.')]\n"
        "assert not loaded, loaded\n"
        "assert 'workers.audio.factory' not in sys.modules\n"
    )
    subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True)


def test_the_package_still_exposes_the_factory_lazily():
    import workers.audio as audio_pkg
    from workers.audio import factory

    assert audio_pkg.transcribe_with_gpu_fallback is factory.transcribe_with_gpu_fallback
    assert audio_pkg.get_audio_transcriber is factory.get_audio_transcriber
    with pytest.raises(AttributeError):
        audio_pkg.not_a_thing


def _model(ends):
    segments = (SimpleNamespace(start=e - 1.0, end=e, text=f" s{i} ", words=None) for i, e in enumerate(ends))
    model = MagicMock()
    model.transcribe.return_value = (
        segments, SimpleNamespace(language="pt", language_probability=0.9, duration=float(ends[-1])),
    )
    return model


def test_result_shape(tmp_path):
    result = whisper_core.transcribe(_model([1.0, 2.0]), tmp_path / "a.mp3", {}, model_name="turbo")

    assert result == {
        "text": "s0 s1", "segments": [{"start": 0.0, "end": 1.0, "text": "s0"}, {"start": 1.0, "end": 2.0, "text": "s1"}],
        "language": "pt", "language_probability": 0.9, "duration": 2.0,
        "word_count": 2, "char_count": 5, "model": "turbo", "provider": "faster-whisper",
    }


def test_cancel_stops_between_segments(tmp_path):
    decoded = []

    def on_progress(done, total, segment=None):
        if segment:
            decoded.append(segment["end"])

    with pytest.raises(whisper_core.TranscriptionCancelled, match="at 2.0s of 4.0s"):
        whisper_core.transcribe(
            _model([1.0, 2.0, 3.0, 4.0]), tmp_path / "a.mp3", {}, model_name="turbo",
            on_progress=on_progress, should_cancel=lambda: len(decoded) >= 2,
        )

    assert decoded == [1.0, 2.0]  # stopped right after the segment that tripped it
