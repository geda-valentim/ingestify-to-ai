# Visão: descrição de imagem e OCR (Florence-2)

> Verificado contra o código em 2026-10-04. Fonte da verdade:
> [backend/api/image_routes.py](../../backend/api/image_routes.py),
> [backend/workers/vision_tasks.py](../../backend/workers/vision_tasks.py),
> [backend/workers/vision/](../../backend/workers/vision/),
> [backend/shared/schemas.py](../../backend/shared/schemas.py).
> Introduzido nos commits `5fd6461`, `6c4fffa`, `038b081`.
> Instalação, GPU, VRAM e download de pesos: [../GPU.md](../GPU.md).

## O que faz

Recebe uma imagem e devolve, **na mesma requisição** (síncrono, com prazo):

- **describe** — uma legenda/descrição em texto (tarefas Florence-2 `<MORE_DETAILED_CAPTION>`,
  `<DETAILED_CAPTION>` ou `<CAPTION>`);
- **ocr** — o texto da imagem e, por linha, o quadrilátero (`quad_box`, 8 valores) e o
  retângulo (`bbox`, 4 valores) em pixels da imagem original (`<OCR_WITH_REGION>`).

Não há UI no frontend para estes endpoints; o uso é via API.

## Como usar

Todos exigem autenticação (JWT ou API key).

| Método e caminho | Entrada |
|---|---|
| `POST /images/describe` | JSON `{image_base64, filename?, task?, tags?}` |
| `POST /images/describe/upload` | multipart `file`, `task?`, `tags?` |
| `POST /images/ocr` | JSON `{image_base64, filename?, tags?}` |
| `POST /images/ocr/upload` | multipart `file`, `tags?` |
| `GET /images/capabilities` | — (estado do subsistema; ver abaixo) |

- `image_base64` aceita o prefixo `data:image/...;base64,`.
- `task` padrão: `<MORE_DETAILED_CAPTION>` (configurável por `VISION_CAPTION_TASK`).
- Formatos aceitos (detectados pelos *magic bytes*, não pela extensão): PNG, JPEG, WEBP,
  BMP, GIF, TIFF.

```bash
curl -X POST http://localhost:8000/images/describe/upload \
  -H "X-API-Key: $INGESTIFY_API_KEY" -F "file=@foto.jpg" -F "task=<CAPTION>"

curl -X POST http://localhost:8000/images/ocr \
  -H "X-API-Key: $INGESTIFY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"image_base64\": \"$(base64 -w0 recibo.png)\"}"
```

Resposta comum: `job_id`, `status: "completed"`, `image_base64` (eco byte a byte da imagem
enviada), `image_mime_type`, `image_bytes`, `image_sha256`, `width`, `height`,
`model {model_id, revision, device, dtype}`, `duration_ms`; mais `description` e `task`
(describe) ou `text` e `lines[]` (ocr). Imagem sem texto no OCR é `200` com `text: ""` e
`lines: []`.

### Erros

Formato `{"detail": {"error_code", "message", ...}}`.

| HTTP | `error_code` | Quando |
|---|---|---|
| 413 | `IMAGE_TOO_LARGE` | Mais que `VISION_MAX_IMAGE_SIZE_MB`. |
| 422 | `IMAGE_TOO_LARGE` | Mais pixels que `VISION_MAX_IMAGE_PIXELS` (proteção contra bomba de descompressão). |
| 422 | `INVALID_BASE64` / `UNSUPPORTED_IMAGE_FORMAT` / `UNSUPPORTED_CAPTION_TASK` | Entrada inválida. |
| 503 | `VISION_DISABLED` | `ENABLE_IMAGE_DESCRIPTION=false`. |
| 503 | `VISION_DEPENDENCIES_MISSING`, `VISION_MODEL_NOT_DOWNLOADED`, `VISION_MODEL_LOAD_FAILED`, `VISION_DEVICE_UNAVAILABLE`, `CELERY_UNAVAILABLE` | Worker sem torch/transformers, pesos ausentes com download desabilitado, falha de carga, `DEVICE=cuda` sem GPU, broker fora. |
| 504 | `VISION_TIMEOUT` | Passou de `VISION_REQUEST_TIMEOUT_SECONDS`. O corpo traz `job_id`, `poll_url` e `result_url`; **a task continua** e o resultado pode ser buscado depois. |

### `GET /images/capabilities`

Lê um heartbeat que o worker de visão publica no Redis (`vision:worker:heartbeat`,
TTL 45 s, renovado a cada 15 s numa thread que roda inclusive durante a inferência). Não
enfileira nada. Campos: `enabled`, `provider`, `model_id`, `revision`, `device_requested`,
`device_resolved`, `torch_available`, `cuda_available`, `cuda_device_name`,
`dependencies_installed`, `model_downloaded`, `model_loaded`, `trust_remote_code`,
`reason`. Sem heartbeat recente: `dependencies_installed=false` e `reason` explicando que
não há worker.

