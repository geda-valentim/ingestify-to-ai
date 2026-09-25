"""Subtitle / text output built from Whisper segments."""
import pytest

from workers.audio.base_transcriber import AudioTranscriber


class _Transcriber(AudioTranscriber):
    def transcribe(self, audio_path, options=None):
        raise NotImplementedError

    def detect_language(self, audio_path):
        raise NotImplementedError

    def get_audio_info(self, audio_path):
        raise NotImplementedError

    def supported_formats(self):
        return []


TRANSCRIPTION = {
    "text": "Olá, tudo bem? Sim --> tudo ótimo.",
    "segments": [
        {"start": 0.0, "end": 2.5, "text": " Olá, tudo bem? "},
        {"start": 3661.042, "end": 3663.9, "text": "Sim -->\n\ntudo ótimo."},
        {"start": 3664.0, "end": 3665.0, "text": "   "},  # empty segments are skipped
    ],
}


@pytest.fixture
def transcriber():
    return _Transcriber()


def test_vtt(transcriber):
    assert transcriber.format_as_vtt(TRANSCRIPTION) == (
        "WEBVTT\n"
        "\n"
        "1\n"
        "00:00:00.000 --> 00:00:02.500\n"
        "Olá, tudo bem?\n"
        "\n"
        "2\n"
        "01:01:01.042 --> 01:01:03.900\n"
        "Sim -> tudo ótimo.\n"
    )


def test_srt(transcriber):
    assert transcriber.format_as_srt(TRANSCRIPTION) == (
        "1\n"
        "00:00:00,000 --> 00:00:02,500\n"
        "Olá, tudo bem?\n"
        "\n"
        "2\n"
        "01:01:01,042 --> 01:01:03,900\n"
        "Sim -> tudo ótimo.\n"
    )


def test_text(transcriber):
    assert transcriber.format_as_text(TRANSCRIPTION) == "Olá, tudo bem?\nSim --> tudo ótimo."


def test_no_speech_produces_valid_empty_outputs(transcriber):
    empty = {"text": "", "segments": []}
    assert transcriber.format_as_vtt(empty) == "WEBVTT\n"
    assert transcriber.format_as_srt(empty) == ""
    assert transcriber.format_as_text(empty) == ""


def test_end_before_start_is_clamped(transcriber):
    vtt = transcriber.format_as_vtt({"segments": [{"start": 5.0, "end": 4.0, "text": "x"}]})
    assert "00:00:05.000 --> 00:00:05.000" in vtt
