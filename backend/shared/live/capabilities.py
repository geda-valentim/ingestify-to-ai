"""Controls compatible with the timestamped LocalAgreement streaming protocol."""
import copy
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
from shared.audio_capabilities import AudioDecodingOptions, VadParameters, validate_audio_options

# The remaining faster-whisper controls would change the PCM clock, remove words,
# or conflict with the protocol's confirmed-prefix context policy.
MANAGED = {
    'task': 'transcribe', 'word_timestamps': True, 'without_timestamps': False,
    'condition_on_previous_text': False, 'clip_timestamps': '0', 'multilingual': False,
}
EXCLUDED = set(MANAGED) | {'language', 'log_progress', 'chunk_length',
    'language_detection_threshold', 'language_detection_segments'}
from shared.audio_decoding import FASTER_WHISPER_OPTIONS
fields = {name: (AudioDecodingOptions.model_fields[name].annotation, copy.deepcopy(AudioDecodingOptions.model_fields[name]))
          for name in sorted(FASTER_WHISPER_OPTIONS - EXCLUDED)}
fields.update(
    beam_size=(int, Field(1, ge=1, le=20)),
    best_of=(int, Field(5, ge=1, le=20)),
    patience=(float, Field(1, gt=0, le=10)),
    length_penalty=(float, Field(1, ge=0, le=2)),
    max_new_tokens=(int, Field(128, ge=1, le=448)),
    initial_prompt=(str | None, Field(None, max_length=1024)),
    prefix=(str | None, Field(None, max_length=1024)),
    hotwords=(str | None, Field(None, max_length=1024)),
    suppress_tokens=(list[int], Field(default_factory=lambda: [-1], max_length=256)),
    prepend_punctuations=(str, Field('\"\'“¿([{-', max_length=128)),
    append_punctuations=(str, Field('\"\'.。,，!！?？:：”)]}、', max_length=128)),
    vad_parameters=(VadParameters | None, Field(default_factory=lambda: VadParameters(min_silence_duration_ms=300))),
)
LiveDecodingOptions = create_model('LiveDecodingOptions', __config__=ConfigDict(extra='forbid', allow_inf_nan=False), **fields)


class LiveOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    decoding: LiveDecodingOptions = Field(default_factory=LiveDecodingOptions)
    interval_seconds: float = Field(0.6, ge=0.2, le=5, description='Minimum received audio between decoding passes.')
    max_context_seconds: float = Field(8, ge=4, le=30, description='Context before trimming confirmed audio; unconfirmed audio is never discarded.')
    segment_no_speech_threshold: float = Field(0.9, ge=0, le=1, description='Discard a decoded segment above this no-speech probability.')

    @model_validator(mode='after')
    def valid_decoding(self):
        validate_audio_options(self.decoding.model_dump(), provider='faster-whisper', model='multilingual', include_word_timestamps=True)
        if self.interval_seconds > self.max_context_seconds:
            raise ValueError('interval_seconds cannot exceed max_context_seconds')
        return self


class LiveCapabilities(BaseModel):
    enabled: bool
    ready: bool
    options_supported: bool = False
    provider: Literal['faster-whisper'] = 'faster-whisper'
    model: str
    languages: list[str]
    protocol: Literal[1] = 1
    max_duration_seconds: int
    options_schema: dict = Field(default_factory=LiveOptions.model_json_schema)
    managed_parameters: dict = Field(default_factory=lambda: dict(MANAGED))
    restrictions: list[str] = Field(default_factory=lambda: [
        'Only transcription with an explicit supported language; translation and automatic language switching are not part of this streaming protocol.',
        'PCM is mono, signed 16-bit little-endian at 16 kHz. Word timestamps, source clock and confirmed-prefix context are managed by the server.',
        'Larger beams or decoding windows increase latency. Backpressure and duration limits still apply.',
        'Audio is not stored. A completed session persists text, segments, subtitles and the requested configuration.',
    ])


def worker_languages(worker):
    if not worker:
        return []
    # Old workers only understand Portuguese and do not accept session options.
    return worker.get('languages', ['pt']) if worker.get('options_protocol') == 1 else ['pt']
