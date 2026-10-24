# Webhook de conclusão de job

`POST /upload`, `POST /convert` e `POST /transcribe` aceitam o campo `callback_url`. Quando o
job principal termina, a plataforma envia um `POST` assinado a essa URL, em vez de você
consultar `GET /jobs/{job_id}` em loop. Disponível desde a API 1.7.0.

Fora do escopo desta versão: as rotas `/images/*`, a análise facial e as sessões ao vivo;
eventos dos jobs filhos (`SPLIT`, `PAGE`, `MERGE`); rotação do segredo; endpoint de log de
entregas; reenvio manual.

## Como pedir

```bash
curl -X POST http://localhost:8000/upload \
  -H "X-API-Key: <chave>" \
  -F "file=@contrato.pdf" -F "project=Cliente X" \
  -F "callback_url=https://app.exemplo.com/hooks/ingestify"
```

A URL é validada antes de qualquer arquivo ser gravado. Recusa com `422`
`{"detail": {"code": "INVALID_CALLBACK_URL", "message": "..."}}` quando:

- o esquema não é `https` (`http` só com `WEBHOOK_ALLOW_HTTP=true`, para desenvolvimento);
- não há host, ou há usuário/senha na URL, ou a URL passa de 2048 caracteres;
- o host é um IP literal que não é público (loopback, rede privada, link-local como o
  `169.254.169.254` dos metadados de nuvem, CGNAT, reservados);
- o host é `localhost`, tem um só rótulo (`redis`, `minio`) ou termina em `.local`,
  `.internal`, `.localhost`.

Nomes que resolvem para endereço privado só podem ser vistos na hora do envio: a entrega é
recusada ali (`last_error: CALLBACK_URL_NOT_PUBLIC`), sem abrir conexão. O fragmento (`#...`)
é descartado.

Arquivo repetido no mesmo projeto: o job existente é devolvido (`duplicate: true`) e passa a
notificar a URL do último pedido; se já terminou, o evento sai na hora. Repetir o pedido com
a mesma URL não envia de novo.

## O evento

Um `POST` com `Content-Type: application/json` e corpo compacto. Só metadados: o Markdown
nunca vai no corpo, busque-o em `GET /jobs/{job_id}/result` com as suas credenciais.

```json
{
  "id": "101905a7-fbd8-5767-9551-ce015c181744",
  "event": "job.completed",
  "created": 1790845200,
  "data": {
    "job_id": "11111111-2222-4333-8444-555555555555",
    "status": "completed",
    "name": "contrato.pdf",
    "type": "main",
    "project_id": "…", "folder_id": null,
    "created_at": "2026-10-01T08:00:00", "completed_at": "2026-10-01T09:00:00",
    "total_pages": 12, "pages_completed": 12, "pages_failed": 0,
    "error": null,
    "result_url": "/jobs/11111111-2222-4333-8444-555555555555/result"
  }
}
```

| `event` | Quando |
|---|---|
| `job.completed` | O job terminou com sucesso. |
| `job.failed` | Falhou depois de esgotadas as tentativas automáticas. `data.error` traz `code` e `message`. |
| `job.partial` | Terminou com lacunas (páginas que falharam). `data.error` explica. |

Um job com tentativa automática pela frente (retry do Celery) **não** gera evento: só o
resultado final conta. Um PDF dividido gera um evento só, depois do merge (e, com
`describe_images`/`ocr_images`, depois de os textos das figuras entrarem no Markdown).
`created` e `completed_at` são UTC.

### Cabeçalhos

| Cabeçalho | Valor |
|---|---|
| `X-Ingestify-Event` | O mesmo `event` do corpo. |
| `X-Ingestify-Delivery` | O mesmo `id` do corpo; use para deduplicar. |
| `X-Ingestify-Signature` | `t=<unix>,v1=<hex>`: HMAC-SHA256 de `"{t}."` + corpo cru. |
| `User-Agent` | `Ingestify-Webhook/1` |

`t` é refeito a cada tentativa. Recuse eventos com `t` muito antigo (por exemplo, mais de
5 minutos) para barrar reenvio de uma captura.

