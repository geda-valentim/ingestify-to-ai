"""Route class that adds Portuguese guidance to coded HTTP errors (0009 CA1).

Routers for engine control, execution profiles, access and IAM use it so every
``{"code": ...}`` refusal — including those raised by router dependencies — also
carries ``message`` and ``next_steps`` from ``shared.error_catalog``. The ``code``
and any other keys are unchanged.
"""

from fastapi import HTTPException
from fastapi.routing import APIRoute

from shared import error_catalog


class GuidedRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guided(request):
            try:
                return await handler(request)
            except HTTPException as exc:
                exc.detail = error_catalog.enrich(exc.detail)
                raise

        return guided
