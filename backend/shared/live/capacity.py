"""Account for live residency alongside the existing declared GPU bindings."""
from shared.engines.capacity import VramUse, validate_engine_config
from shared.models import Engine


def require_production_budget(db, settings, gpu):
    engine = db.query(Engine).filter(Engine.slug == 'local').first()
    if engine is None:
        raise RuntimeError('Declare the local GPU and resident workload bindings before enabling live')
    declared = next((g for g in (engine.config or {}).get('gpus', []) if g['ref'] == settings.live_gpu_ref), None)
    if not declared or declared.get('uuid') != gpu['uuid']:
        raise RuntimeError('LIVE_GPU_REF must match the detected GPU UUID in the local inventory')
    uses = validate_engine_config('local', engine.config, settings.vision_model_id)
    use = next((u for u in uses if u.gpu.startswith('GPU ' + settings.live_gpu_ref + ' ')), None)
    if use is None:
        raise RuntimeError('Live GPU budget is unavailable')
    use.used_gb += settings.live_vram_footprint_gb
    use.terms.append(f'live resident {settings.live_vram_footprint_gb:g}')
    use.reserve_gb = max(use.reserve_gb, settings.live_vram_reserve_gb, .2 * use.vram_gb)
    if not use.fits:
        raise RuntimeError('Live model does not fit alongside the declared resident workloads: ' + '; '.join(use.explain()))
    return use
