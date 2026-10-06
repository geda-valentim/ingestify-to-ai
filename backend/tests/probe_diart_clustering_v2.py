"""Run with the isolated real Diart environment; no model or audio inference.

PYTHONPATH=backend <diart-python> backend/tests/probe_diart_clustering_v2.py
This verifies the pinned library's actual mapping/block API, not DER/latency.
"""
import json
import numpy as np
import torch
from pyannote.core import SlidingWindowFeature, SlidingWindow
from workers.live.diart_clustering import EvidenceClustering
from shared.live.protocol import LiveError

cluster = EvidenceClustering(.6, .3, .5, max_speakers=2)
def identify(scores,vectors):
    return cluster.identify(SlidingWindowFeature(np.array(scores,dtype=float),SlidingWindow(duration=.1,step=.1)),
                            torch.tensor(vectors,dtype=torch.float32)).valid_assignments()
assert identify([[.9,0]]*10,[[1.,0],[0,1.]])==([0],[0])
# Short novel voice must remain unknown, not map to existing nearest center.
assert identify([[0,.9]]+[[0,0]]*9,[[1.,0],[0,1.]])==([],[])
assert cluster.num_known_speakers==1
assert identify([[0,.9]]*10,[[1.,0],[0,1.]])==([1],[1])
assert identify([[.9,0]]*10,[[1.,0],[0,1.]])==([0],[0])
# Invalid embeddings must not invent speakers or contaminate known centers.
assert identify([[.9]]*10,[[float('nan'),0]])==([],[])
try:
    identify([[.9]]*10,[[-1.,0]])
except LiveError as exc:
    assert exc.code=='LIVE_DIARIZATION_SPEAKER_LIMIT'
else:
    raise AssertionError('a third new voice was silently mapped into full catalog')
cluster.clear()
assert cluster.centers is None and not cluster.active_centers
print(json.dumps({'diart_version':'0.9.2','checks':6,'short_novel_voice':'unknown',
                  'reentry':'same ID','catalog_overflow':'explicit error','embedding_cleanup':True,
                  'audio_inference_tested':False}))
