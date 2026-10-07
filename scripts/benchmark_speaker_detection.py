#!/usr/bin/env python3
"""Isolated speaker capability probe. No API calls, jobs, or saved transcripts.

Uses one pinned public tutorial fixture. Dependencies for the optional embeddings
probe are deliberately separate from Ingestify's runtime requirements.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time
import urllib.request

REVISION = "b749285c5cdd4636b2edc7f766f1352c8dde9369"
HASHES = {
    "sample.wav": "c319b4abca767b124e41432d364fd7df006cb26bb79d09326c487d606a134e6e",
    "sample.rttm": "d78fe62c69d8e6dcbb42c26adfce83faccb374c5a1e6d987fe37f85f1c173c87",
}
REFERENCES = [("speaker90", 18.70, 21.40), ("speaker91", 22.00, 24.50)]
HOLDOUT = [
    ("speaker90", 8.40, 9.80), ("speaker90", 11.20, 14.40),
    ("speaker90", 28.60, 30.00), ("speaker91", 14.90, 17.90),
    ("speaker91", 24.60, 27.70),
]


def fixture(directory, download=False):
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in HASHES.items():
        path = directory / name
        if download and not path.exists():
            url = f"https://raw.githubusercontent.com/pyannote/pyannote-audio/{REVISION}/tutorials/assets/{name}"
            path.write_bytes(urllib.request.urlopen(url, timeout=30).read())
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Fixture hash mismatch: {name}")
    labels = {line.split()[7] for line in (directory / "sample.rttm").read_text().splitlines()}
    if labels != {"speaker90", "speaker91"}:
        raise ValueError("Unexpected reference speakers")


def versions(packages):
    return {name: importlib.metadata.version(name) for name in packages}


def current(directory, model_path):
    from workers.engines import whisper_core

    started = time.monotonic()
    model = whisper_core.load_model(model_path, "cpu", "int8")
    load_seconds = time.monotonic() - started
    started = time.monotonic()
    result = whisper_core.transcribe(
        model, directory / "sample.wav",
        {"language": "en", "include_word_timestamps": True, "beam_size": 1},
        model_name="turbo",
    )
    return {
        "model": "turbo", "device": "cpu", "compute_type": "int8",
        "load_seconds": load_seconds, "transcribe_seconds": time.monotonic() - started,
        "audio_duration_seconds": result["duration"],
        "segments": len(result["segments"]), "words": result["word_count"],
        "result_keys": sorted(result),
        "segment_keys": sorted({k for s in result["segments"] for k in s}),
        "word_keys": sorted({k for s in result["segments"] for w in s.get("words", []) for k in w}),
        "speaker_fields_present": any("speaker" in k for s in result["segments"] for k in s),
        "versions": versions(["faster-whisper", "ctranslate2", "numpy"]),
    }


def embeddings(directory):
    import librosa
    import numpy as np
    import soundfile as sf
    import torch
    from resemblyzer import VoiceEncoder, preprocess_wav
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics import adjusted_rand_score

    torch.set_num_threads(2)
    audio, rate = sf.read(directory / "sample.wav", dtype="float32")
    if rate != 16000 or audio.ndim != 1:
        raise ValueError("Expected mono 16 kHz")
    encoder = VoiceEncoder(device="cpu", verbose=False)

    def embed(start, end, shift=0):
        chunk = audio[round(start * rate):round(end * rate)]
        if shift:
            chunk = librosa.effects.pitch_shift(chunk, sr=rate, n_steps=shift)
        return encoder.embed_utterance(preprocess_wav(chunk, source_sr=rate))

    started = time.monotonic()
    refs = np.stack([embed(a, b) for _, a, b in REFERENCES])
    held_embeddings, held_results = [], []
    for speaker, start, end in HOLDOUT:
        value = embed(start, end)
        held_embeddings.append(value)
        scores = value @ refs.T
        predicted = REFERENCES[int(scores.argmax())][0]
        held_results.append({
            "reference_speaker": speaker, "start": start, "end": end,
            "predicted_speaker": predicted, "similarities": scores.tolist(),
            "correct": speaker == predicted,
        })
    clusters = AgglomerativeClustering(
        n_clusters=None, distance_threshold=.35, metric="cosine", linkage="average",
    ).fit_predict(np.stack(held_embeddings))
    pitch = []
    for speaker, start, end in [HOLDOUT[1], HOLDOUT[3]]:
        baseline = embed(start, end)
        for shift in [-2, 2]:
            value = embed(start, end, shift)
            scores = value @ refs.T
            predicted = REFERENCES[int(scores.argmax())][0]
            pitch.append({
                "reference_speaker": speaker, "semitones": shift,
                "predicted_speaker": predicted, "similarities": scores.tolist(),
                "similarity_to_original": float(value @ baseline),
                "correct": speaker == predicted,
            })
    import resemblyzer
    weights = Path(resemblyzer.__file__).parent / "pretrained.pt"
    return {
        "model": "Resemblyzer 0.1.4", "device": "cpu", "sample_rate": rate,
        "audio_seconds": len(audio) / rate,
        "embedding_seconds_including_jit_and_pitch": time.monotonic() - started,
        "reference_intervals": REFERENCES, "holdout": held_results,
        "holdout_accuracy": sum(x["correct"] for x in held_results) / len(held_results),
        "clustering": {
            "algorithm": "average linkage cosine distance threshold 0.35, no supplied speaker count",
            "labels": clusters.tolist(), "clusters": len(set(clusters.tolist())),
            "adjusted_rand_index": adjusted_rand_score([x[0] for x in HOLDOUT], clusters),
        },
        "pitch_control": pitch,
        "versions": versions(["resemblyzer", "librosa", "numpy", "torch", "scikit-learn", "numba", "llvmlite"]),
        "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "current", "embeddings"])
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--model-path")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fixture(args.fixture_dir, download=args.mode == "prepare")
    if args.mode == "prepare":
        result = {"fixture_revision": REVISION, "sha256": HASHES, "reference_speakers": 2}
    elif args.mode == "current":
        if not args.model_path:
            parser.error("current requires --model-path to use an existing offline model")
        result = current(args.fixture_dir, args.model_path)
    else:
        result = embeddings(args.fixture_dir)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        args.output.chmod(0o600)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
