"""Real Pyannote 3/Torch 2.8 checkpoint roundtrip with narrow safe globals.

Random untrained model tests serialization compatibility only; no diarization
quality or gated checkpoint compatibility claim is made by this probe.
"""
import json
import tempfile
from pathlib import Path
import torch
import pytorch_lightning
from pyannote.audio import Model
from pyannote.audio.models.segmentation import PyanNet
from pyannote.audio.core.task import Specifications,Problem,Resolution
from workers.live.diart_process import checkpoint_globals

torch.set_num_threads(2)
model=PyanNet(lstm={'hidden_size':8,'num_layers':1},linear={'hidden_size':8,'num_layers':1})
model.specifications=Specifications(problem=Problem.MULTI_LABEL_CLASSIFICATION,resolution=Resolution.FRAME,
                                    duration=5,classes=['speaker'])
model.build()
checkpoint={'state_dict':model.state_dict(),'hyper_parameters':dict(model.hparams),
            'pytorch-lightning_version':pytorch_lightning.__version__}
model.on_save_checkpoint(checkpoint)
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'random-local.ckpt';torch.save(checkpoint,path)
    # Confirm default loading still rejects custom globals outside the context.
    try:torch.load(path,weights_only=True)
    except Exception:pass
    else:raise AssertionError('probe did not exercise safe-global compatibility')
    with torch.serialization.safe_globals(checkpoint_globals()):
        loaded=Model.from_pretrained(str(path),use_auth_token=False)
    assert type(loaded) is PyanNet
    assert loaded.specifications.classes==['speaker']
    assert all(torch.equal(value,loaded.state_dict()[key]) for key,value in model.state_dict().items())
    with torch.inference_mode():
        scores=loaded(torch.zeros((1,1,80000)))
    assert scores.shape[0]==1 and scores.shape[-1]==1
    try:torch.load(path,weights_only=True)
    except Exception:pass
    else:raise AssertionError('safe globals leaked outside scoped loader')
print(json.dumps({'checkpoint_roundtrip':True,'model':'random untrained PyanNet','torch':torch.__version__,
                  'safe_globals_scoped':True,'real_gated_weights_tested':False}))
