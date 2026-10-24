"""
Job completion webhook: the caller's signing secret (docs/features/webhooks.md).

`callback_url` itself is a form field of /upload, /convert and /transcribe
(api/routes.py); the delivery is shared/webhooks.py + workers/webhook_tasks.py.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.iam_deps import require
from shared import webhooks
from shared.models import User

router = APIRouter(tags=["Conversion"])


class SigningSecretResponse(BaseModel):
    secret: str


@router.get("/webhooks/signing-secret", response_model=SigningSecretResponse,
            summary="Segredo de assinatura dos webhooks")
async def get_signing_secret(current_user: User = Depends(require("jobs.create"))):
    """
    Segredo com que o receptor verifica o cabeçalho `X-Ingestify-Signature` dos
    webhooks de conclusão (`callback_url`). Um por usuário, estável: não há como
    gerar outro nem como lê-lo de volta pelos eventos. Trate como senha.

    A assinatura é `HMAC-SHA256(secret, "{t}.{corpo}")` em hexadecimal, com `t` o
    timestamp (segundos) do cabeçalho `t=<t>,v1=<hex>`. Recuse eventos com `t`
    muito antigo (ex.: mais de 5 minutos). Exemplos em Python e Node:
    docs/features/webhooks.md.
    """
    return SigningSecretResponse(secret=webhooks.signing_secret(current_user.id))
