# Visão: descrição, OCR, Full Analysis e rostos/expressões

## Rostos e expressões

`POST /images/faces` (JSON) e `POST /images/faces/upload` (multipart) oferecem
detecção simples (`face_options.mode=detection`) ou detecção, movimentos e
expressão estimada (`expressions`, padrão). Consulte
`GET /images/faces/capabilities` para disponibilidade por etapa, modelos e schema.
Ambas as criações exigem `Idempotency-Key`, localização de projeto e imagem;
replay devolve o mesmo job enquanto ele não falhou (ver tentativas abaixo, em análise
completa). `/jobs/{id}/result` conserva o resultado após F5/Redis expirado.

MediaPipe fornece caixas/confiança/keypoints e landmarks/blendshapes. O modelo
ONNX EmotiEffLib fixado oferece oito classes de expressão. Scores são estimativas
não calibradas de expressão visível, sem determinar estado emocional interno.
IDs de rosto são locais ao job; não existe reconhecimento de identidade.
Falhas e classificações inconclusivas são distintas de detecção vazia.

Full `image-full-v2` inclui as 15 famílias Florence e três faciais. Envie
`full_options.profile=image-full-v2`; `full_options.faces` permite thresholds e
até cinco rostos. O prazo único é de até 900s e o teto é 54 invocações incluindo
recuperação (32 Florence + 22 faciais). Omissão do perfil conserva v1. Operação
específica aceita até dez rostos, até 42 invocações e prazo de até 300s.
Campos exclusivos de expressão são recusados em `detection`; prazo dentro de
`faces` é recusado no Full. Limites e omissões ficam visíveis nos resultados.

Ativação administrada: aplique `PYTHONPATH=backend alembic upgrade head` com o ambiente do backend antes de usar os novos perfis. As migrações são aditivas e repetíveis.

Depois:

1. Instale `backend/requirements-faces.txt` no worker e as bibliotecas nativas
   `libegl1`/`libgles2` (incluídas no Dockerfile do worker).
2. No Compose, execute `make faces-download` para preencher o volume `ingestify-face-cache`,
   montado em leitura no worker. Fora do Compose, execute
   `python scripts/download_face_models.py --destination /models/faces` num ambiente
   com as dependências do backend. O instalador verifica todos os SHA-256.
3. Configure `FACE_MODEL_CACHE_DIR=/models/faces` e `FACE_ANALYSIS_ENABLED=true`
   na API e nos workers que atendem a fila de visão; reinicie-os e confira capabilities.

Os pesos não são baixados durante uma requisição. O manifesto
[`face_models.json`](../../backend/shared/face_models.json) registra origem,
licenças, versões, labels e pré-processamento. O custo do executor é liquidado
por lote; contadores e tempos dos adapters ficam separados no resultado/ledger,
com tentativas sem medição identificadas, sem inventar rate de custo por modelo.

As próximas seções descrevem as operações Florence existentes.

> Contratos dos endpoints revisados em 2026-10-06. Campos, modelos e autorização:
> [referência completa da API](../api-reference.md). As datas abaixo também registram revisões da implementação/operação.

> Verificado contra o código em 2026-10-05 (branch `main`). Fonte da verdade:
> [backend/api/image_routes.py](../../backend/api/image_routes.py),
> [backend/workers/vision_tasks.py](../../backend/workers/vision_tasks.py),
> [backend/workers/vision/](../../backend/workers/vision/),
> [backend/shared/schemas.py](../../backend/shared/schemas.py).
> Introduzido nos commits `5fd6461`, `6c4fffa`, `038b081`.
> Instalação, GPU, VRAM e download de pesos: [../GPU.md](../GPU.md).

## O que faz

Recebe uma imagem e executa uma das tarefas do modelo Florence integrado:

- **describe** — uma legenda/descrição em texto (tarefas Florence-2 `<MORE_DETAILED_CAPTION>`,
  `<DETAILED_CAPTION>` ou `<CAPTION>`);
- **ocr** — o texto da imagem e, por linha, o quadrilátero (`quad_box`, 8 valores) e o
  retângulo (`bbox`, 4 valores) em pixels da imagem original (`<OCR_WITH_REGION>`).

