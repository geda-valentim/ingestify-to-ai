"""Schema 2 semantics shared by file, Modal and downloaded artifacts."""
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest

from shared.transcription import make_profile, normalize_options, profile_hash, options_from_profile
from workers.engines.transcript_schema import normalize_aligned_segments, speaker_for_interval, validate_result
from workers.engines.pipeline import build_transcription_outputs
from workers.engines.modal_apps import protocol


def sample():
    return {'schema_version': 2, 'text': 'Olá mundo', 'language': 'pt', 'duration': 2,
        'word_count': 2, 'char_count': 9, 'provider': 'whisperx', 'model': 'turbo',
        'speakers': [{'id': 'SPEAKER_00', 'label': 'Falante 1'}],
        'diarization': {'status': 'completed', 'speaker_count': 1, 'turns': [
            {'start': 0, 'end': 1, 'speaker_id': 'SPEAKER_00'}]},
        'alignment': {'status': 'completed', 'model': 'fixture'},
        'segments': [{'start': 0, 'end': 2, 'text': 'Olá mundo', 'speaker_id': 'SPEAKER_00',
            'words': [{'word': 'Olá', 'start': 0., 'end': 1., 'alignment_score': .8, 'speaker_id': 'SPEAKER_00'},
                      {'word': 'mundo', 'start': None, 'end': None, 'speaker_id': None}]}]}


def test_tie_and_missing_intersection_never_guess_a_speaker():
    turns = [{'start': 0, 'end': 1, 'speaker_id': 'SPEAKER_00'},
             {'start': 0, 'end': 1, 'speaker_id': 'SPEAKER_01'}]
    assert speaker_for_interval(0, 1, turns) is None
    assert speaker_for_interval(2, 3, turns) is None
    assert speaker_for_interval(None, None, turns) is None
    assert speaker_for_interval(0, 1, turns[:1]) == 'SPEAKER_00'


def test_aligned_speaker_changes_split_but_untimed_words_are_kept():
    turns = [{'start': 0, 'end': 1, 'speaker_id': 'SPEAKER_00'}, {'start': 1, 'end': 2, 'speaker_id': 'SPEAKER_01'}]
    segment = {'start': 0, 'end': 2, 'text': 'Olá mundo', 'words': [
        {'word': 'Olá', 'start': 0, 'end': 1, 'score': .9}, {'word': 'mundo', 'start': 1, 'end': 2}]}
    split = normalize_aligned_segments([segment], turns, expose_words=True)
    assert [row['speaker_id'] for row in split] == ['SPEAKER_00', 'SPEAKER_01']
    assert split[0]['words'][0]['alignment_score'] == .9
    assert 'probability' not in split[0]['words'][0]
    segment['words'][1] = {'word': 'mundo'}
    unsplit = normalize_aligned_segments([segment], turns, expose_words=True)
    assert len(unsplit) == 1 and unsplit[0]['text'] == segment['text']
    assert unsplit[0]['speaker_id'] is None
    assert unsplit[0]['words'][1]['start'] is None


def test_alignment_native_real_scalars_become_json_primitives_before_validation():
    from fractions import Fraction
    # Real scalar subclasses reproduce the strict-type failure without NumPy as
    # a unit-test dependency; the offline runtime probe covers real NumPy output.
    class NativeFloat(float):
        pass
    raw = {'start':NativeFloat(0), 'end':NativeFloat(2), 'text':'Olá mundo', 'words':[
        {'word':'Olá','start':NativeFloat(0),'end':NativeFloat(1),'score':Fraction(4,5)},
        {'word':'mundo'}]}
    result = sample()
    result['segments'] = normalize_aligned_segments([raw], result['diarization']['turns'], expose_words=True)
    validate_result(result)
    segment = result['segments'][0]
    assert type(segment['start']) is float and type(segment['end']) is float
    word = segment['words'][0]
    assert type(word['start']) is float and type(word['end']) is float
    assert type(word['alignment_score']) is float and word['alignment_score'] == .8
    assert segment['words'][1]['start'] is None
    assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize('value', [True, '0.1', object(), float('nan'), float('inf'), -0.1])
def test_alignment_scalar_conversion_does_not_coerce_invalid_types(value):
    with pytest.raises(ValueError, match='INVALID_ALIGNMENT_NUMBER'):
        normalize_aligned_segments([{'start':0,'end':1,'text':'a','words':[
            {'word':'a','start':value,'end':1}]}], [], expose_words=True)


@pytest.mark.parametrize('change', [
    lambda r: r['segments'][0].update(speaker_id='SPEAKER_19'),
    lambda r: r['segments'][0]['words'][0].update(start=float('nan')),
    lambda r: r['diarization'].update(speaker_count=2),
    lambda r: r['diarization']['turns'][0].update(end=3),
    lambda r: r['segments'][0]['words'][1].update(speaker_id='SPEAKER_00'),
])
def test_invalid_payloads_rejected(change):
    result = sample()
    change(result)
    with pytest.raises(ValueError):
        validate_result(result)


def test_formats_and_modal_preserve_nullable_words_and_speakers():
    result = sample()
    payload, outputs = build_transcription_outputs(result, options={}, input_metadata={}, processing_seconds=1, compute_type='int8')
    assert json.loads(outputs['json'])['segments'] == result['segments']
    for fmt in ('srt', 'vtt', 'txt'):
        assert 'Falante 1: Olá mundo' in outputs[fmt]
    assert 'Falante 1: Olá mundo' in payload['markdown']
    usage = dict(exec_started_unix=1, exec_ended_unix=2, exec_seconds=1, cold_start_seconds=0,
                 container_id='test', protocol=protocol.PROTOCOL_VERSION)
    clean, _ = protocol.parse_response(protocol.build_response(result, usage))
    assert clean['segments'] == result['segments']
    assert clean['language_probability'] is None
    assert clean['diarization'] == result['diarization']


def settings(**kwargs):
    return SimpleNamespace(audio_transcriber_provider='whisperx', whisperx_diarization_default=True,
                           whisper_model='turbo', **kwargs)


def test_profiles_change_with_capability_and_survive_server_defaults():
    conf = settings()
    profile = make_profile(conf, {'language': 'pt'})
    disabled = make_profile(conf, {'language': 'pt', 'diarize': False})
    assert profile_hash(profile) != profile_hash(disabled)
    assert profile_hash(profile) == profile_hash(make_profile(conf, {'language': 'pt', 'output_format': 'srt'}))
    assert options_from_profile(profile, {'diarize': False})['diarize'] is True
    conf.audio_transcriber_provider = 'faster-whisper'
    assert not normalize_options(conf)['diarize']
    with pytest.raises(ValueError, match='UNSUPPORTED_PROVIDER'):
        normalize_options(conf, {'diarize': True})


@pytest.mark.parametrize('options', [{'min_speakers': True}, {'max_speakers': 21},
    {'min_speakers': 3, 'max_speakers': 2}, {'diarize': False, 'min_speakers': 1}])
def test_invalid_speaker_options(options):
    with pytest.raises(ValueError):
        normalize_options(settings(), options)
