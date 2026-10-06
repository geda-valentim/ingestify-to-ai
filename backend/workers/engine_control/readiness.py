"""Readiness belongs to each execution child, not the Celery parent heartbeat."""

import json
import os
from pathlib import Path
import tempfile
import threading
import time

_lock = threading.RLock()
_ready = None
ROOT = Path("/tmp/ingestify-runtime")


def pdf_fixture():
    stream = b"BT /F1 12 Tf 30 60 Td (Ingestify readiness) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for n, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(n).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n"
    for pos in offsets[1:]:
        data += f"{pos:010d} 00000 n \n".encode()
    return (
        data
        + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )


def ensure():
    global _ready
    revision = os.environ.get("INGESTIFY_RUNTIME_REVISION")
    feature = os.environ.get("INGESTIFY_RUNTIME_FEATURE")
    if not revision or not feature:
        return None
    with _lock:
        if _ready:
            return _ready
        ROOT.mkdir(exist_ok=True)
        path = ROOT / f"{os.getpid()}.json"
        base = {
            "pid": os.getpid(),
            "revision": revision,
            "feature": feature,
            "profile": os.environ["INGESTIFY_MODEL_PROFILE"],
            "observed_at": time.time(),
            "ready": False,
        }
        path.write_text(json.dumps(base))
        if feature in ("transcription", "live-transcription"):
            from workers.audio.factory import get_audio_transcriber

            transcriber = get_audio_transcriber()
            import wave

            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "probe.wav"
                with wave.open(str(p), "wb") as f:
                    f.setnchannels(1)
                    f.setsampwidth(2)
                    f.setframerate(16000)
                    f.writeframes(b"\0\0" * 16000)
                transcriber.transcribe(p, {"language": "pt"})
            base["device"] = transcriber.device
        elif feature == "document_conversion":
            from workers.converter import get_converter
            from shared.device import resolve_docling_device

            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "probe.pdf"
                p.write_bytes(pdf_fixture())
                result = get_converter().convert_to_markdown(p, {})
                if not result:
                    raise RuntimeError("Document probe failed")
            base["device"] = resolve_docling_device()
        elif feature == "vision":
            from workers.vision.factory import get_image_describer
            from PIL import Image

            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "probe.png"
                Image.new("RGB", (64, 64), "white").save(p)
                describer = get_image_describer()
                describer.describe(p, {"task": "<CAPTION>"})
            base["device"] = describer.device
        else:
            raise RuntimeError("Unsupported readiness feature")
        expected = os.environ.get("INGESTIFY_EXPECTED_DEVICE", "cpu")
        if expected == "cuda" and not str(base["device"]).startswith("cuda"):
            raise RuntimeError("Model fell back from the required CUDA device")
        base.update(ready=True, observed_at=time.time())
        path.write_text(json.dumps(base))
        _ready = base
        return base


def snapshot():
    results = []
    if ROOT.exists():
        for p in ROOT.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                os.kill(data["pid"], 0)
                results.append(data)
            except (OSError, ValueError):
                pass
    return results


def install():
    from celery.signals import worker_process_init

    @worker_process_init.connect(weak=False)
    def start(**kwargs):
        if os.environ.get("INGESTIFY_RUNTIME_REVISION"):
            threading.Thread(target=ensure, daemon=True).start()


if __name__ == "__main__":
    print(json.dumps(snapshot()))