O formulário `/convert` permite descrição, OCR e as demais tarefas de análise,
incluindo seleção de uma região por arraste e os controles de geração. A página
do job mostra a imagem original, texto, caixas ou polígonos e permite baixar o
resultado. O guia bilíngue está em `/docs/images` e `/pt/docs/images`.

## Como usar

Todos exigem autenticação (JWT ou API key). Cada inferência precisa de um projeto:
`project` (nome; criado se não existir) ou `project_id` (ID existente), salvo uma API key
vinculada a projeto. `folder` / `folder_id` são opcionais. Não combine nome e ID do mesmo
recurso; pasta deve pertencer ao projeto; IDs alheios respondem `404`. Com JWT e key
juntos, vale o JWT e a vinculação da key não é usada. Imagens repetidas criam novos jobs;
não há deduplicação nessas rotas. A deduplicação por checksum de `/upload`/`/convert`
nunca devolve um job de imagem (é outra operação sobre os mesmos bytes), e a
`Idempotency-Key` de `mode=full`/rostos cobre a operação inteira (modo, opções, tarefa):
outra operação com a mesma chave é `409`.

| Método e caminho | Entrada |
|---|---|
| `POST /images/describe` | JSON `{image_base64, project?, project_id?, folder?, folder_id?, filename?, task?, tags?}` |
| `POST /images/describe/upload` | multipart `file`, localização, `task?`, `tags?` |
| `POST /images/ocr` | JSON `{image_base64, project?, project_id?, folder?, folder_id?, filename?, tags?}` |
| `POST /images/ocr/upload` | multipart `file`, localização, `tags?` |
| `GET /images/capabilities` | — (estado do subsistema; ver abaixo) |
| `POST /images/analyze` | JSON: imagem/localização, `mode=single/full`, `wait?`; single usa `task`, `text_input?`, `region?`, `generation?`; full usa `full_options?`, `datalake?` e header `Idempotency-Key` |
| `POST /images/analyze/upload` | multipart: arquivo/localização + os mesmos controles; `region`, `generation`, `full_options` e `datalake` são campos JSON |
| `POST /images/{job_id}/cancel` | Sem corpo; somente Full Analysis do dono, 202 em execução e 200 terminal |

As rotas `analyze` retornam **202** com `job_id` por padrão (`wait=false`).
`wait=true` espera e retorna 200 com o resultado, ou 504 sem cancelar a tarefa.
As rotas anteriores de descrição/OCR mantêm seu contrato síncrono.

### Todas as tarefas do processor Florence

O catálogo em `/images/capabilities` publica `tasks[]` com tarefa, rótulo,
entrada exigida e tipo de saída; `generation_schema` e `generation_defaults`
publicam os controles e os padrões do worker. São 15 tarefas verificadas no
processor instalado, sem converter tarefas de segmentação em OCR ou Markdown.

| Tarefa | Entrada adicional | Saída |
|---|---|---|
| `<CAPTION>` | — | Descrição breve |
| `<DETAILED_CAPTION>` | — | Descrição detalhada |
| `<MORE_DETAILED_CAPTION>` | — | Descrição muito detalhada |
| `<OCR>` | — | Texto |
| `<OCR_WITH_REGION>` | — | Texto, linhas e quadriláteros |
| `<OD>` | — | Caixas e classes de objetos |
| `<DENSE_REGION_CAPTION>` | — | Caixas e descrições |
| `<REGION_PROPOSAL>` | — | Propostas de regiões |
| `<CAPTION_TO_PHRASE_GROUNDING>` | `text_input` | Caixas associadas às frases |
| `<REFERRING_EXPRESSION_SEGMENTATION>` | `text_input` | Polígonos do objeto descrito |
| `<OPEN_VOCABULARY_DETECTION>` | `text_input` | Caixas e/ou polígonos de objetos descritos |
| `<REGION_TO_SEGMENTATION>` | `region` | Polígonos da região |
| `<REGION_TO_CATEGORY>` | `region` | Classe da região |
| `<REGION_TO_DESCRIPTION>` | `region` | Descrição da região |
| `<REGION_TO_OCR>` | `region` | Texto da região |

