"""Narrow Diart 0.9.2 clustering extension: abstain instead of nearest fallback.

Uses upstream distance assignment and center updates. Short/invalid embeddings
cannot create a center or be assigned a voice; exhausting slots fails explicitly.
This policy must be qualified with real audio before online admission is enabled.
"""
import numpy as np
from diart.blocks.clustering import OnlineSpeakerClustering
from diart.mapping import SpeakerMapBuilder
from shared.live.protocol import LiveError


class EvidenceClustering(OnlineSpeakerClustering):
    def identify(self, segmentation, embeddings):
        vectors = embeddings.detach().cpu().numpy()
        eligible = np.flatnonzero(
            (np.max(segmentation.data, axis=0) >= self.tau_active)
            & (np.mean(segmentation.data, axis=0) >= self.rho_update)
            & np.isfinite(vectors).all(axis=1)
            & (np.linalg.norm(vectors, axis=1) > 0))
        local = segmentation.data.shape[1]
        if self.centers is None:
            self.init_centers(vectors.shape[1])
        if not len(eligible):
            return SpeakerMapBuilder.hard_map((local, self.max_speakers), [], maximize=False)
        if not self.active_centers:
            if len(eligible) > self.num_free_centers:
                raise LiveError('LIVE_DIARIZATION_SPEAKER_LIMIT', 4429)
            return SpeakerMapBuilder.hard_map((local, self.max_speakers),
                [(int(i), self.add_center(vectors[i])) for i in eligible], maximize=False)
        mapping = SpeakerMapBuilder.dist(vectors, self.centers, self.metric)
        excluded = np.array([i for i in range(local) if i not in eligible], dtype=int)
        mapping = mapping.unmap_speakers(excluded, self.inactive_centers).unmap_threshold(self.delta_new)
        missed = [int(i) for i in eligible if not mapping.is_source_speaker_mapped(i)]
        if len(missed) > self.num_free_centers:
            raise LiveError('LIVE_DIARIZATION_SPEAKER_LIMIT', 4429)
        self.update(zip(*mapping.valid_assignments()), vectors)
        for i in missed:
            mapping = mapping.set_source_speaker(i, self.add_center(vectors[i]))
        return mapping

    def __call__(self, segmentation, embeddings):
        mapped = super().__call__(segmentation, embeddings)
        self.latest = mapped
        return mapped

    def clear(self):
        if self.centers is not None:
            self.centers.fill(0)
        self.centers = None
        self.active_centers.clear()
        self.blocked_centers.clear()
        self.latest = None