## Verificar a assinatura

O segredo do usuário vem de `GET /webhooks/signing-secret` (`{"secret": "whsec_..."}`), o
mesmo sempre; trate como senha. Calcule o HMAC sobre o **corpo cru**, antes de qualquer
parse.

```python
import hashlib, hmac, time

def verify(secret: str, header: str, raw_body: bytes, tolerance=300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    t, sent = int(parts["t"]), parts["v1"]
    if abs(time.time() - t) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sent)
```

```js
import crypto from "node:crypto";

export function verify(secret, header, rawBody, tolerance = 300) {
  const parts = Object.fromEntries(header.split(",").map((p) => p.split("=", 2)));
  if (Math.abs(Date.now() / 1000 - Number(parts.t)) > tolerance) return false;
  const expected = crypto.createHmac("sha256", secret)
    .update(`${parts.t}.`).update(rawBody).digest("hex");
  const a = Buffer.from(expected), b = Buffer.from(parts.v1);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}
```

## Entrega e novas tentativas

Responda rápido (o timeout é 10 s, 5 s para conectar) com um status 2xx. A plataforma lê no
máximo 4 KB da resposta e **não segue redirecionamentos**.

| Resposta | Resultado |
|---|---|
| 2xx | Entregue. |
| 3xx, 4xx (menos 408 e 429; inclui 410) | Falha definitiva, sem nova tentativa. |
| 5xx, 408, 429, timeout, erro de rede ou DNS | Nova tentativa. |
| Host que resolve para endereço não público | Falha definitiva (`CALLBACK_URL_NOT_PUBLIC`). |

Seis tentativas no total, com 30 s, 2 min, 10 min, 30 min e 2 h entre elas. A conexão vai
para o endereço IP já validado (sem resolver o nome de novo), com o `Host` e o SNI originais,
o que impede DNS rebinding.

`GET /jobs/{job_id}` traz o bloco `webhook` (só em jobs principais com `callback_url`):

```json
"webhook": {"url_host": "app.exemplo.com", "status": "delivered", "attempts": 1,
            "last_http_status": 200, "last_error": null, "last_attempt_at": "…",
            "delivered_at": "…", "delivery_id": "101905a7-…"}
```

`status` é `pending` (a enviar ou em nova tentativa), `delivered` ou `failed`. Só o host da
URL aparece: o caminho e a query podem conter um token.

## Mais de um evento por job

Um job pode terminar mais de uma vez: uma página refeita depois de `job.partial` leva o job a
`completed`, e um job `failed` pode ser retomado. Cada término é uma entrega com `id` próprio:
vale o evento de `completed_at` mais recente, e entregas repetidas do mesmo término trazem o
mesmo `id` (o id é determinístico por job, status e `completed_at`). Deduplique por
`X-Ingestify-Delivery`.

Só o término mais recente é entregue: se o estado do job mudar antes de uma tentativa, a
entrega antiga é descartada (`superseded`) e a nova segue.

## Configuração

| Variável | Default | Efeito |
|---|---|---|
| `WEBHOOK_SIGNING_SECRET` (ou `_FILE`) | vazio | Chave de que o segredo de cada usuário deriva (HMAC). Vazio: derivada de `JWT_SECRET_KEY`, e então **trocar o JWT troca todos os segredos de webhook**. |
| `WEBHOOK_QUEUE` | vazio | Fila Celery da entrega; vazio usa a fila padrão. |
| `WEBHOOK_ALLOW_HTTP` | `false` | Aceita `http://` em `callback_url` (só desenvolvimento). |

O segredo é derivado por usuário, sem tabela: um usuário não lê o de outro.

## Limites conhecidos

- Se o broker estiver fora no instante do commit, o evento não é enfileirado: `webhook.status`
  fica `pending` e nada o reenvia sozinho (varredura periódica fica para uma próxima versão).
- A entrega usa a fila padrão: com a fila cheia de conversões, o evento espera junto.
- Sem `WEBHOOK_SIGNING_SECRET`, girar o `JWT_SECRET_KEY` gira os segredos de todos os usuários.