`region=[x_min,y_min,x_max,y_max]` usa coordenadas normalizadas entre 0 e 1,
com mínimos menores que máximos. Texto obrigatório não pode ser vazio; texto e
região são rejeitados nas tarefas que não os usam. As **saídas** geométricas
usam pixels da imagem original. `output` preserva a resposta do processor;
`regions[]` a normaliza como `label`, `bbox`, `quad_box` e `polygons`.

`generation` aceita `max_new_tokens` (1..1024, contexto do checkpoint integrado), `num_beams` (1..8), `do_sample`,
`temperature` (>0..2), `top_p` (>0..1), `top_k` (0..100),
`repetition_penalty` (0.5..3), `length_penalty` (-2..2),
`no_repeat_ngram_size` (0..20) e `early_stopping` (booleano ou `"never"`).
Controles de amostragem personalizados exigem `do_sample=true`; controles de
beam personalizados exigem `num_beams>1`. Campos desconhecidos são rejeitados.
Tokens/beams omitidos usam a configuração do worker, registrada no resultado.

```bash
curl https://dev.ingestify.ai/api/images/analyze/upload \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "file=@foto.jpg" -F "project=Documentos" \
  --form-string 'task=<OPEN_VOCABULARY_DETECTION>' \
  --form-string 'text_input=a red car' \
  --form-string 'generation={"max_new_tokens":512,"num_beams":1}'
```

