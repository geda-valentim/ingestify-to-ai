"""
BlockwiseFeatureExtractor must produce the same features as faster-whisper's
own FeatureExtractor: it is a memory optimisation, not a behaviour change.
"""

import numpy as np
import pytest

pytest.importorskip("faster_whisper")

from faster_whisper.feature_extractor import FeatureExtractor  # noqa: E402

from workers.audio import feature_extractor as fx  # noqa: E402
from workers.audio.feature_extractor import BlockwiseFeatureExtractor  # noqa: E402

SR = 16000


def _speechlike(seconds: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 0.7 * t)
    return (envelope * (0.3 * np.sin(2 * np.pi * 220 * t) + 0.05 * rng.standard_normal(t.size))).astype(np.float32)


@pytest.mark.parametrize("seconds", [0.5, 29.9, 30.0, 301.37])
@pytest.mark.parametrize("feature_size", [80, 128])
def test_matches_stock_extractor(monkeypatch, seconds, feature_size):
    # Small blocks so even short audio crosses several block boundaries
    monkeypatch.setattr(fx, "BLOCK_FRAMES", 997)
    audio = _speechlike(seconds)

    expected = FeatureExtractor(feature_size=feature_size)(audio, chunk_length=30)
    actual = BlockwiseFeatureExtractor(feature_size=feature_size)(audio, chunk_length=30)

    assert actual.shape == expected.shape
    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-5)


def test_chunk_length_updates_frame_budget_like_stock():
    extractor = BlockwiseFeatureExtractor(feature_size=128)

    extractor(_speechlike(1.0), chunk_length=20)

    assert extractor.n_samples == 20 * SR
    assert extractor.nb_max_frames == 20 * SR // extractor.hop_length


def test_install_replaces_the_model_extractor():
    class Model:
        feat_kwargs = {"feature_size": 128}
        feature_extractor = None

    model = Model()
    fx.install(model)

    assert isinstance(model.feature_extractor, BlockwiseFeatureExtractor)
    assert model.feature_extractor.mel_filters.shape[0] == 128
