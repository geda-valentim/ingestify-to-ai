"""
Memory-bounded log-Mel spectrogram for faster-whisper

faster-whisper computes the spectrogram of the whole recording in one go, and
its intermediates (complex STFT, magnitudes, mel, log) scale with the audio
length: ~2.4 GB peak for 45 min, several GB for multi-hour lectures. Every
STFT frame depends only on its own n_fft samples and the only global step is
the final max-clamp, so the same features can be built block by block into one
preallocated float32 array. Transcription itself still sees the whole audio.
"""

import numpy as np
from faster_whisper.feature_extractor import FeatureExtractor

# 30,000 frames = 5 min of audio per block (~150 MB of intermediates)
BLOCK_FRAMES = 30_000


class BlockwiseFeatureExtractor(FeatureExtractor):
    """Drop-in FeatureExtractor whose peak memory does not grow with the audio"""

    def __call__(self, waveform: np.ndarray, padding=160, chunk_length=None):
        if chunk_length is not None:
            self.n_samples = chunk_length * self.sampling_rate
            self.nb_max_frames = self.n_samples // self.hop_length

        waveform = waveform.astype(np.float32, copy=False)
        if padding:
            waveform = np.pad(waveform, (0, padding))

        # Same framing as FeatureExtractor.stft(center=True): reflect-pad both
        # ends, one frame per hop, and the last frame dropped
        half = self.n_fft // 2
        padded = np.pad(waveform, (half, half), mode="reflect")
        n_frames = len(waveform) // self.hop_length

        window = np.hanning(self.n_fft + 1)[:-1].astype("float32")
        log_spec = np.empty((self.mel_filters.shape[0], n_frames), dtype=np.float32)

        for start in range(0, n_frames, BLOCK_FRAMES):
            end = min(start + BLOCK_FRAMES, n_frames)
            block = padded[start * self.hop_length:(end - 1) * self.hop_length + self.n_fft]
            stft = self.stft(
                block,
                self.n_fft,
                self.hop_length,
                window=window,
                center=False,
                return_complex=True,
            ).astype("complex64")
            magnitudes = np.abs(stft) ** 2
            mel_spec = self.mel_filters @ magnitudes
            log_spec[:, start:end] = np.log10(np.clip(mel_spec, a_min=1e-10, a_max=None))

        np.maximum(log_spec, log_spec.max() - 8.0, out=log_spec)
        log_spec += 4.0
        log_spec /= 4.0
        return log_spec


def install(model) -> None:
    """Swap a WhisperModel's feature extractor for the blockwise one"""
    model.feature_extractor = BlockwiseFeatureExtractor(**model.feat_kwargs)
