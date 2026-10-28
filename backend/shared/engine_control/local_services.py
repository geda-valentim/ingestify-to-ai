"""Compose services of the local engine per feature (spec 0007), shared by the local adapter
(workers), the profile seed and admission (shared), which cannot import workers."""

SERVICES = {
    "transcription": "worker-audio",
    "document_conversion": "worker",
    "vision": "worker-vision",
    "live-transcription": "worker-live",
}
GENERIC = "worker"  # legacy media can also execute on the generic worker


def admission_services(feature):
    """The services whose resources a feature WITHOUT a runtime profile is admitted on (spec 0007
    §4.6): its canonical service, plus the generic worker for transcription and vision. No GPU
    key: without a profile there is no GPU binding to protect. None for a feature without a
    service here: the caller keeps every row of the engine (no fail-open)."""
    if feature not in SERVICES:
        return None
    names = {SERVICES[feature]}
    if feature in ("transcription", "vision"):
        names.add(GENERIC)
    return names


def is_service_key(key, services=None):
    """`local:<host>:service:<name>` of one of `services` (any service without them), on any
    host (a host id may hold ":")."""
    parts = key.split(":")
    return (len(parts) >= 4 and parts[0] == "local" and parts[-2] == "service"
            and (services is None or parts[-1] in services))


def key_host(key):
    """The host of a local resource key (`local:<host>:<kind>:<name>`), or None for another shape."""
    parts = key.split(":")
    return ":".join(parts[1:-2]) if len(parts) >= 4 and parts[0] == "local" else None
