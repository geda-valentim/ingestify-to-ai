"""
Docling converter reuse.

Building a DoclingConverter loads docling's layout and table models - onto the
GPU when DEVICE=cuda. `get_converter` used to build a fresh one for every task,
so every page of every PDF reloaded the weights, and `process_conversion` built
one even for audio jobs, which never use it (a ~20 s stall per worker-audio
process, and docling weights sitting next to Whisper for nothing).
"""

from unittest.mock import MagicMock

import pytest

import workers.converter as converter_module
import workers.tasks as tasks
from shared.config import get_settings
from workers.converter import get_converter


@pytest.fixture(autouse=True)
def built(monkeypatch):
    """Count real constructions; nothing here needs docling itself."""
    constructed = []

    class FakeDoclingConverter:
        def __init__(self, **options):
            constructed.append(options)
            self.options = options

    monkeypatch.setattr(converter_module, "DoclingConverter", FakeDoclingConverter)
    converter_module._cached_converter.cache_clear()
    get_settings.cache_clear()
    yield constructed
    converter_module._cached_converter.cache_clear()
    get_settings.cache_clear()


def test_the_same_preset_reuses_one_converter(built):
    first = get_converter("fast")
    second = get_converter("fast")

    assert first is second
    assert len(built) == 1


def test_different_option_sets_get_their_own_converter(built):
    fast = get_converter("fast")
    quality = get_converter("quality")

    assert fast is not quality
    assert fast.options == {"enable_ocr": False, "enable_table_structure": True, "enable_images": False}
    assert quality.options == {"enable_ocr": True, "enable_table_structure": True, "enable_images": True}


def test_presets_resolving_to_the_same_options_share_a_converter(built, monkeypatch):
    monkeypatch.setenv("DOCLING_ENABLE_OCR", "False")
    monkeypatch.setenv("DOCLING_ENABLE_IMAGES", "False")
    monkeypatch.setenv("DOCLING_ENABLE_TABLE_STRUCTURE", "True")
    get_settings.cache_clear()

    assert get_converter(None) is get_converter("fast")
    assert len(built) == 1


def test_at_most_two_option_sets_stay_resident(built):
    fast = get_converter("fast")
    get_converter("balanced")
    get_converter("quality")  # evicts the least recently used: fast

    assert get_converter("fast") is not fast
    assert len(built) == 4


def test_an_audio_job_never_builds_a_docling_converter(monkeypatch, tmp_path):
    """The converter is built on the document branch only."""
    audio = tmp_path / "aula.mp3"
    audio.write_bytes(b"ID3")

    get_converter_spy = MagicMock(side_effect=AssertionError("audio job built a docling converter"))
    monkeypatch.setattr(tasks, "get_converter", get_converter_spy)
    monkeypatch.setattr(tasks, "get_redis_client", MagicMock)
    monkeypatch.setattr(tasks, "get_es_client", MagicMock)
    monkeypatch.setattr(tasks, "SessionLocal", MagicMock)
    monkeypatch.setattr(tasks, "_resolve_uploaded_file", lambda source, job_id: audio)

    reached = []

    def transcribe(*args, **kwargs):
        reached.append(True)
        raise RuntimeError("stop here")

    import workers.audio as audio_pkg
    monkeypatch.setattr(audio_pkg, "transcribe_with_gpu_fallback", transcribe)

    try:
        tasks.process_conversion.run(
            job_id="job-audio",
            source_type="file",
            source=str(audio),
            options={"is_audio": True, "output_format": "json"},
        )
    except Exception:
        # Whatever the task does with a failed transcription is not under test
        pass

    assert reached, "the task never got to the audio branch"
    get_converter_spy.assert_not_called()
