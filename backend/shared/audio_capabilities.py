"""Validated audio requests and provider-specific, discoverable parameters."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from shared.audio_decoding import PROVIDER_OPTIONS


# Snapshot of faster-whisper 1.2.1 tokenizer._LANGUAGE_CODES. Keep the API free
# of native inference imports; tests compare this list with the pinned package.
WHISPER_LANGUAGE_CODES = (
    'af', 'am', 'ar', 'as', 'az', 'ba', 'be', 'bg', 'bn', 'bo', 'br', 'bs', 'ca', 'cs',
    'cy', 'da', 'de', 'el', 'en', 'es', 'et', 'eu', 'fa', 'fi', 'fo', 'fr', 'gl', 'gu',
    'ha', 'haw', 'he', 'hi', 'hr', 'ht', 'hu', 'hy', 'id', 'is', 'it', 'ja', 'jw', 'ka',
    'kk', 'km', 'kn', 'ko', 'la', 'lb', 'ln', 'lo', 'lt', 'lv', 'mg', 'mi', 'mk', 'ml',
    'mn', 'mr', 'ms', 'mt', 'my', 'ne', 'nl', 'nn', 'no', 'oc', 'pa', 'pl', 'ps', 'pt',
    'ro', 'ru', 'sa', 'sd', 'si', 'sk', 'sl', 'sn', 'so', 'sq', 'sr', 'su', 'sv', 'sw',
    'ta', 'te', 'tg', 'th', 'tk', 'tl', 'tr', 'tt', 'uk', 'ur', 'uz', 'vi', 'yi', 'yo',
    'zh', 'yue',
)


def local_whisper_languages(model):
    model = model.lower()
    if model.endswith('.en'):
        return ('en',)
    # Cantonese was added in large-v3. Unknown/custom checkpoints may use the
    # latest vocabulary; exact readiness for those remains the worker's concern.
    if model in {'tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2', 'distil-large-v2', 'distil-medium.en', 'distil-small.en'}:
        return WHISPER_LANGUAGE_CODES[:-1]
    return WHISPER_LANGUAGE_CODES

Temperature = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
PromptText = Annotated[str, Field(max_length=10000)]
PromptTokens = Annotated[list[Annotated[int, Field(ge=0)]], Field(max_length=10000)]
ClipSeconds = Annotated[float, Field(ge=0, le=1e9, allow_inf_nan=False)]


class VadParameters(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    threshold: float = Field(0.5, ge=0, le=1)
    neg_threshold: float | None = Field(None, ge=0, le=1)
    min_speech_duration_ms: int = Field(0, ge=0, le=1_000_000_000)
    max_speech_duration_s: float | None = Field(None, gt=0, le=1e9, description='Omitir para duração ilimitada.')
    min_silence_duration_ms: int = Field(500, ge=0, le=1_000_000_000)
    speech_pad_ms: int = Field(400, ge=0, le=1_000_000_000)


class AudioDecodingOptions(BaseModel):
    """Controles públicos dos providers. Consulte /audio/capabilities antes de enviar."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    task: Literal['transcribe', 'translate'] = 'transcribe'
    language: str | None = Field(None, pattern=r'^[a-z]{2,3}$', description='Idioma da gravação; omitido detecta automaticamente.')
    log_progress: bool = False
    beam_size: int | None = Field(5, ge=1, le=20)
    best_of: int | None = Field(5, ge=1, le=20)
    patience: float | None = Field(1, gt=0, le=10)
    length_penalty: float | None = Field(1, ge=0, le=2)
    repetition_penalty: float = Field(1, gt=0, le=5)
    no_repeat_ngram_size: int = Field(0, ge=0, le=100)
    temperature: Temperature | Annotated[list[Temperature], Field(min_length=1, max_length=100)] = 0.0
    compression_ratio_threshold: float | None = Field(2.4, gt=0, le=1e9)
    log_prob_threshold: float | None = Field(-1.0, ge=-1e9, le=1e9)
    logprob_threshold: float | None = Field(-1.0, description='Nome do controle no provider openai-whisper.')
    no_speech_threshold: float | None = Field(0.6, ge=0, le=1)
    condition_on_previous_text: bool = True
    prompt_reset_on_temperature: float = Field(0.5, ge=0, le=1)
    initial_prompt: PromptText | PromptTokens | None = Field(None, description='Contexto textual; tokens numéricos somente no faster-whisper.')
    carry_initial_prompt: bool = False
    prompt: PromptText | PromptTokens | None = None
    prefix: PromptText | PromptTokens | None = None
    suppress_blank: bool = True
    suppress_tokens: PromptText | list[Annotated[int, Field(ge=-1)]] = Field(default_factory=lambda: [-1], max_length=10000)
    without_timestamps: bool = False
    max_initial_timestamp: float = Field(1, ge=0, le=30)
    prepend_punctuations: str = '\"\'“¿([{-'
    append_punctuations: str = '\"\'.。,，!！?？:：”)]}、'
    multilingual: bool = False
    vad_filter: bool = True
    vad_parameters: VadParameters | None = Field(default_factory=VadParameters)
    max_new_tokens: int | None = Field(None, ge=1, le=448)
    sample_len: int | None = Field(None, ge=1, le=448)
    chunk_length: int | None = Field(None, ge=1, le=30)
    clip_timestamps: Annotated[str, Field(max_length=10000)] | Annotated[list[ClipSeconds], Field(min_length=1, max_length=10000)] = '0'
    hallucination_silence_threshold: float | None = Field(None, gt=0, le=1e9)
    hotwords: str | None = Field(None, max_length=10000)
    language_detection_threshold: float | None = Field(0.5, ge=0, le=1)
    language_detection_segments: int = Field(1, ge=1, le=100)
    fp16: bool = True

    @model_validator(mode='after')
    def check_sequences(self):
        if isinstance(self.temperature, list) and not self.temperature:
            raise ValueError('temperature precisa conter ao menos um valor')
        if isinstance(self.clip_timestamps, str):
            try:
                timestamps = [float(x) for x in self.clip_timestamps.split(',')]
            except ValueError:
                raise ValueError('clip_timestamps deve conter segundos separados por vírgula') from None
        else:
            timestamps = self.clip_timestamps
        import math
        if not timestamps or any(not math.isfinite(x) or x < 0 or x > 1e9 for x in timestamps):
            raise ValueError('clip_timestamps deve conter segundos finitos e não negativos')
        if any(b < a for a, b in zip(timestamps, timestamps[1:])):
            raise ValueError('clip_timestamps deve estar em ordem crescente')
        return self


