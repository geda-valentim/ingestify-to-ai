"""
The Modal app `ingestify-whisper` (spec 0003, 4.11) - the deploy target.

Deployed only by the CLI, from worker-remote, with the engine's credentials in
a from-scratch environment:

    python scripts/engines.py modal-deploy --engine modal_1

which runs `python -m modal deploy -m workers.engines.modal_apps.whisper_app`
with INGESTIFY_MODAL_DEPLOY set to the deploy spec (fingerprint.deploy_spec):
the binding's decorator (GPU, cpu, memory, timeout, scaledown window, max
containers) and the fingerprint. The spec is baked into the image, so the
container's own import of this file builds the same classes.

    meta()                   CPU only, no GPU: protocol and fingerprint, to verify a deploy
    WhisperRunner.transcribe one request (bytes + options) -> result + usage; with
                             `live`, decoded segments also go to the live Queue (protocol 3)

Never min_containers > 0 (an idle GPU is billed), retries=0 (the backlog decides
what a failure means), one input per container until gates T4/T8 pass (E=1).
"""

import json
import os
import time

import modal

from workers.engines.modal_apps import protocol, runner
from workers.engines.modal_apps.files import ALLOW_UNHASHED_ENV, DEPLOY_ENV
from workers.engines.modal_apps.image import build_image

SPEC = json.loads(os.environ[DEPLOY_ENV])
DECORATOR = SPEC["decorator"]
FINGERPRINT = SPEC["fingerprint"]

app = modal.App(protocol.APP_NAME, include_source=False)
image = build_image(SPEC, allow_unhashed=os.environ.get(ALLOW_UNHASHED_ENV) == "1"
                    or not modal.is_local())


@app.function(image=image, cpu=0.25, memory=512, timeout=60, max_containers=1, min_containers=0, retries=0)
def meta() -> dict:
    """What is deployed, without touching a GPU (the deploy CLI verifies it)"""
    return {
        "app": protocol.APP_NAME,
        "protocol": protocol.PROTOCOL_VERSION,
        "fingerprint": FINGERPRINT,
        "decorator": DECORATOR,
        "model_revision": protocol.MODEL_REVISION,
    }


def _cls_options() -> dict:
    return {
        "image": image,
        "gpu": DECORATOR["gpu"],
        "cpu": DECORATOR["cpu"],
        "memory": DECORATOR["memory_mib"],
        "timeout": DECORATOR["timeout"],
        "scaledown_window": DECORATOR["scaledown_window"],
        "max_containers": DECORATOR["max_containers"],
        "min_containers": 0,
        "retries": 0,
    }


class WhisperRunner:
    """One Whisper model per container, loaded once; one input at a time (E=1)"""

    @modal.enter()
    def load(self):
        started = time.time()
        from workers.engines import whisper_core

        self.model = whisper_core.load_model(protocol.MODEL_DIR, "cuda", protocol.COMPUTE_TYPE)
        self.cold_start_seconds = time.time() - started
        self.first_input = True
        self.container_id = runner.container_id()
        self.state = modal.Dict.from_name(protocol.STATE_DICT, create_if_missing=True)
        self.live = modal.Queue.from_name(protocol.LIVE_QUEUE, create_if_missing=True)

    @modal.method()
    def transcribe(self, request: dict) -> dict:
        cold = self.cold_start_seconds if self.first_input else 0.0
        self.first_input = False
        return runner.handle(
            request, model=self.model, state=self.state, container_id=self.container_id,
            call_id=modal.current_function_call_id(), cold_start_seconds=cold, gpu=DECORATOR["gpu"],
            fingerprint=FINGERPRINT, live=self.live,
        )


if DECORATOR.get("max_inputs", 1) > 1:  # slice 4d, behind gates T4/T8; refused by validation until then
    WhisperRunner = modal.concurrent(max_inputs=DECORATOR["max_inputs"])(WhisperRunner)
WhisperRunner = app.cls(**_cls_options())(WhisperRunner)
