# Conversão de documentos (Docling)

> Verificado contra o código em 2026-10-05 (branch `main`).
> Fonte da verdade: [backend/api/routes.py](../../backend/api/routes.py),
> [backend/workers/tasks.py](../../backend/workers/tasks.py),
> [backend/workers/converter.py](../../backend/workers/converter.py),
> [backend/shared/pdf_splitter.py](../../backend/shared/pdf_splitter.py).

## O que faz

Converte um documento (PDF, DOCX, HTML, PPTX, XLSX, …) em Markdown com o
[Docling](https://github.com/docling-project/docling). A chamada devolve na hora um
`job_id`; a conversão roda em background num worker Celery. PDFs com 2 ou mais páginas
são divididos e cada página é convertida em paralelo (ver
[Hierarquia de jobs](#o-que-acontece-por-dentro)).

Áudio e vídeo **não** passam por aqui: use `POST /transcribe` (transcrição, documentada à
parte). Imagens avulsas têm endpoints próprios em [vision.md](vision.md).

## Como usar

Os dois endpoints exigem autenticação (`Authorization: Bearer <jwt>` **ou**
`X-API-Key: <chave>`; ver [auth-and-api-keys.md](auth-and-api-keys.md)).

### `POST /upload` — upload de arquivo (recomendado)

`multipart/form-data`:

| Campo | Obrigatório | Padrão | Descrição |
|---|---|---|---|
| `file` | sim | — | O arquivo. Limite `MAX_FILE_SIZE_MB` (50 MB); acima disso, `413`. Arquivo vazio, `400`. |
| `project` / `project_id` | sim, salvo API key vinculada | — | Nome (criado se não existir) ou ID de projeto existente do usuário; não envie ambos. Sem projeto, `422`. |
| `folder` / `folder_id` | não | nenhuma | Nome (criado se não existir) ou ID de pasta do projeto; não envie ambos. Pastas têm um nível e o nome não aceita `/`. |
| `name` | não | nome do arquivo | Nome amigável do job. |
| `tags` | não | — | Tags separadas por vírgula (ver [tags.md](tags.md)). |
| `docling_preset` | não | `fast` | `fast`, `balanced` ou `quality` (tabela abaixo). Qualquer outro valor cai nos defaults do `config.py`. |

```bash
curl -X POST http://localhost:8000/upload \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "file=@relatorio.pdf" \
  -F "project=Documentos" \
  -F "folder=Financeiro" \
  -F "docling_preset=quality" \
  -F "tags=cliente-x, financeiro"
# {"job_id":"<uuid>","status":"queued","created_at":"...","message":"...","project":{"id":"<uuid>","name":"Documentos","created":true,"source":"request"},"folder":{"id":"<uuid>","name":"Financeiro","created":true}}
```

### `POST /convert` — endpoint unificado (arquivo, URL, Google Drive, Dropbox)

`multipart/form-data` com `source_type` (`file` | `url` | `gdrive` | `dropbox`), `source`
(URL, file ID ou path; ignorado quando `source_type=file`), `file`, `name`, `tags` e os
mesmos campos de projeto/pasta do `/upload`. Não envie JSON: o contrato da rota é form.
Detalhes de cada fonte em [sources.md](sources.md).

```bash
curl -X POST http://localhost:8000/convert \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "source_type=url" \
  -F "source=https://example.com/documento.pdf" \
  -F "project=Documentos"
```

Diferenças em relação ao `/upload` (comportamento atual, não necessariamente desejado):

- `/convert` **não aceita `docling_preset`**: envia `options={}` ao worker, então vale a
  configuração `DOCLING_*` do ambiente.
- Os dois endpoints excluem jobs `FAILED` da deduplicação; reenviar o arquivo de um job
  falho cria outro job (a regra compartilhada está em `api/projects_api.py`).

### Deduplicação por checksum

Nos dois endpoints, quando há arquivo, a API calcula o SHA-256 enquanto grava o upload em
disco. Se o mesmo usuário já tem um job `MAIN` não falho com o mesmo checksum **no mesmo
projeto**, a resposta devolve o
`job_id` existente (com `message` "Arquivo já foi processado anteriormente…") e as tags
enviadas são **adicionadas** ao job existente. A pasta original é preservada e trocar
`docling_preset` no reenvio não reprocessa. Enviar para outro projeto cria uma conversão
independente. Não há opção para forçar reprocessamento de um job não falho no mesmo projeto.

O projeto vem do request ou, quando não há campo de projeto, da API key vinculada.
Com JWT e API key juntos, vale o JWT e a vinculação da key não é usada. IDs de projetos
ou pastas de outro usuário retornam `404`. Nomes usam a normalização compartilhada
(sem diferenciar maiúsculas, espaços repetidos e acentos latinos; até 100 caracteres).

### Presets do Docling

Definidos em `get_converter()` ([converter.py](../../backend/workers/converter.py)):

| Preset | OCR | Imagens | Tabelas | Uso |
|---|---|---|---|---|
| `fast` (padrão do `/upload`) | não | não | sim | PDFs digitais, só texto |
| `balanced` | não | sim | sim | PDFs com figuras |
| `quality` | sim | sim | sim | Documentos escaneados (bem mais lento) |
| *(nenhum / inválido)* | `DOCLING_ENABLE_OCR` | `DOCLING_ENABLE_IMAGES` | `DOCLING_ENABLE_TABLE_STRUCTURE` | `/convert` e chamadas sem preset |

O preset é repassado do job MAIN para o split e para cada página.

### Formatos

`detect_format()` reconhece por extensão: `.pdf`, `.docx`, `.doc`, `.html/.htm`, `.pptx`,
`.ppt`, `.xlsx`, `.xls`, `.rtf`, `.odt`, `.md`. A API **não valida** o tipo do arquivo no
upload: qualquer arquivo é aceito e enfileirado; se o Docling não suportar o formato, o
job termina `failed` com a mensagem do Docling. Na prática o suporte real é o da versão
do Docling instalada (o `.doc`/`.ppt`/`.xls` legado e `.rtf` costumam falhar).

### Acompanhar e obter o resultado

`GET /jobs/{job_id}` para progresso e `GET /jobs/{job_id}/result` para o Markdown — ver
[jobs-api.md](jobs-api.md).

```bash
curl "http://localhost:8000/jobs/$JOB_ID" -H "X-API-Key: $INGESTIFY_API_KEY"
curl "http://localhost:8000/jobs/$JOB_ID/pages" -H "X-API-Key: $INGESTIFY_API_KEY"
curl "http://localhost:8000/jobs/$JOB_ID/pages/1/result" -H "X-API-Key: $INGESTIFY_API_KEY"
curl "http://localhost:8000/jobs/$JOB_ID/result" -H "X-API-Key: $INGESTIFY_API_KEY"
```

`/result` responde JSON com `result.markdown` e `result.metadata`; não é download de
texto Markdown puro. Documentos não geram VTT/SRT. Para PDF dividido, é possível ler
cada página concluída antes do merge. Os números de página começam em 1. Antes do split,
`/pages` pode retornar `404`; durante a criação, a lista pode estar incompleta e o
`job_id` de uma página pode ser `null` — consulte de novo, sem inventar IDs.

`GET /jobs/{id}/pages/{n}/pdf` retorna `{url, expires_in: 900, expires_at, ...}`.
Abra a URL assinada diretamente, sem credenciais do Ingestify e sem alterar a query;
ela expira em 15 minutos. PDF de uma página não é dividido e não tem esses jobs filhos.
`POST /jobs/{id}/pages/{n}/retry` reprocessa uma página `failed` (até 3 tentativas
manuais) e devolve o novo `page_job_id`; uma página falha impede o merge final.

## O que acontece por dentro

```
POST /upload ─► API grava o upload em {TEMP_STORAGE_PATH}/uploads/.staging/<uuid>
               ─► move para {TEMP_STORAGE_PATH}/uploads/{job_id}/{arquivo}
               ─► cópia em MinIO: ingestify-uploads/uploads/{job_id}/{arquivo}
               ─► linha em MySQL (jobs, job_type=MAIN, status=PENDING) + status no Redis
               ─► process_conversion.delay(...)            (fila `ingestify`)

process_conversion (worker)
  ├─ progresso 10% ─► baixa/resolve a fonte (sources.py)
  ├─ PDF com ≥ 2 páginas (qpdf --show-npages)?
  │    sim ─► split_pdf_task  ──► qpdf extrai cada página
  │                              ├─ página em MinIO: ingestify-pages/pages/{job_id}/page_NNNN.pdf
  │                              ├─ linha em `pages` (MySQL) + job PAGE no Redis
  │                              └─ convert_page_task.delay(...) por página
  │         cada página ─► Docling ─► resultado no Redis (job:{page_job_id}:result),
  │                        Elasticsearch (page_results) e MinIO
  │                        (ingestify-results/results/{job_id}/page_NNNN.md)
  │         progresso do MAIN = 20 + int(concluídas / total * 70)
  │         quando TODAS as páginas estão `completed` ─► merge_pages_task
  │              junta as páginas em ordem com "\n\n---\n\n", grava no Redis e no ES
  │              (job_results), marca o MAIN como completed (100%)
  └─ não ─► converte o arquivo inteiro de uma vez, grava Redis + ES, completed
```

- Todas as tasks de documento vão para a fila padrão `CELERY_TASK_DEFAULT_QUEUE`
  (`ingestify`), consumida pelo serviço `worker` do compose.
- Limite de tempo por task: `CONVERSION_TIMEOUT_SECONDS` (hard) e esse valor − 30 s
  (soft). O default do código é 300 s; o `docker-compose.yml` usa 600 s.
- `process_conversion` faz até 3 retries com backoff exponencial (60 s, 120 s, 240 s)
  em qualquer falha (inclusive soft time limit); entre uma tentativa e outra o job aparece
  como `failed` com a mensagem de erro. `convert_page_task` tem `max_retries=3`;
  `split_pdf_task` e `merge_pages_task`, 2.
- Um conversor Docling é reaproveitado por processo e por combinação de opções (o
  carregamento dos modelos de layout/tabela é caro).
- Ao concluir, os arquivos locais do job são apagados (`_remove_job_files`); o original
  continua no MinIO. Sobras de jobs que falharam são varridas pela task diária
  `cleanup_stale_files` (ver [storage-and-retention.md](storage-and-retention.md)).
- Se o pacote `docling` não puder ser importado, o conversor devolve um Markdown
  **MOCK** ("This is a **MOCK conversion**…") em vez de falhar. Útil em testes, perigoso
  em produção: confira o log `Failed to import Docling` se o resultado parecer falso.

### GPU

O Docling roda em `DEVICE` (`auto` | `cpu` | `cuda` | `cuda:N`, default `auto`), resolvido
em [backend/shared/device.py](../../backend/shared/device.py). `DOCLING_DEVICE` é
ignorado. No overlay `docker-compose.gpu.yml` o serviço `worker` vira **um** processo
(`replicas: 1`, `--concurrency=1`) com `DEVICE=cuda`. Detalhes, VRAM e troubleshooting:
[../GPU.md](../GPU.md).

## Configuração

Variáveis lidas por [backend/shared/config.py](../../backend/shared/config.py):

| Variável | Default (código) | Efeito |
|---|---|---|
| `MAX_FILE_SIZE_MB` | `50` | Limite do upload (`413` acima disso) e do download por URL. |
| `CONVERSION_TIMEOUT_SECONDS` | `300` (compose: `600`) | Hard time limit das tasks; soft = valor − 30. |
| `TEMP_STORAGE_PATH` | `/tmp/ingestify` | Diretório de trabalho compartilhado entre API e workers (bind mount `./tmp`). |
| `DOCLING_ENABLE_OCR` | `false` | OCR quando não há preset. |
| `DOCLING_ENABLE_TABLE_STRUCTURE` | `true` | Reconhecimento de tabelas quando não há preset. |
| `DOCLING_ENABLE_IMAGES` | `false` | `generate_picture_images` quando não há preset. |
| `DOCLING_NUM_THREADS` | `4` | Threads do Docling (`AcceleratorOptions.num_threads`). |
| `DEVICE` | `auto` | Dispositivo do Docling (e de Whisper/Florence-2). |
| `DOCLING_USE_V2_BACKEND` | `true` | **Sem efeito**: declarado mas não lido por nenhum código. O conversor sempre tenta `DoclingParseDocumentBackend` e depois `DoclingParseV2DocumentBackend`. |
| `CELERY_TASK_DEFAULT_QUEUE` | `ingestify` | Fila das tasks de documento. |

## Limites e lacunas conhecidas

- **Página que falha bloqueia o merge.** O merge só dispara quando todas as páginas estão
  `completed`. Uma página `failed` deixa o job MAIN em `processing` até alguém chamar
  `POST /jobs/{id}/pages/{n}/retry` (máx. 3 tentativas por página) ou até o monitor de
  jobs travados marcá-lo como `failed` (ver [monitoring-and-admin.md](monitoring-and-admin.md)).
- **Auto-retry de páginas não reenfileira.** A task periódica `auto_retry_failed_pages`
  incrementa `retry_count`, volta a página para `PENDING` e troca o `page_job_id`, mas
  **não** enfileira a conversão (há um `TODO` em
  [monitoring.py](../../backend/workers/monitoring.py)). A página fica parada até um retry
  manual.
- Metadados do resultado: `pages` vem `null` para documentos não divididos; `title` é o
  nome do arquivo; `author` é sempre `null`; no merge, `size_bytes` é `0`.
- O parâmetro `callback_url` (webhook) existe em `process_conversion`, mas nenhum endpoint
  o expõe.
- `GET /jobs/{id}/result` de um job em `processing`/`queued` devolve `400`; de um job
  `failed`, `500` com a mensagem de erro.

## Com rota de `document_conversion` (spec 0003, fatia 8)

Opcional. Com `engines.py routes set document_conversion --step local`, cada página de um PDF
dividido (e cada retry de página) entra no backlog durável e o despachante a coloca no `worker`
até a capacidade declarada; uma página que falha volta ao backlog com backoff e, esgotadas as
tentativas, só ela fica `FAILED`. Sem rota, nada muda. Detalhes em
[engines.md](engines.md#documentos-por-página-fatia-8).
