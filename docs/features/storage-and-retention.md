# Armazenamento e retenção

> Verificado contra o código em 2026-10-04. Fonte da verdade:
> [backend/shared/minio_client.py](../../backend/shared/minio_client.py),
> [backend/shared/redis_client.py](../../backend/shared/redis_client.py),
> [backend/shared/elasticsearch_client.py](../../backend/shared/elasticsearch_client.py),
> [backend/shared/models.py](../../backend/shared/models.py),
> [backend/workers/monitoring.py](../../backend/workers/monitoring.py),
> [backend/workers/celery_app.py](../../backend/workers/celery_app.py).

## Visão geral: o que fica onde

| Armazém | Papel | Retenção |
|---|---|---|
| **MySQL** | Fonte da verdade: usuários, API keys, jobs, páginas, tags. Decide autorização. | Permanente até `DELETE /jobs/{id}`. |
| **Elasticsearch** | Markdown final (`job_results`) e por página (`page_results`); busca. | Permanente até `DELETE /jobs/{id}`. |
| **MinIO** | Arquivos: originais, PDFs por página, Markdown por página, áudio/legendas. | Sem expiração (ver lacunas). |
| **Redis** | Cache com TTL: status ao vivo, resultados recentes, filas Celery, rate limit. | Toda chave expira. |
| **Disco** (`TEMP_STORAGE_PATH`) | Área de trabalho compartilhada entre API e workers. | Apagado ao concluir; sobras varridas após 72 h. |

O MySQL **não** faz parte do compose: a `DATABASE_URL` padrão do compose aponta para
`host.docker.internal` (um MySQL no host); o default do código é
`mysql+pymysql://root:root@localhost/ingestify`. As tabelas são criadas por
`init_db()` no startup da API (com `ALTER TABLE` para colunas novas); há também
`alembic/` e `backend/migrations/*.sql`.

## MinIO

Buckets criados no startup (`_ensure_buckets_exist`). Todos são **privados**: o cliente
remove qualquer política de leitura pública herdada de versões antigas e **recusa
iniciar** se não conseguir verificar isso.

| Bucket (variável) | Objetos | Escrito por |
|---|---|---|
| `ingestify-uploads` (`MINIO_BUCKET_UPLOADS`) | `uploads/{job_id}/{arquivo}` — original enviado em `/upload` ou `/convert` (só `source_type=file`) | API |
| `ingestify-pages` (`MINIO_BUCKET_PAGES`) | `pages/{job_id}/page_NNNN.pdf` — cada página de um PDF dividido | `split_pdf_task` |
| `ingestify-results` (`MINIO_BUCKET_RESULTS`) | `results/{job_id}/page_NNNN.md` — Markdown de cada página | `convert_page_task` |
| `ingestify-audio` (`MINIO_BUCKET_AUDIO`) | mídia enviada a `/transcribe` e `transcripts/{job_id}/…` | API / worker de transcrição |
| `ingestify-crawled` (`MINIO_BUCKET_CRAWLED`) | vazio — reservado ao crawler não implementado ([crawler.md](crawler.md)) | — |

