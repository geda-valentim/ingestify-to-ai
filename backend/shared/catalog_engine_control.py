"""Bilingual texts of engine-control codes (spec 0007) added after ``error_catalog`` passed its
size cap: a new domain gets its own module.

Same shape as ``catalog_api.API_CATALOG`` (``code -> ({"en", "pt"}, next_steps)``), merged
into ``error_catalog.CATALOG`` at import. Literal texts, no parameters.
"""

ENGINE_CONTROL_CATALOG = {
    "IDLE_WORK_ARRIVED": (
        {
            "en": "The automatic cooldown did not run: work for this service arrived after it was "
                  "found idle. The idle policy tries again after the next idle period.",
            "pt": "O desligamento automático não rodou: chegou trabalho para este serviço depois que "
                  "ele foi visto ocioso. A política de ociosidade tenta de novo no próximo período ocioso.",
        },
        [],
    ),
}
