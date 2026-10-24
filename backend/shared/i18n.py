"""Language negotiation for human-readable API text (P-13).

English is the native/default language; Portuguese (pt-BR) is served when the
client asks for it with ``Accept-Language``. Machine ``code`` values never
change with the language.

The negotiated language lives in a ``ContextVar`` that ``LanguageMiddleware``
sets per request. Text is rendered *at raise time* (``api_error``, ``render``),
so anything that reads ``detail["message"]`` afterwards (route guidance,
``/images`` envelope, ...) sees the right language. Celery tasks and scripts
never set the variable, so they render English.
"""

import contextlib
import contextvars
from typing import Optional

LANGS = ("en", "pt")
DEFAULT = "en"
CONTENT_LANGUAGE = {"en": "en", "pt": "pt-BR"}

_lang: contextvars.ContextVar = contextvars.ContextVar("ingestify_lang", default=DEFAULT)


def negotiate(header: Optional[str]) -> str:
    """The best supported language of an ``Accept-Language`` value (``en`` when none fits)."""
    ranked = []
    for index, part in enumerate(str(header or "").split(",")):
        tag, _, params = part.strip().partition(";")
        tag = tag.strip().lower()
        if not tag:
            continue
        quality = 1.0
        for param in params.split(";"):
            name, _, value = param.partition("=")
            if name.strip().lower() == "q":
                try:
                    quality = float(value.strip())
                except ValueError:
                    quality = 1.0
        if quality <= 0:
            continue
        primary = tag.split("-", 1)[0]
        if primary in LANGS:
            ranked.append((-quality, index, primary))
    return min(ranked)[2] if ranked else DEFAULT


def current_lang() -> str:
    return _lang.get()


@contextlib.contextmanager
def use_lang(lang: str):
    """Render in ``lang`` inside the block (unknown values fall back to English)."""
    token = _lang.set(lang if lang in LANGS else DEFAULT)
    try:
        yield
    finally:
        _lang.reset(token)


def api_error(status_code: int, code: str, *, headers: Optional[dict] = None, **params):
    """An ``HTTPException`` whose detail is ``{"code", "message"}`` in the current language."""
    from fastapi import HTTPException

    from shared.error_catalog import render

    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": render(code, **params)},
        headers=headers,
    )


class LanguageMiddleware:
    """Pure ASGI (not ``BaseHTTPMiddleware``): the context is set in the request's own task."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = b""
        for name, value in scope.get("headers") or []:
            if name == b"accept-language":
                raw = value
                break
        lang = negotiate(raw.decode("latin-1"))
        token = _lang.set(lang)

        async def send_with_language(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                if not any(name.lower() == b"content-language" for name, _ in headers):
                    headers.append((b"content-language", CONTENT_LANGUAGE[lang].encode()))
                vary = [i for i, (name, _) in enumerate(headers) if name.lower() == b"vary"]
                if vary:
                    value = headers[vary[0]][1]
                    if b"accept-language" not in value.lower():
                        headers[vary[0]] = (headers[vary[0]][0], value + b", Accept-Language")
                else:
                    headers.append((b"vary", b"Accept-Language"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_language)
        finally:
            _lang.reset(token)
