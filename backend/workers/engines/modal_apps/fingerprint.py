"""
The fingerprint of a Modal deploy (spec 0003, 4.11): a hash of everything the
deployed app contains - the source files shipped into the image, the pinned
requirements lock, the protocol version, the model revision and the binding's
decorator (GPU, cpu, memory, timeout, scaledown window, max containers, max
inputs). Any change to one of them makes the engine `needs_redeploy`.

It is a consistency check, not authentication: whoever holds the account's
token can deploy anything under the app name.
"""

import hashlib
import json
from typing import Dict

from shared.engines import pricing
from shared.engines.capacity import Binding
from workers.engines.modal_apps import protocol
from workers.engines.modal_apps.files import BACKEND_DIR, LOCK_FILE, REQUIREMENTS_IN, SOURCE_FILES


def deploy_spec(feature: str, config: dict, binding: Binding) -> Dict[str, object]:
    """What a deploy of this binding puts in the account; its fingerprint covers all of it"""
    spec = {
        "app": protocol.APP_NAME,
        "feature": feature,
        "protocol": protocol.PROTOCOL_VERSION,
        "model": {"repo": protocol.MODEL_REPO, "revision": protocol.MODEL_REVISION,
                  "compute_type": protocol.COMPUTE_TYPE},
        "decorator": pricing.modal_decorator(config, binding),
    }
    spec["fingerprint"] = fingerprint(spec)
    return spec


def fingerprint(spec: Dict[str, object]) -> str:
    digest = hashlib.sha256()
    body = {k: v for k, v in spec.items() if k != "fingerprint"}
    digest.update(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
    for path in SOURCE_FILES + [REQUIREMENTS_IN, LOCK_FILE]:
        digest.update(path.relative_to(BACKEND_DIR).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() if path.exists() else b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def expected_fingerprint(feature: str, config: dict, binding: Binding) -> str:
    return deploy_spec(feature, config, binding)["fingerprint"]