Leitura pelo navegador: só via URL pré-assinada de 15 min em
`GET /jobs/{id}/pages/{n}/pdf` ([jobs-api.md](jobs-api.md#páginas)). A URL é assinada para
`MINIO_PUBLIC_ENDPOINT` (ou, se não definido, o host da requisição na porta do MinIO).

Imagens de `/images/*` **não** vão para o MinIO.

Se o MinIO estiver indisponível no upload, a API loga o erro e segue com o arquivo só no
disco (o retry de página depende do original no MinIO depois que o disco é limpo).

## Redis

Ver também a seção "Redis Key Structure" do [CLAUDE.md](../../CLAUDE.md).

| Chave | Conteúdo | TTL |
|---|---|---|
| `job:{id}:status` | JSON com tipo, status, progresso, erro, `parent_job_id`, `page_number`, `child_job_ids` | 24 h |
| `job:{id}:result` | Resultado (`{markdown, metadata}` ou payload de visão/transcrição) | `RESULT_TTL_SECONDS` (3600 s) |
| `job:{id}:pages:total` | Número de páginas de um PDF dividido | 24 h |
| `job:{id}:owner` | `user_id` — fallback de autorização quando o MySQL não conhece o job | 24 h |
| `user:{user_id}:jobs` | SET com os job ids do usuário | 30 dias |
| `job:{id}:output_format`, `job:{id}:transcript:partial` | Transcrição | ver doc de transcrição |
| `vision:worker:heartbeat` | Capacidades do worker de visão | 45 s |
| `ratelimit:<bucket>:<identidade>` | Contadores de login/registro | janela da regra |

Não existe chave por página (`job:{id}:page:{n}`): cada página é um job próprio. O Redis
também serve de broker (`CELERY_BROKER_URL`, db 0) e result backend do Celery
(`CELERY_RESULT_BACKEND`, db 1).

## Disco local

`TEMP_STORAGE_PATH` (default `/tmp/ingestify`; no compose, bind mount `./tmp`):

- `uploads/.staging/` — upload sendo recebido (apagado se a requisição falhar);
- `uploads/{job_id}/` — original lido pelo worker;
- `{job_id}/` — páginas extraídas e arquivos de trabalho;
- `images/{job_id}/` — handoff de imagem para o worker de visão;
- `audio/{job_id}/` — mídia de transcrição.

Jobs concluídos apagam seus arquivos locais imediatamente.

## Tarefas agendadas (Celery Beat)

Serviço `beat` do compose; agenda definida em
[celery_app.py](../../backend/workers/celery_app.py) **somente se `MONITORING_ENABLED=true`**:

| Task | Quando | O que faz |
|---|---|---|
| `detect_stuck_jobs` | a cada `MONITORING_CHECK_INTERVAL_MINUTES` (5) | Marca `failed` jobs/páginas em `PROCESSING` há mais de `MONITORING_STUCK_JOB_THRESHOLD_MINUTES` (30). |
| `auto_retry_failed_pages` | a cada 5 min | Ver lacuna em [monitoring-and-admin.md](monitoring-and-admin.md). |
| `cleanup_old_jobs` | diariamente às 02:00 UTC | Apaga do **Redis** as chaves de jobs concluídos/falhos há mais de `MONITORING_CLEANUP_DAYS` (7) e varre handoffs órfãos de imagem. MySQL, ES e MinIO não são tocados. |
| `cleanup_stale_files` | diariamente às 03:00 UTC | Apaga do disco arquivos com mais de `TEMP_FILES_RETENTION_HOURS` (72) de jobs que não estão ativos. |
| `health_check` | a cada minuto | Prova de vida do beat. |

## Configuração

| Variável | Default | Observação |
|---|---|---|
| `MINIO_ENDPOINT` | `127.0.0.1:9000` | |
| `MINIO_PUBLIC_ENDPOINT` | `127.0.0.1:9000` | Endereço visível pelo navegador para URLs assinadas. |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | **obrigatórias** | Iguais a `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`. `minioadmin` é recusado com `ENVIRONMENT=production`. |
| `MINIO_SECURE` | `false` | HTTPS. |
| `MINIO_BUCKET_*` | ver tabela | |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` / `REDIS_PASSWORD` | `redis` / `6379` / `0` / vazio | Senha é injetada também nas URLs do Celery. |
| `RESULT_TTL_SECONDS` | `3600` | |
| `TEMP_STORAGE_PATH` | `/tmp/ingestify` | |
| `TEMP_FILES_RETENTION_HOURS` | `72` | |
| `MONITORING_*` | ver [monitoring-and-admin.md](monitoring-and-admin.md) | |
| `DATABASE_URL` | `mysql+pymysql://root:root@localhost/ingestify` | |
| `SQL_ECHO` | `false` | Loga todo SQL (só debug). |
| `CLEANUP_INTERVAL_HOURS` | `24` | **Sem efeito**: declarada, não lida. Os horários do beat são fixos. |

## Limites e lacunas conhecidas

- **Nada expira no MinIO** (não há política de lifecycle) e `DELETE /jobs/{id}` só apaga
  objetos de transcrição. Originais, PDFs e Markdown por página de documentos ficam para
  sempre.
- `GET /jobs/{id}` depende do status no Redis (24 h); após isso responde `404`, embora o
  job continue no MySQL e o Markdown no Elasticsearch.
- `cleanup_old_jobs` ainda tenta apagar chaves antigas `job:{id}:page:{n}` que nada mais
  escreve (inofensivo).