def validate_audio_options(options, *, provider, model, include_word_timestamps=False):
    parsed = AudioDecodingOptions.model_validate(options)
    unsupported = parsed.model_fields_set - PROVIDER_OPTIONS[provider]
    if unsupported:
        raise ValueError(f'{provider} não aceita: {", ".join(sorted(unsupported))}')
    if parsed.task == 'translate' and ('turbo' in model.lower() or model.lower().endswith('.en')):
        raise ValueError(f'O modelo {model} não suporta tradução; configure um modelo multilíngue treinado para tradução.')
    if model.lower().endswith('.en') and parsed.language not in (None, 'en'):
        raise ValueError(f'O modelo {model} aceita somente inglês')
    if provider != 'openai-api' and parsed.language is not None and parsed.language not in local_whisper_languages(model):
        raise ValueError(f'Idioma {parsed.language} não é suportado pelo modelo {model}')
    if parsed.without_timestamps and include_word_timestamps:
        raise ValueError('without_timestamps é incompatível com timestamps de palavras')
    if provider == 'openai-api':
        if isinstance(parsed.temperature, list) or isinstance(parsed.initial_prompt, list):
            raise ValueError('openai-api aceita temperature numérica e initial_prompt textual')
        if parsed.task == 'translate' and include_word_timestamps:
            raise ValueError('whisper-1 translations não fornece timestamps de palavras')
    if provider == 'openai-whisper' and isinstance(parsed.initial_prompt, list):
        raise ValueError('openai-whisper aceita initial_prompt textual')
    if provider == 'faster-whisper' and (isinstance(parsed.prefix, list) or isinstance(parsed.suppress_tokens, str)):
        raise ValueError('faster-whisper aceita prefix textual e suppress_tokens como lista de tokens')
    if provider == 'faster-whisper' and any(getattr(parsed, key) is None for key in ('beam_size', 'best_of', 'patience', 'length_penalty')):
        raise ValueError('faster-whisper exige beam_size, best_of, patience e length_penalty numéricos')
    output = {k: v for k, v in parsed.model_dump().items() if k in PROVIDER_OPTIONS[provider]}
    if provider == 'openai-whisper':
        for key in ('best_of', 'patience', 'length_penalty'):
            if key not in parsed.model_fields_set:
                output[key] = None
    if output.get('vad_parameters'):
        output['vad_parameters'] = {k: v for k, v in output['vad_parameters'].items() if v is not None}
    return output


