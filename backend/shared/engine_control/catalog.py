"""Approved profiles use existing loaders, never browser supplied code or repos."""

from shared.config import get_settings


def profiles():
    s = get_settings()
    from workers.engines.modal_apps import protocol

    builtins = [
        dict(
            id="whisper-turbo-modal",
            title="Whisper turbo / Modal",
            feature="transcription",
            adapters=["modal"],
            backend="faster-whisper",
            model=protocol.MODEL_REPO,
            revision=protocol.MODEL_REVISION,
            compute_type=protocol.COMPUTE_TYPE,
            footprint_gb=3.0,
            device="cuda",
            approved=True,
        ),
        dict(
            id="whisper-local",
            title=f"Whisper {s.whisper_model}",
            feature="transcription",
            adapters=["local"],
            backend=s.audio_transcriber_provider,
            model=s.whisper_model,
            footprint_gb=3.0 if s.whisper_model == "turbo" else None,
            device="cuda",
            approved=s.audio_transcriber_provider == "faster-whisper",
        ),
        dict(
            id="docling-local",
            title="Docling",
            feature="document_conversion",
            adapters=["local"],
            backend="docling",
            model="installed",
            footprint_gb=1.5,
            device="cuda",
            approved=True,
        ),
        dict(
            id="vision-local",
            title=s.vision_model_id,
            feature="vision",
            adapters=["local"],
            backend=s.vision_provider,
            model=s.vision_model_id,
            revision=s.vision_model_revision,
            footprint_gb=1.8 if s.vision_model_id.endswith("base") else 3.8,
            device="cuda",
            approved=s.vision_provider == "florence2" and s.enable_image_description,
        ),
        dict(
            id="live-local",
            title=f"Live Whisper {s.whisper_model}",
            feature="live-transcription",
            adapters=["local"],
            backend="faster-whisper",
            model=s.whisper_model,
            footprint_gb=s.live_vram_footprint_gb,
            device="cuda",
            approved=s.live_transcription_enabled,
        ),
    ]
    from shared.engine_control.registry import descriptors

    # Additional providers ship approved model metadata with their reviewed
    # descriptor; the browser cannot register code, repositories or profiles.
    extras = [
        profile
        for descriptor in descriptors()
        for profile in descriptor.get("model_profiles", [])
    ]
    return builtins + extras


def get(profile_id, adapter_type, feature):
    p = next((p for p in profiles() if p["id"] == profile_id), None)
    if (
        not p
        or not p["approved"]
        or adapter_type not in p["adapters"]
        or feature != p["feature"]
    ):
        raise ValueError("MODEL_PROFILE_UNAVAILABLE")
    return p
