# Jobs: ciclo de vida e consulta

> Verificado contra o código em 2026-10-04. Fonte da verdade:
> [backend/api/routes.py](../../backend/api/routes.py),
> [backend/api/deps.py](../../backend/api/deps.py),
> [backend/shared/schemas.py](../../backend/shared/schemas.py).

## O que é um job

Toda operação assíncrona do Ingestify (conversão, transcrição, visão) cria um **job MAIN**
com um `job_id` (UUID). PDFs com 2+ páginas geram jobs filhos:

```
MAIN ─┬─ SPLIT   (divide o PDF)
      ├─ PAGE 1..N (uma conversão por página, em paralelo)
      └─ MERGE   (junta as páginas)
```

- **MySQL** (tabelas `jobs`, `pages`, `job_tags`) é a fonte da verdade de **existência,
  dono e histórico**. Só o MAIN tem linha em `jobs`; páginas têm linha em `pages`
  (com `page_job_id`); SPLIT e MERGE existem apenas no Redis.
- **Redis** guarda o status ao vivo (`job:{id}:status`, TTL 24 h) e o resultado
  (`job:{id}:result`, TTL `RESULT_TTL_SECONDS` = 1 h).
- **Elasticsearch** guarda o Markdown final (`job_results`) e por página
  (`page_results`) sem TTL — é de lá que `/result` lê primeiro.

Detalhes de armazenamento: [storage-and-retention.md](storage-and-retention.md).

### Status

| API | MySQL (`JobStatus`) | Observação |
|---|---|---|
| `queued` | `PENDING` | Recém-criado. |
| `processing` | `PROCESSING` | |
| `completed` | `COMPLETED` | |
| `failed` | `FAILED` | Pode voltar a `processing` se o Celery fizer retry. |
| `cancelled` | `CANCELLED` | Existe no enum, mas nenhum endpoint cancela jobs. |

### Progresso (job MAIN de PDF dividido)

`10%` ao iniciar → `20 + int(páginas_concluídas / total * 70)` conforme as páginas
terminam → `100%` quando o merge conclui. Documentos não divididos vão de 10 → 80 → 90 → 100.

## Autorização

Todos os endpoints abaixo exigem autenticação. Os que recebem `{job_id}` passam por
`get_owned_job` ([deps.py](../../backend/api/deps.py)):

- O dono é sempre resolvido no **MySQL**; para jobs filhos, sobe-se até o MAIN
  (via `pages.page_job_id` ou `parent_job_id`).
- Job inexistente **e** job de outro usuário devolvem o mesmo `404 "Job não encontrado"`
  (sem enumeração).
- O dono registrado no Redis (`job:{id}:owner`) só é consultado quando o MySQL não conhece
  o job, e só autoriza com igualdade explícita.

## Endpoints

| Método e caminho | Para quê |
|---|---|
| `GET /jobs` | Lista os jobs MAIN do usuário (paginação e filtros). |
| `GET /jobs/{job_id}` | Status de qualquer job (MAIN, SPLIT, PAGE, MERGE). |
| `GET /jobs/{job_id}/result` | Resultado (Markdown) de um MAIN ou de um PAGE. |
| `GET /jobs/{job_id}/pages` | Lista de páginas com status e `job_id` de cada uma. |
| `GET /jobs/{job_id}/pages/{n}/status` | Status da página `n` (1-indexada). |
| `GET /jobs/{job_id}/pages/{n}/result` | Markdown da página `n`. |
| `GET /jobs/{job_id}/pages/{n}/pdf` | URL pré-assinada (15 min) do PDF da página `n`. |
| `POST /jobs/{job_id}/pages/{n}/retry` | Reprocessa uma página `failed` (máx. 3 vezes). |
| `PUT /jobs/{job_id}/tags` | Substitui as tags (ver [tags.md](tags.md)). |
| `DELETE /jobs/{job_id}` | Apaga o job. |
| `GET /jobs/{job_id}/transcript/partial` | Só para transcrições (fora do escopo deste doc). |

### `GET /jobs`

Lista do **MySQL**, do mais recente para o mais antigo; para jobs `queued`/`processing`
o status e o progresso vêm do Redis.

| Query | Padrão | Descrição |
|---|---|---|
| `limit` | `50` | Limitado a 1..100. |
| `offset` | `0` | |
| `status` | — | `queued`, `processing`, `completed`, `failed`, `cancelled` (outro valor: `422`). |
| `job_type` | `main` | `main` ou `all` (inclui qualquer `job_type` com linha em `jobs`). |
| `tag` | — | Repetível; `?tag=a&tag=b` exige as duas (E). |
| `q` | — | Busca `ILIKE` em `name` e `filename` (não no conteúdo; para isso, [search.md](search.md)). |
| `kind` | — | `document`, `transcription` (`source_type=audio`) ou `image` (`source_type=image`). |

Resposta: `{total, limit, offset, jobs[], counts}`. `counts` traz `all` e um contador por
status, com os demais filtros aplicados (antes do filtro de status). Cada item tem
`job_id, type, status, progress, name, filename, kind, source_type, mime_type,
file_size_bytes, tags, error, created_at, completed_at` e, para PDFs divididos,
`total_pages` e `pages_completed`.

```bash
curl -H "X-API-Key: $INGESTIFY_API_KEY" \
  "http://localhost:8000/jobs?kind=document&status=completed&tag=financeiro&limit=20"
```

### `GET /jobs/{job_id}`

Lê o status do **Redis** (se expirou — 24 h — responde `404 "Job não encontrado ou
expirado"`, mesmo que o job exista no MySQL e o resultado esteja no Elasticsearch).
Datas e nome vêm do MySQL quando existem.

