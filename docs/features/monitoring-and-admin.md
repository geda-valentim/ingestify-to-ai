# Monitoramento, health check e rotas de admin

> Verificado contra o código em 2026-10-04. Fonte da verdade:
> [backend/api/admin_routes.py](../../backend/api/admin_routes.py),
> [backend/workers/monitoring.py](../../backend/workers/monitoring.py),
> [backend/workers/celery_app.py](../../backend/workers/celery_app.py),
> [backend/shared/queries.py](../../backend/shared/queries.py),
> [backend/api/routes.py](../../backend/api/routes.py) (`GET /health`).

## Health check (público)

`GET /health` — sem autenticação.

```bash
curl http://localhost:8000/health
# {"status":"healthy","version":"1.0.0","redis":true,
#  "workers":{"active":7,"available":7,"elasticsearch":true},"timestamp":"..."}
```

| `status` | Condição | HTTP |
|---|---|---|
| `healthy` | Redis ok, Elasticsearch ok, ≥ 1 worker Celery respondendo | 200 |
| `degraded` | Redis ok, ≥ 1 worker, Elasticsearch fora | 200 |
| `unhealthy` | Redis fora ou nenhum worker | 503 |

`workers.active` conta **todos** os workers Celery (documentos, áudio e visão), via
`inspect().stats()`; não diz qual fila tem consumidor. MySQL e MinIO não são verificados.
Para visão, use `GET /images/capabilities` ([vision.md](vision.md)).

`GET /` devolve nome, versão e status da API (também público).

## Rotas de admin (`/admin`)

Exigem um usuário admin: `users.is_admin = true` (via `python scripts/make_admin.py`) ou
id listado em `ADMIN_USER_IDS`. Outros usuários recebem `403`. Não há UI no frontend.

| Método e caminho | O que faz |
|---|---|
| `GET /admin/stats` | Contagem de jobs/páginas por status, travados, info do Redis e a configuração de monitoramento. |
| `GET /admin/jobs/stuck?threshold_minutes=&limit=100` | Lista jobs e páginas travados em `PROCESSING`. |
| `POST /admin/jobs/recover-stuck` | Executa `detect_stuck_jobs` na hora (síncrono). |
| `POST /admin/jobs/{job_id}/retry-all-failed` | Marca para retry as páginas `failed` do job com `retry_count < MONITORING_MAX_RETRY_COUNT` (ver lacunas). |
| `POST /admin/cleanup` | Executa `cleanup_old_jobs` na hora. |
| `GET /admin/health/monitoring` | Tasks agendadas e registradas no Celery. |

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/admin/stats
```

## Tarefas periódicas

Agenda do Celery Beat (serviço `beat`), ativa só com `MONITORING_ENABLED=true`. Lista
completa e horários em [storage-and-retention.md](storage-and-retention.md#tarefas-agendadas-celery-beat).

- **Jobs travados:** um job MAIN é considerado travado quando está em `PROCESSING` com
  `started_at` mais antigo que o limite; uma página, quando está em `PROCESSING` com
  `created_at` mais antigo que o limite. Ambos viram `FAILED` no MySQL e no Redis.

## Configuração

| Variável | Default | Efeito |
|---|---|---|
| `MONITORING_ENABLED` | `true` | Liga a agenda do beat e as tasks de monitoramento. |
| `MONITORING_STUCK_JOB_THRESHOLD_MINUTES` | `30` | Limite para "travado". |
| `MONITORING_CHECK_INTERVAL_MINUTES` | `5` | Período de `detect_stuck_jobs` e `auto_retry_failed_pages`. |
| `MONITORING_CLEANUP_DAYS` | `7` | Idade mínima para `cleanup_old_jobs` limpar o Redis. |
| `MONITORING_AUTO_RETRY_ENABLED` | `true` | |
| `MONITORING_MAX_RETRY_COUNT` | `3` | |
| `MONITORING_BATCH_SIZE` | `100` | Máximo de itens por ciclo. |
| `ADMIN_USER_IDS` | vazio | |

## Limites e lacunas conhecidas

- **Retry automático e em massa não reenfileiram nada.** `auto_retry_failed_pages` e
  `POST /admin/jobs/{id}/retry-all-failed` incrementam `retry_count` e voltam a página
  para `PENDING`, mas apenas logam que "o reenfileiramento automático ainda não foi
  implementado". A página fica parada em `PENDING`; o caminho que funciona é
  `POST /jobs/{id}/pages/{n}/retry` ([jobs-api.md](jobs-api.md#páginas)). O log sugere
  `POST /admin/jobs/{id}/pages/{n}/retry`, rota que **não existe**.
- O limite de "travado" conta desde o início do job, não desde o último progresso: um PDF
  grande que leve mais de 30 min no total é marcado `FAILED` mesmo progredindo.
- Não há métricas Prometheus nem endpoint `/metrics`.
