"""A shared result contract for language detection and file inspection."""
import json


def media_info(path):
    import av
    with av.open(str(path), metadata_errors='ignore') as container:
        streams = list(container.streams.audio)
        if not streams:
            raise ValueError('Arquivo não contém faixa de áudio')
        stream = streams[0]
        duration = container.duration / av.time_base if container.duration is not None else (
            float(stream.duration * stream.time_base) if stream.duration is not None else 0.0)
        return dict(duration=duration, format=container.format.name, channels=stream.codec_context.channels,
                    sample_rate=stream.codec_context.sample_rate, bitrate=container.bit_rate,
                    size_bytes=path.stat().st_size, codec=stream.codec_context.name,
                    metadata=dict(container.metadata))


def analysis_result(*, operation, info, language=None, probability=None, model, provider):
    text = f'Idioma detectado: {language}' if operation == 'detect_language' else json.dumps(info, ensure_ascii=False, indent=2)
    return dict(text=text, segments=[], language=language, language_probability=probability,
                duration=info.get('duration', 0), word_count=len(text.split()), char_count=len(text),
                model=model, provider=provider, operation=operation, media_info=info)