## O que acontece por dentro

1. A API valida tamanho e formato, cria um job MAIN (`source_type="image"`) no MySQL e no
   Redis — por isso a imagem aparece em `GET /jobs?kind=image`.
2. Grava a imagem em `{TEMP_STORAGE_PATH}/images/{job_id}/` (os bytes **não** passam pelo
   broker e **não** vão para o MinIO).
3. Envia a task para a fila dedicada `VISION_QUEUE` (`ingestify-vision`), consumida pelo
   serviço `worker-vision` (`--concurrency=1`, um modelo residente por máquina).
4. Espera o resultado sem bloquear o event loop, até `VISION_REQUEST_TIMEOUT_SECONDS`.
5. O worker roda o Florence-2, grava o resultado no Redis (`job:{id}:result`) e apaga a
   imagem num `finally`. Sobras de workers mortos são varridas pela task diária
   `cleanup_old_jobs` (diretórios com mais de `max(4 × VISION_TASK_TIMEOUT_SECONDS, 1 h)`).

As tasks de visão têm `max_retries=0` e `time_limit = VISION_TASK_TIMEOUT_SECONDS`.

## Configuração

| Variável | Default | Efeito |
|---|---|---|
| `ENABLE_IMAGE_DESCRIPTION` | `true` | Liga/desliga describe **e** OCR. |
| `VISION_PROVIDER` | `florence2` | `florence2` ou `stub` (testes). |
| `VISION_MODEL_ID` | `florence-community/Florence-2-base-ft` | Trocar exige também `VISION_MODEL_REVISION` (validação no startup). |
| `VISION_MODEL_REVISION` | sha fixo (`0b03b6f…`) | Commit do repositório no Hugging Face. |
| `VISION_TRUST_REMOTE_CODE` | `false` | Só para repositórios `microsoft/Florence-2-*`, que executam código do Hub. |
| `VISION_MODEL_CACHE_DIR` | `/models/huggingface` | Volume `hf_cache` no compose. |
| `VISION_ALLOW_MODEL_DOWNLOAD` | `true` | `false` = `local_files_only` (air-gapped). |
| `VISION_PRELOAD_MODEL` | `false` | Carrega o modelo no boot do worker. |
| `VISION_MAX_IMAGE_SIZE_MB` | `10` | Não herda `MAX_FILE_SIZE_MB`. |
| `VISION_MAX_IMAGE_PIXELS` | `50000000` | |
| `VISION_REQUEST_TIMEOUT_SECONDS` | `60` | Prazo da requisição (deve ficar abaixo do timeout do proxy reverso). |
| `VISION_TASK_TIMEOUT_SECONDS` | `120` | Limite da task (o dobro do prazo da requisição, de propósito). |
| `VISION_MAX_NEW_TOKENS` | `1024` | |
| `VISION_NUM_BEAMS` | `3` | `1` reduz a latência em CPU. |
| `VISION_CAPTION_TASK` | `<MORE_DETAILED_CAPTION>` | |
| `VISION_TORCH_DTYPE` | `auto` | `auto` = float16 em CUDA, float32 em CPU. |
| `VISION_QUEUE` | `ingestify-vision` | |
| `DEVICE` | `auto` | Dispositivo compartilhado (Docling, Whisper, Florence-2). |

A imagem do worker inclui as dependências de visão por padrão
(`REQUIREMENTS_FILE=requirements-vision.txt` em
[docker/Dockerfile.worker](../../docker/Dockerfile.worker)). `make vision-download`
pré-baixa os pesos.

## Limites e lacunas conhecidas

- **Status no MySQL não é atualizado no sucesso.** O worker grava o resultado só no
  Redis; a linha em `jobs` fica `PENDING` (só falhas a marcam `FAILED`). `GET /jobs` mostra
  o status correto enquanto o status no Redis existe (24 h) e depois volta a mostrar
  `queued`.
- O resultado só vive no Redis (`RESULT_TTL_SECONDS`, 1 h): depois disso
  `/jobs/{id}/result` devolve `404`. A imagem não é guardada.
- `/jobs/{id}/result` foi pensado para recuperar o resultado após um `504`, mas o payload
  da visão não tem `markdown`, que o schema `JobResultResponse` exige — **não verificado**
  se essa rota responde corretamente para jobs de imagem.
- Um worker de visão por máquina; requisições concorrentes enfileiram e podem dar `504`.

## Com rota de visão (spec 0003, fatia 8)

Opcional. Com `engines.py routes set vision --step local`, cada requisição reserva uma vaga do
motor `local` (capacidade declarada de `vision`) dentro da própria requisição e entrega a reserva
ao worker; sem vaga, segue a fila `ingestify-vision` como sem rota; uma rota sem passo local e sem
motor que atenda agora responde `503 VISION_ENGINE_UNAVAILABLE` com `Retry-After`. Detalhes em
[engines.md](engines.md#visão-síncrona-fatia-8).
