"""How an execution profile revision is shown by the API (spec 0009)."""


def revision_view(r):
    return dict(
        id=r.id,
        revision=r.revision,
        settings=r.settings,
        warm_for_seconds=r.warm_for_seconds,
        model_fingerprint=r.model_fingerprint,
        content_hash=r.content_hash,
        published_at=r.published_at,
    )
