"""Public decoding keys; dependency free for local and remote workers."""

FASTER_WHISPER_OPTIONS = frozenset({
    'task', 'language', 'log_progress', 'beam_size', 'best_of', 'patience',
    'length_penalty', 'repetition_penalty', 'no_repeat_ngram_size', 'temperature',
    'compression_ratio_threshold', 'log_prob_threshold', 'no_speech_threshold',
    'condition_on_previous_text', 'prompt_reset_on_temperature', 'initial_prompt',
    'prefix', 'suppress_blank', 'suppress_tokens', 'without_timestamps',
    'max_initial_timestamp', 'word_timestamps', 'prepend_punctuations',
    'append_punctuations', 'multilingual', 'vad_filter', 'vad_parameters',
    'max_new_tokens', 'chunk_length', 'clip_timestamps',
    'hallucination_silence_threshold', 'hotwords', 'language_detection_threshold',
    'language_detection_segments',
})
OPENAI_WHISPER_OPTIONS = frozenset({
    'task', 'language', 'temperature', 'compression_ratio_threshold',
    'logprob_threshold', 'no_speech_threshold', 'condition_on_previous_text',
    'initial_prompt', 'carry_initial_prompt', 'word_timestamps',
    'prepend_punctuations', 'append_punctuations', 'clip_timestamps',
    'hallucination_silence_threshold', 'sample_len', 'best_of', 'beam_size',
    'patience', 'length_penalty', 'prompt', 'prefix', 'suppress_tokens',
    'suppress_blank', 'without_timestamps', 'max_initial_timestamp', 'fp16',
})
OPENAI_API_OPTIONS = frozenset({'task', 'language', 'temperature', 'initial_prompt'})
PROVIDER_OPTIONS = {
    'faster-whisper': FASTER_WHISPER_OPTIONS,
    'openai-whisper': OPENAI_WHISPER_OPTIONS,
    'openai-api': OPENAI_API_OPTIONS,
}


def decoding_kwargs(options, provider):
    """Omitted arguments preserve the installed implementation's defaults."""
    kwargs = {k: v for k, v in options.items() if k in PROVIDER_OPTIONS[provider]}
    kwargs.setdefault('language', None)
    kwargs.setdefault('temperature', 0.0)
    kwargs.setdefault('beam_size', 5)
    kwargs['word_timestamps'] = options.get('include_word_timestamps', False)
    if provider == 'faster-whisper':
        kwargs.setdefault('vad_filter', True)
        kwargs.setdefault('vad_parameters', {'min_silence_duration_ms': 500})
    return kwargs


def clean_remote_options(options):
    """Validate portable requests without importing application settings or Pydantic."""
    import math
    if options is None:
        return {}
    if not isinstance(options, dict):
        raise ValueError('options must be an object')
    boolean_keys = {'include_word_timestamps', 'log_progress', 'condition_on_previous_text',
                    'suppress_blank', 'without_timestamps', 'multilingual', 'vad_filter'}
    integers = {'beam_size': (1, 20), 'best_of': (1, 20), 'no_repeat_ngram_size': (0, 100),
                'max_new_tokens': (1, 448), 'chunk_length': (1, 30), 'language_detection_segments': (1, 100)}
    numbers = {'patience': (0, 10, False), 'length_penalty': (0, 2, True),
               'repetition_penalty': (0, 5, False), 'compression_ratio_threshold': (0, 1e9, False),
               'log_prob_threshold': (-1e9, 1e9, True), 'no_speech_threshold': (0, 1, True),
               'prompt_reset_on_temperature': (0, 1, True), 'max_initial_timestamp': (0, 30, True),
               'hallucination_silence_threshold': (0, 1e9, False), 'language_detection_threshold': (0, 1, True)}

    def number(value, key, low=0, high=1e9, inclusive=True):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{key} must be a finite number')
        if value > high or (value < low if inclusive else value <= low):
            raise ValueError(f'{key} out of range')

    def token_list(value, key):
        if not isinstance(value, list) or len(value) > 10000 or any(type(token) is not int or token < -1 for token in value):
            raise ValueError(f'{key} must be a bounded token list')

    clean = {}
    for key, value in options.items():
        if key not in FASTER_WHISPER_OPTIONS | {'include_word_timestamps', 'operation'} or key == 'word_timestamps':
            continue
        if value is None:
            if key in {'language', 'initial_prompt', 'prefix', 'vad_parameters', 'max_new_tokens', 'chunk_length',
                       'hotwords', 'compression_ratio_threshold', 'log_prob_threshold', 'no_speech_threshold',
                       'hallucination_silence_threshold', 'language_detection_threshold'}:
                if key != 'language': clean[key] = None
                continue
            raise ValueError(f'{key} cannot be null')
        if key in boolean_keys:
            if type(value) is not bool: raise ValueError(f'{key} must be boolean')
        elif key in integers:
            if type(value) is not int: raise ValueError(f'{key} must be integer')
            number(value, key, *integers[key])
        elif key in numbers:
            number(value, key, *numbers[key])
        elif key == 'temperature':
            temperatures = value if isinstance(value, list) else [value]
            if not temperatures or len(temperatures) > 100: raise ValueError('temperature list length')
            for item in temperatures: number(item, key, 0, 1)
        elif key == 'suppress_tokens':
            token_list(value, key)
        elif key == 'initial_prompt' and isinstance(value, list):
            token_list(value, key)
        elif key == 'clip_timestamps':
            try: timestamps = [float(item) for item in value.split(',')] if isinstance(value, str) else value
            except ValueError: raise ValueError('clip_timestamps must contain seconds') from None
            if not isinstance(timestamps, list) or not timestamps or len(timestamps) > 10000:
                raise ValueError('clip_timestamps list length')
            for item in timestamps: number(item, key)
            if any(b < a for a, b in zip(timestamps, timestamps[1:])): raise ValueError('clip_timestamps order')
        elif key == 'vad_parameters':
            bounds = {'threshold': (0, 1), 'neg_threshold': (0, 1), 'min_speech_duration_ms': (0, 1e9),
                      'max_speech_duration_s': (0, 1e9), 'min_silence_duration_ms': (0, 1e9), 'speech_pad_ms': (0, 1e9)}
            if not isinstance(value, dict) or set(value) - set(bounds): raise ValueError('vad_parameters keys')
            for name, item in value.items():
                number(item, name, *bounds[name], inclusive=name != 'max_speech_duration_s')
                if name.endswith('_ms') and type(item) is not int: raise ValueError(f'{name} must be integer')
        elif not isinstance(value, str) or len(value) > 10000:
            raise ValueError(f'{key} must be bounded text')
        if key == 'task' and value not in {'transcribe', 'translate'}: raise ValueError('task not supported')
        if key == 'operation' and value not in {'transcribe', 'detect_language', 'inspect'}: raise ValueError('operation not supported')
        clean[key] = value
    return clean
