"""Localized refusals for the admin routes (P-13 slice 4).

``refusal`` builds the ``{"code", "message", "next_steps", ...}`` detail of an
``HTTPException`` in the request language. A domain exception's raw text (always
English, as raised by the service layer) goes to ``technical``; ``message`` is the
catalog sentence for the code. Extra keyword arguments are kept as extra keys
(``vram``, ``problems``...).
"""

from typing import Optional

from fastapi import HTTPException

from shared import error_catalog


def refusal(
    status_code: int,
    code: str,
    exc: Optional[BaseException] = None,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    **extra,
) -> HTTPException:
    detail = error_catalog.detail(code, text=str(exc) if exc is not None else None, context=params)
    return HTTPException(status_code=status_code, detail={**extra, **detail}, headers=headers)