Referências: [processor Florence](https://huggingface.co/docs/transformers/model_doc/florence2),
[checkpoint integrado](https://huggingface.co/florence-community/Florence-2-base-ft).

- `image_base64` aceita o prefixo `data:image/...;base64,` e quebras de linha.
- `task` padrão: `<MORE_DETAILED_CAPTION>` (configurável por `VISION_CAPTION_TASK`).
  Só aceita as três tarefas de descrição acima; não é um campo de prompt livre. OCR
  sempre usa `<OCR_WITH_REGION>` e não recebe `task`.
- `tags` é uma lista no JSON e texto separado por vírgula no multipart.
- Formatos aceitos (detectados pelos *magic bytes*, não pela extensão): PNG, JPEG, WEBP,
  BMP, GIF, TIFF.
- Limites padrão: 10 MB da imagem decodificada e 50 milhões de pixels.

```bash
curl -X POST http://localhost:8000/images/describe/upload \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "file=@foto.jpg" -F "project=Documentos" \
  --form-string "task=<CAPTION>"

curl -X POST http://localhost:8000/images/ocr/upload \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "file=@recibo.png" -F "project=Documentos" -F "folder=Recibos"
```

Use `--form-string` para os tokens `<…>`: o `-F` do curl interpreta um valor começando
em `<` como leitura de arquivo. Exemplo JSON em Python (sem limite de argumentos do shell):

```python
import base64
import requests

with open("recibo.png", "rb") as file:
    image = base64.b64encode(file.read()).decode("ascii")

response = requests.post(
    "http://localhost:8000/images/ocr",
    headers={"X-API-Key": "SUA_CHAVE"},
    json={"image_base64": image, "filename": "recibo.png",
          "project": "Documentos", "folder": "Recibos", "tags": ["ocr"]},
    timeout=75,
)
response.raise_for_status()
print(response.json()["text"])
```

Resposta comum: `job_id`, `status: "completed"`, `image_base64` (eco byte a byte da imagem
enviada), `image_mime_type`, `image_bytes`, `image_sha256`, `width`, `height`,
`model {model_id, revision, device, dtype}`, `duration_ms`, `project` e `folder`; mais `description` e `task`
(describe) ou `text` e `lines[]` (ocr). Imagem sem texto no OCR é `200` com `text: ""` e
`lines: []`.

`duration_ms` é o tempo reportado pelo worker; não inclui necessariamente fila, upload
e resposta HTTP. Exemplo ilustrativo dos campos de OCR (os demais campos comuns foram
omitidos):

```json
{
  "text": "TOTAL 42.00",
  "lines": [{
    "text": "TOTAL 42.00",
    "quad_box": [12, 20, 180, 20, 180, 40, 12, 40],
    "bbox": [12, 20, 180, 40]
  }]
}
```

`quad_box` contém `[x1,y1,x2,y2,x3,y3,x4,y4]`; `bbox` contém
`[x_min,y_min,x_max,y_max]`, ambos em pixels absolutos da imagem original.

### Erros

Erros produzidos pela rota usam `{"detail": {"error_code", "message", "job_id", ...}}`.
Erros de autenticação, tags e validação Pydantic podem usar outro formato de `detail`.

| HTTP | `error_code` | Quando |
|---|---|---|
| 413 | `IMAGE_TOO_LARGE` | Mais que `VISION_MAX_IMAGE_SIZE_MB`. |
| 422 | `IMAGE_TOO_LARGE` | Mais pixels que `VISION_MAX_IMAGE_PIXELS` (proteção contra bomba de descompressão). |
| 422 | `INVALID_BASE64` / `UNSUPPORTED_IMAGE_FORMAT` / `UNSUPPORTED_CAPTION_TASK` | Entrada inválida. |
| 503 | `VISION_DISABLED` | `ENABLE_IMAGE_DESCRIPTION=false`. |
| 503 | `JOB_PERSISTENCE_UNAVAILABLE` | O job e sua configuração não puderam ser salvos; nenhuma imagem foi enfileirada. |
| 503 | `VISION_ENGINE_UNAVAILABLE` | Roteamento configurado sem motor disponível; respeite o header `Retry-After`. |
| 503 | `VISION_DEPENDENCIES_MISSING`, `VISION_MODEL_NOT_DOWNLOADED`, `VISION_MODEL_LOAD_FAILED`, `VISION_DEVICE_UNAVAILABLE`, `CELERY_UNAVAILABLE` | Worker sem torch/transformers, pesos ausentes com download desabilitado, falha de carga, `DEVICE=cuda` sem GPU, broker fora. |
| 504 | `VISION_TIMEOUT` | Passou do prazo de espera síncrona; detail inclui job_id/poll_url/result_url. A tarefa continua e pode ser consultada pelo mesmo job. |

No `504`, salve `detail.job_id` e acompanhe `poll_url`. Não reenvie automaticamente a
imagem: uma nova inferência criará outro job. Exemplo ilustrativo:

```json
{
  "detail": {
    "error_code": "VISION_TIMEOUT",
    "message": "O job continua processando.",
    "job_id": "7186e44b-3098-4590-9b5f-a29e9991e4e7",
    "poll_url": "/jobs/7186e44b-3098-4590-9b5f-a29e9991e4e7",
    "result_url": "/jobs/7186e44b-3098-4590-9b5f-a29e9991e4e7/result"
  }
}
```

### `GET /images/capabilities`

Lê um heartbeat que o worker de visão publica no Redis (`vision:worker:heartbeat`,
TTL 45 s, renovado a cada 15 s numa thread que roda inclusive durante a inferência). Não
enfileira nada. Campos: `enabled`, `provider`, `model_id`, `revision`, `device_requested`,
`device_resolved`, `torch_available`, `cuda_available`, `cuda_device_name`,
`dependencies_installed`, `model_downloaded`, `model_loaded`, `trust_remote_code`,
`reason`. Sem heartbeat recente: `dependencies_installed=false` e `reason` explicando que
não há worker.
Quando a feature está habilitada, essa sonda retorna `200` mesmo com worker ausente;
quando `ENABLE_IMAGE_DESCRIPTION=false`, responde `503 VISION_DISABLED`.

## O que acontece por dentro (tarefas individuais)

1. A API valida tamanho e formato e salva um job MAIN (`source_type="image"`) e sua
   configuração no MySQL antes de despachar. Se essa gravação falhar, responde
   `503 JOB_PERSISTENCE_UNAVAILABLE` sem enfileirar a imagem. O Redis recebe uma
   cópia de cache; o job continua consultável pelo banco quando esse cache expira.
2. Grava a imagem em `{TEMP_STORAGE_PATH}/images/{job_id}/` (os bytes **não** passam pelo
   broker e **não** vão para o MinIO).
3. Envia a task para a fila dedicada `VISION_QUEUE` (`ingestify-vision`), consumida pelo
   serviço `worker-vision` (`--concurrency=1`, um modelo residente por máquina).
4. Espera o resultado sem bloquear o event loop, até `VISION_REQUEST_TIMEOUT_SECONDS`.
5. O worker roda o Florence-2, grava o resultado no Redis e no objeto privado de
   resultados do MinIO, atualiza o status no MySQL e apaga a
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

## Consulta, persistência e limites

`GET /jobs/{id}/result?format=markdown` retorna o envelope padrão com `markdown`,
`metadata` e `image`: tarefa, entrada/configuração, imagem original, dimensões,
modelo e resultado próprio. O status é mantido no MySQL. Para describe/ocr/analyze
single, o resultado completo é salvo em `images/{job_id}/result.json` no bucket privado
de resultados, com referência em `jobs.minio_result_path` (é a cópia durável que a
entrega ao datalake lê), mas `GET /jobs/{id}/result` lê o Elasticsearch e depois o Redis
(`job:{id}:result`, cache com TTL): depois que o cache expira, o resultado nativo não é
mais servido por essa rota. Full Analysis e rostos são lidos do relatório no MinIO. A
exclusão do job remove esses objetos. O handoff temporário é apagado ao terminar a
tarefa.

Requisições síncronas concorrentes podem ultrapassar o prazo de espera. Prefira
`analyze` com `wait=false` para acompanhar a fila sem manter uma conexão aberta.

## Guardar ou apagar a imagem original (`purge_source`)

Todas as rotas de imagem aceitam `purge_source` (padrão `false`, mesmo nome e sentido de
`/upload`, `/convert` e `/transcribe`): campo de formulário em `/images/describe/upload`,
`/images/ocr/upload`, `/images/analyze/upload` e `/images/faces/upload`; campo booleano do
corpo JSON em `/images/describe`, `/images/ocr`, `/images/analyze` (single e `mode=full`) e
`/images/faces`. Valor que não é booleano → `422`, sem criar job.

Onde o original de um job de imagem fica guardado hoje (todas contam como "original"):

| Cópia | Rotas | Ciclo de vida sem `purge_source` |
|---|---|---|
| handoff local `{TEMP_STORAGE_PATH}/images/{job_id}/` | todas (Full/rostos: `.../{job_id}/{holder}/full-source`) | a própria task apaga no `finally`; `cleanup_old_jobs` (`sweep_image_handoffs`) varre o que um worker morto deixou |
| `image.image_base64` do resultado (`images/{job_id}/result.json` + `job:{id}:result`) | describe, ocr, analyze single | fica enquanto o job existir |
| `images/{job_id}/source` (bucket de resultados, `ImageAnalysisRun.source_path`) | Full, rostos | fica enquanto o job existir |
| prévia PNG em tamanho real, normalizada (`images/{job_id}/preview/…`) e embutida no relatório (`image.image_base64`) | Full, rostos | fica enquanto o job existir |

O resto é resultado derivado e fica sempre: descrição, OCR, regiões, rostos (caixas,
landmarks e expressões são coordenadas e rótulos, nunca recortes), markdown e as saídas
por etapa (`images/{job_id}/steps/…`). O eco `image_base64` da resposta síncrona
de describe/ocr e de analyze single com `wait=true` vem dos bytes da própria requisição,
não de uma cópia guardada (Full Analysis e rostos respondem com o relatório, que traz
`image.image_base64: null`); o valor que a task devolve ao backend de resultados do
Celery nunca carrega a imagem.

Com `purge_source=true`:

- a opção fica no job (`jobs.purge_source`, e em `configuration.options.purge_source`);
- os workers gravam o resultado/relatório **sem** a imagem (`image.image_base64: null`,
  também no Redis e no que vai para o datalake);
- quando o job termina — `completed`, `failed`, `partial` ou `cancelled` (rotas de imagem
  não têm retry automático: as tasks nativas usam `max_retries=0`, e a Full Analysis só
  termina quando `finish` grava o estado final) — o worker apaga o handoff, o
  `images/{job_id}/source`, todas as prévias e grava `jobs.source_deleted_at`. Uma falha
  antes de chegar ao worker (fila fora, sem motor) também grava `source_deleted_at`: o
  handoff, única cópia, já foi apagado;
- falha ao apagar (MinIO fora no fim do job) nunca muda o job e deixa
  `source_deleted_at` vazio; a task periódica `workers.image_full_tasks.reconcile` refaz
  o purge desses jobs (`purge_source=true`, terminados, `source_deleted_at` nulo), no
  máximo uma vez por minuto e até 20 jobs por vez, mais antigos primeiro. É idempotente:
  cada tentativa reconfere tudo sob o lock da linha do job, e o sucesso grava
  `source_deleted_at`, que tira o job da fila. `DELETE /jobs/{id}/source` também termina;
- um worker de Full Analysis/rostos que perdeu o lease (o reconciliador fechou o run, ou
  o job já terminou e foi purgado) apaga a prévia que acabou de gravar; no `finally`, se
  o original já foi apagado, apaga todo `images/{job_id}/preview/`, e se a prévia dele
  não é a do run, apaga a dele.

`GET /jobs/{id}` diz a verdade para jobs de imagem: `source_available` é `true` só enquanto
alguma cópia acima existe (handoff com arquivo, `source_path`/`preview_path` do run, qualquer
objeto listado em `images/{job_id}/source`, `images/{job_id}/preview/` ou um relatório que
não é o selecionado, ou um resultado nativo — no MinIO ou no Redis — que ainda embute a
imagem). Um job nativo que falhou sem `purge_source`
responde `source_available: false` com `source_deleted_at: null` (a task já apagou o
handoff, a única cópia). `DELETE /jobs/{id}/source` funciona para jobs de imagem: apaga as
cópias que restam (reescreve o resultado sem `image_base64`; o relatório da Full Analysis é
gravado sob o novo hash, o novo caminho é gravado no MySQL, e só depois o antigo é apagado;
quem lê com `wait=true` no meio relê o caminho), `404` quando não há nenhuma, `409
JOB_STILL_PROCESSING` enquanto o job está na fila ou processando. Entregas já feitas a um
datalake do usuário não são alcançadas por `DELETE` (com `purge_source=true` elas nunca
recebem a imagem).

Sem deduplicação: rotas de imagem continuam criando um job por requisição. Na Full Analysis
e em rostos, `purge_source` **não** faz parte do fingerprint da `Idempotency-Key`: repetir a
chave com outro `purge_source` devolve a tentativa existente sem mudar nada (nem liga nem
desliga o purge daquele job; use `DELETE /jobs/{id}/source`). Depois de uma tentativa
`failed`, a próxima tentativa da mesma chave usa o `purge_source` do novo pedido. O
formulário do front gera uma chave nova quando a opção muda.

```bash
curl -X POST http://localhost:8000/images/ocr/upload \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "file=@recibo.png" -F "project=Cursos" -F "purge_source=true"
```

## Com rota de visão (spec 0003, fatia 8)

Opcional. Com `engines.py routes set vision --step local`, cada requisição reserva uma vaga do
motor `local` (capacidade declarada de `vision`) dentro da própria requisição e entrega a reserva
ao worker; sem vaga, segue a fila `ingestify-vision` como sem rota; uma rota sem passo local e sem
motor que atenda agora responde `503 VISION_ENGINE_UNAVAILABLE` com `Retry-After`. Detalhes em
[engines.md](engines.md#visão-síncrona-fatia-8).

## Full Analysis de imagens

Em `/convert`, **Full Analysis** reúne as 15 famílias num único job: descrições,
OCR, objetos, grounding, regiões e segmentações. Consultas e regiões são derivadas
automaticamente; entradas avançadas explícitas substituem as derivadas do mesmo tipo.
A interface mostra cobertura por tarefa e permite selecionar camadas e baixar JSON/Markdown.

Use as rotas `/images/analyze` (JSON) ou `/images/analyze/upload` (multipart) com
`mode=full` e header `Idempotency-Key` obrigatório, de 1 a 128 caracteres.
Repetir chave e payload recupera o mesmo job; payload diferente (outro modo, outras
opções) retorna 409. A chave vale por **tentativa**: enquanto a última tentativa está na
fila, processando ou terminou sem `failed`, a mesma chave a devolve; se ela terminou
`failed`, a mesma chave cria a tentativa seguinte (um job novo) em vez de devolver o job
falho. A resposta traz `attempt` (1, 2, …). O contador fica em
`image_analysis_submissions.attempt` (migração aditiva `a7d30021c5e9`); duas requisições
simultâneas com a mesma chave depois de uma falha criam um único job (compare-and-set em
`(id, attempt, job_id)`; a outra devolve o job vencedor).
Chave de job excluído retorna 410 por pelo menos 24h e até confirmar a limpeza.
Use outra chave para uma nova análise intencional.

```bash
curl "$API_URL/images/analyze/upload" \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -H "Idempotency-Key: image-full-example-001" \
  -F "file=@photo.jpg" \
  -F "project=Análises de imagens" \
  --form-string 'mode=full' \
  --form-string 'full_options={"queries":["a red car"],"generation":{"max_new_tokens":1024,"num_beams":3},"deadline_seconds":900}'
```

JSON equivalente: `{"mode":"full","image_base64":"...","project":"Análises de imagens","full_options":{...}}`.
Omitir `full_options` usa entradas automáticas. `queries` aceita até 3 textos
(total até 2000 caracteres); `regions` aceita até 4 retângulos normalizados
`[x_min,y_min,x_max,y_max]`. O padrão inclui a imagem inteira e até 3 candidatos.
O máximo inicial é 31 chamadas, com teto de 32 incluindo recuperação.
Não representa todas as combinações possíveis de parâmetros.

Full rejeita `task`, `text_input`, `region` e `generation` na raiz; geração fica
em `full_options.generation`. Multipart codifica `full_options` e `datalake`
como JSON. O destino opcional usa `Destination` com `connection_id`, `bucket`,
`partitioning` e `partition_values`, congelado na criação. Resultados `partial`
podem ser exportados; o envelope e o dataset preservam `analysis_status`.

A resposta padrão 202 contém `job_id`, `poll_url` e `result_url`. `wait=true`
espera até o prazo HTTP; 504 mantém o mesmo job. `GET /jobs/{id}` inclui
`image_analysis` com progresso, chamadas, cancelamento e deadline. Prazo total
máximo: 900s desde a admissão, incluindo fila, carga, inferência e persistência.
`POST /images/{id}/cancel` preserva checkpoints: 202 enquanto processa, 200 terminal.

`GET /jobs/{id}/result` retorna 202 enquanto processa. Ao terminar, o envelope
contém `image.operation=full_analysis`, `analysis_status`, `coverage`,
`resolved_inputs`, `calls_started`, `results[]` e Markdown. `?format=json` entrega
o envelope bruto; `?format=markdown` mantém o envelope padrão. Estados finais:
`completed`, `partial`, `failed`, `cancelled`. Só `completed` indica cobertura
integral sem truncamento e persistência durável. Cada etapa mantém output nativo,
texto, linhas/caixas/polígonos, motivo, tentativas, duração e metadados de geração.
A imagem PNG canônica mantém as mesmas coordenadas, sem rotação EXIF posterior;
GIF/TIFF usa o primeiro frame.

Fonte, checkpoints e relatório ficam privados no MinIO; SQL controla claims,
fences, limites e caminhos selecionados. Redis é cache. A recuperação reutiliza
checkpoints e repete no máximo uma vez uma etapa incerta, dentro do teto e prazo.
Com rota de engine ativa, o lote aguarda reserva e contabiliza o processamento;
indisponibilidade de capacidade não libera execução fora da admissão.

Execute `python scripts/migrate_image_full_analysis.py` antes de reiniciar API,
worker de visão, worker geral e beat com o mesmo código. Reconstrua o frontend.
A migração aditiva cria três tabelas `image_analysis_*` e acrescenta `PARTIAL`
ao enum SQL de jobs. É repetível. Alembic: `01b5000bd5d4`, após `f0a4000ac4c3`.
Downgrade exige não haver lotes retidos e mantém o enum aditivo histórico.
`VISION_FULL_TASK_TIMEOUT_SECONDS=900` configura o prazo máximo, limitado a 900s.
`/images/capabilities` publica `analysis_modes`, `full_profile` e `full_limits`.

O guia publicado em `/pt/docs/images#full-analysis` e `/docs/images#full-analysis` inclui exemplos automáticos/avançados multipart, envio JSON/Python, acompanhamento, cancelamento, formatos de resultado e datalakes. Todas as oito rotas de imagens aparecem na tabela do guia.
