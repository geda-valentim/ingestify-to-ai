"""Datalake refusals that carry a catalog code (P-13).

A ``DatalakeError`` is still a ``ValueError`` (pydantic validators and the
callers that catch ``ValueError`` keep working); its text is rendered at raise
time in the request language, and routes turn it into ``{"code", "message"}``
with ``to_http``. Raised outside a request (Celery) it renders English.
"""

from shared.error_catalog import render
from shared.i18n import api_error


class DatalakeError(ValueError):
    def __init__(self, code: str, **params):
        self.code = code
        self.params = params
        super().__init__(render(code, **params))


def to_http(exc: DatalakeError, status: int = 422):
    """The HTTP refusal of a coded datalake error: same code, request-language message."""
    return api_error(status, exc.code, **exc.params)


def datalake_not_found_detail() -> str:
    """The text of the non-disclosure 404: a missing and a foreign connection answer the same."""
    return render("DATALAKE_NOT_FOUND")