Para jobs MAIN de PDF dividido, inclui `total_pages`, `pages_completed`, `pages_failed`,
`pages[]` (cada um com `page_number, job_id, status, url, error_message, retry_count`) e
`child_jobs` (`split_job_id`, `page_job_ids[]`, `merge_job_id`). Páginas ainda não criadas
pelo split aparecem como `queued` com `job_id: null`.

Paginação da lista de páginas: `?page_limit=50&page_offset=0` (sem `page_limit`, todas).

`source_available` (bool) diz se o arquivo original ainda existe (`Job.minio_upload_path`
preenchido ou cópia local em `{TEMP_STORAGE_PATH}/uploads|audio/{job_id}/`). Fica `false`
depois de `purge_source` ou de `DELETE /jobs/{job_id}/source`, e para jobs filhos.

### `GET /jobs/{job_id}/result`

1. Status do Redis: `queued`/`processing` → `400`; `failed` → `500` com o erro.
2. Resultado do **Elasticsearch** (`job_results`); se não houver, do Redis
   (`job:{id}:result`); se nenhum, `404`.

Resposta: `{job_id, type, status: "completed", result: {markdown, metadata}, completed_at}`
e, para jobs PAGE, `page_number` e `parent_job_id`. O parâmetro `?format=` só tem efeito
em transcrições.

```bash
curl -H "X-API-Key: $INGESTIFY_API_KEY" http://localhost:8000/jobs/$JOB_ID/result \
  | jq -r .result.markdown > saida.md
```

### Páginas

- `GET /jobs/{id}/pages` — do MySQL (`pages`); se não houver linhas, cai para o Redis.
  `404` se o job não tem páginas (documento não dividido).
- `GET /jobs/{id}/pages/{n}/status` e `.../result` — dispensam conhecer o `page_job_id`.
  O resultado vem do Elasticsearch (`page_results`) ou, em fallback, do Redis.
- `GET /jobs/{id}/pages/{n}/pdf` — devolve **JSON**, não redirect:
  `{job_id, page_number, url, expires_in: 900, expires_at}`. A `url` é assinada para o
  host que o navegador usa (`MINIO_PUBLIC_ENDPOINT`, ou o host da requisição) e não aceita
  parâmetros extras na query string (invalidaria a assinatura → `403` no MinIO).
- `POST /jobs/{id}/pages/{n}/retry` — só para página `failed` e com `retry_count < 3`.
  Gera um novo `page_job_id`; se a cópia local do PDF já foi apagada, restaura o original
  de `ingestify-uploads` antes de reextrair a página. Resposta inclui `new_page_job_id`,
  `retry_count` e `retry_limit: 3`.

### `DELETE /jobs/{job_id}`

Remove, nesta ordem: o resultado e as páginas no Elasticsearch; para transcrições, os
objetos de áudio/legendas no MinIO; as linhas do MySQL (`jobs` filhos, `pages`, o MAIN —
`job_tags` cai por cascade); e as chaves do Redis (MAIN, SPLIT, PAGEs, MERGE e o índice
`user:{id}:jobs`). Responde `{message, job_id, deleted_at}`.

**Lacuna:** para documentos, os objetos no MinIO **não** são apagados — o original
(`ingestify-uploads/uploads/{job_id}/…`; apague-o antes com `DELETE /jobs/{job_id}/source`
ou use `purge_source`), os PDFs por página
(`ingestify-pages/pages/{job_id}/…`) e os Markdown por página
(`ingestify-results/results/{job_id}/…`) permanecem.

### `DELETE /jobs/{job_id}/source`

Apaga só o **arquivo original** (documento, áudio ou vídeo enviado), mantendo o job e o
resultado: o objeto no MinIO (`ingestify-uploads` para `uploads/…`, `ingestify-audio` para
`audio/…`) e a cópia local; zera `Job.minio_upload_path`. Autorização `jobs.delete`.

| Resposta | Quando |
|---|---|
| `200 {"job_id": "...", "source_deleted": true}` | apagado |
| `404` | job inexistente, de outro usuário, job filho, ou sem original (já apagado) |
| `409 {"code": "JOB_STILL_PROCESSING", "message": ...}` | job `queued`/`processing` (inclui PDF dividido com páginas em andamento ou falhas ainda não resolvidas) |
| `503 {"code": "SOURCE_DELETE_FAILED", ...}` | o MinIO recusou; o original continua referenciado |

Depois disso o retry de página não tem mais de onde restaurar o PDF (`404`). Os PDFs por
página continuam disponíveis. Para apagar automaticamente ao terminar, use
`purge_source=true` no `/upload`, `/convert` ou `/transcribe` (ver
[conversion.md](conversion.md#guardar-ou-apagar-o-arquivo-original-purge_source)).

## Configuração

| Variável | Default | Efeito |
|---|---|---|
| `RESULT_TTL_SECONDS` | `3600` | TTL de `job:{id}:result` no Redis. |
| (fixo no código) | 24 h | TTL de `job:{id}:status`, `job:{id}:owner`, `job:{id}:pages:total`. |
| (fixo no código) | 15 min | Validade da URL de `/pages/{n}/pdf` (`PAGE_PDF_URL_TTL_SECONDS`). |
| (fixo no código) | 3 | Limite de retries manuais por página. |

## Limites e lacunas conhecidas

- `GET /jobs/{id}` e `GET /jobs/{id}/result` dependem do status no Redis: depois de 24 h
  respondem `404` mesmo com o Markdown guardado no Elasticsearch. `GET /jobs` continua
  listando o job (vem do MySQL).
- Não há cancelamento de job.
- `GET /jobs/{id}/pages/{n}/status` devolve `job_id: "page-{n}"` quando a linha da página
  não tem `page_job_id` (esse valor não é um id endereçável).