def validate_audio_operation(decoding, operation):
    if operation == 'detect_language' and decoding.get('language'):
        raise ValueError('Detecção de idioma exige language omitido')
    if operation != 'transcribe' and decoding.get('task', 'transcribe') != 'transcribe':
        raise ValueError('task=translate exige operation=transcribe')


class AudioConversionOptions(BaseModel):
    """The same audio controls for uploads, external sources and bucket imports."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    operation: Literal['transcribe', 'detect_language', 'inspect'] = 'transcribe'
    decoding: AudioDecodingOptions = Field(default_factory=AudioDecodingOptions)
    include_timestamps: bool = True
    include_word_timestamps: bool = False
    output_format: Literal['markdown', 'vtt', 'srt', 'txt', 'json'] = 'markdown'
    purge_source: bool = False

    def resolve(self, settings):
        provider = settings.audio_transcriber_provider
        model = 'whisper-1' if provider == 'openai-api' else settings.whisper_model
        decoding = validate_audio_options(self.decoding.model_dump(exclude_unset=True),
            provider=provider, model=model, include_word_timestamps=self.include_word_timestamps)
        validate_audio_operation(decoding, self.operation)
        options = {**decoding, **self.model_dump(exclude={'decoding'})}
        return provider, model, options


class AudioCapabilitiesResponse(BaseModel):
    enabled: bool
    provider: str
    model: str
    tasks: list[str]
    operations: list[str] = ['transcribe', 'detect_language', 'inspect']
    formats: list[str] = ['markdown', 'vtt', 'srt', 'txt', 'json']
    max_audio_size_mb: int
    max_video_size_mb: int
    parameters_schema: dict
    restrictions: list[str]
    workers_running: bool | None = Field(None, description='Heartbeat de workers; não representa vaga livre. A fila continua aceitando jobs quando pausada.')
    execution_reason: str | None = None


def audio_capabilities(settings):
    provider = settings.audio_transcriber_provider
    model = 'whisper-1' if provider == 'openai-api' else settings.whisper_model
    tasks = ['transcribe']
    restrictions = []
    if 'turbo' in model.lower() or model.lower().endswith('.en'):
        restrictions.append(f'{model} não suporta tradução.')
    else:
        tasks.append('translate')
    schema = AudioDecodingOptions.model_json_schema()
    schema['properties'] = {k: v for k, v in schema['properties'].items() if k in PROVIDER_OPTIONS[provider]}
    schema['properties']['task']['enum'] = tasks
    if provider != 'openai-api':
        schema['properties']['language']['enum'] = [None, *local_whisper_languages(model)]
    if provider == 'openai-whisper':
        for key in ('best_of', 'patience', 'length_penalty'):
            schema['properties'][key]['default'] = None
    if provider == 'openai-api':
        schema['properties']['temperature'] = {'type': 'number', 'minimum': 0, 'maximum': 1, 'default': 0, 'title': 'Temperature'}
        schema['properties']['initial_prompt'] = {'type': 'string', 'title': 'Initial Prompt'}
        restrictions.extend(['Tradução retorna texto em inglês; timestamps de palavras só na transcrição.',
                             'Detecção de idioma usa uma transcrição e não fornece probabilidades.',
                             'Limite do provider: 25 MB; chamadas externas exigem OPENAI_API_KEY.'])
    return AudioCapabilitiesResponse(enabled=settings.enable_audio_transcription, provider=provider, model=model,
        tasks=tasks, max_audio_size_mb=min(settings.max_audio_file_size_mb, 25) if provider == 'openai-api' else settings.max_audio_file_size_mb,
        max_video_size_mb=min(settings.max_video_file_size_mb, 25) if provider == 'openai-api' else settings.max_video_file_size_mb,
        parameters_schema=schema, restrictions=restrictions)
