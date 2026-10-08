# Conversão de documentos (Docling)

> Verificado contra o código em 2026-10-05 (branch `main`).
> Fonte da verdade: [backend/api/routes.py](../../backend/api/routes.py),
> [backend/workers/tasks.py](../../backend/workers/tasks.py),
> [backend/workers/converter.py](../../backend/workers/converter.py),
> [backend/shared/pdf_splitter.py](../../backend/shared/pdf_splitter.py),
> [backend/shared/conversion_assets.py](../../backend/shared/conversion_assets.py),
> [backend/workers/image_assets.py](../../backend/workers/image_assets.py).

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
| `purge_source` | não | `false` | `true` apaga os arquivos de origem (o enviado e os PDFs por página) quando o job termina — `completed`, ou `failed`/`partial` depois das tentativas automáticas (ver [Guardar ou apagar o original](#guardar-ou-apagar-o-arquivo-original-purge_source)). |

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
(URL, file ID ou path; ignorado quando `source_type=file`), `file`, `name`, `tags`,
`purge_source` e os mesmos campos de projeto/pasta do `/upload`. Não envie JSON: o contrato da rota é form.
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

### Deduplicação por checksum (por operação e por tentativa)

Nos dois endpoints, quando há arquivo, a API calcula o SHA-256 enquanto grava o upload em
disco. Se o mesmo usuário já tem um job `MAIN` com o mesmo checksum, **a mesma operação**
e **no mesmo projeto**, a resposta devolve o `job_id` existente (`duplicate: true`,
`message` "Arquivo já foi processado anteriormente…") e as tags enviadas são
**adicionadas** ao job existente. A pasta original é preservada. Enviar para outro projeto
cria uma conversão independente.

- **Operação.** A chave inclui o que muda o resultado: numa conversão, o `docling_preset`
  (`/convert` não tem preset: usa os defaults); numa transcrição, o perfil de
  processamento. O mesmo arquivo com outro preset é outro job. Jobs de imagem
  (`/images/describe`, `/images/ocr`, `/images/analyze`, rostos) nunca são devolvidos
  pela deduplicação de documentos, mesmo com os mesmos bytes. A chave fica na coluna
  `jobs.operation_key` (nunca na configuração solicitada); um job criado antes dela
  responde a qualquer conversão do mesmo arquivo, como antes.
- **`/upload` e `/convert` não deduplicam entre si.** O `/upload` sem `docling_preset`
  usa o preset `fast`; o `/convert` não aceita preset (chave "sem preset", defaults
  `DOCLING_*`). São operações diferentes: o mesmo arquivo enviado a um e depois ao outro
  cria **dois jobs**. Só reenvios ao mesmo endpoint (com o mesmo preset) devolvem o job
  existente.
- **Tentativa.** Um job que terminou com falha (`failed`, ou `partial` — páginas que
  falharam depois das tentativas automáticas) nunca é devolvido: reenviar o arquivo é a
  nova tentativa e cria outro job.
- **`purge_source`.** Com `purge_source=true` a duplicata devolvida passa a apagar a
  origem: se ela já terminou, na hora (`source_available` na resposta diz o resultado;
  uma falha ao apagar não falha o pedido), senão quando terminar. Com `false` (manter), um
  job cuja origem já foi apagada, ou foi pedida para ser apagada, não é reaproveitado: um
  job novo é criado, e `message` cita o job anterior.

O projeto vem do request ou, quando não há campo de projeto, da API key vinculada.
Com JWT e API key juntos, vale o JWT e a vinculação da key não é usada. IDs de projetos
ou pastas de outro usuário retornam `404`. Nomes usam a normalização compartilhada
(sem diferenciar maiúsculas, espaços repetidos e acentos latinos; até 100 caracteres).

### Guardar ou apagar o arquivo original (`purge_source`)

Por padrão os arquivos de origem ficam guardados: o original em
`ingestify-uploads/uploads/{job_id}/…` (é dele que o retry de página restaura o PDF) e,
num PDF dividido, os PDFs por página em `ingestify-pages/pages/{job_id}/…` (servidos por
`/jobs/{id}/pages/{n}/pdf`). Com `purge_source=true` em `/upload` ou `/convert` (mesmo
nome e sentido do parâmetro do `/transcribe`):

- **O que é apagado:** o original (objeto no MinIO e cópias locais em
  `{TEMP_STORAGE_PATH}/uploads/{job_id}/` e no diretório de trabalho
  `{TEMP_STORAGE_PATH}/{job_id}/`, onde fica o download de URL/Drive/Dropbox) e os PDFs
  por página (MinIO e locais). **Ficam** o Markdown do documento e de cada página, e o
  índice de busca. As imagens extraídas (`image_mode`/`page_images`) **não** são apagadas
  aqui: seguem a [retenção própria](#imagens-do-documento-image_mode-page_images)
  (`ASSET_RETENTION_SECONDS`).
- **Quando:** quando o job MAIN termina de vez — `completed` (documento único ao fim da
  conversão; PDF dividido depois do merge), ou `failed` / `partial` **depois de
  esgotadas as tentativas automáticas** (retries do Celery de `process_conversion`,
  `convert_page_task`/`process_page` e `merge_pages_task`, e do backlog de engines).
  Nunca enquanto houver retry agendado, página na fila ou em processamento.
- **Depois:** `GET /jobs/{id}` responde `source_available: false` e `source_deleted_at`
  (UTC); `GET /jobs/{id}/pages/{n}/pdf` responde `410` `SOURCE_PURGED` com a data; o
  retry manual de página responde `409` `SOURCE_NOT_AVAILABLE` (a interface esconde o
  botão e explica).

A escolha é gravada com o job no MySQL (coluna `jobs.purge_source`; quando veio no
próprio pedido, também na configuração solicitada, `job_configurations.options.purge_source`),
não só na mensagem do Celery: o merge depois de um retry, em qualquer worker, a respeita.
Uma duplicata com `purge_source=true` grava só a coluna (não reescreve a configuração
solicitada do job existente). A data do apagamento fica em `jobs.source_deleted_at`
(migração Alembic `b8f20022e1c4`). Se o MinIO recusar o apagamento, o erro é registrado
no log, o que não foi apagado continua referenciado e o status do job **não muda**.

Todo apagamento (worker ao assentar o job, duplicata, `DELETE /jobs/{id}/source`) e todo
retry de página (manual, `POST /admin/jobs/{id}/retry-all-failed`, auto-retry do
monitoramento) usam o mesmo lock da linha do job MAIN (`SELECT … FOR UPDATE`): o
apagamento reconfere sob o lock que nada está pendente e só faz commit depois de apagar
tudo; o retry, se chegar depois, responde `409 SOURCE_NOT_AVAILABLE` sem mudar nada.

Um reenvio do mesmo arquivo segue as regras da
[deduplicação](#deduplicação-por-checksum-por-operação-e-por-tentativa).

```bash
curl -X POST http://localhost:8000/upload \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "file=@contrato.pdf" \
  -F "project=Cliente X" \
  -F "purge_source=true"
```

Para apagar os arquivos de origem de um job já terminado, sem ter enviado `purge_source`:

```bash
curl -X DELETE "http://localhost:8000/jobs/$JOB_ID/source" -H "X-API-Key: $INGESTIFY_API_KEY"
# {"job_id":"<uuid>","source_deleted":true,"source_deleted_at":"2026-10-07T21:30:00"}
```

`404` se o job não existe, não é seu ou já não tem arquivos de origem; `409`
(`code: JOB_STILL_PROCESSING`) enquanto o job, uma página ou um retry automático está
pendente (o campo `source_deletable` de `GET /jobs/{id}` diz se pode agora). Ver
[jobs-api.md](jobs-api.md#delete-jobsjob_idsource). Na interface: caixa "Don't keep the
original file after converting" no formulário de arquivo, botão "Delete original files" e
a data "Original files deleted on …" na página do job.

Não há a opção nas abas URL / Google Drive / Dropbox (que enviam para `POST /convert`):
essas fontes não guardam original no MinIO; o arquivo baixado só existe no diretório de
trabalho e já é apagado quando o job completa. A API aceita `purge_source` nelas (apaga o
download e os PDFs por página quando o job falha de vez, e dá às imagens extraídas a
retenção de `ASSET_RETENTION_SECONDS`), mas a interface não oferece: nelas as imagens
duram o mesmo que o job.

### Imagens do documento (`image_mode`, `page_images`)

Por padrão (`image_mode=none`) nada muda: o Docling roda com
`generate_picture_images=False` (preset `fast`) e o Markdown traz `<!-- image -->` no
lugar de cada figura; nenhuma imagem sai do Ingestify. Os dois campos de form, em
`/upload` e `/convert`:

| Campo | Valores | Efeito |
|---|---|---|
| `image_mode` | `none` (padrão) \| `referenced` | `referenced`: liga `generate_picture_images` (escala `CONVERSION_IMAGES_SCALE`, padrão 2.0 = 144 DPI; só neste modo — `none` com os presets `balanced`/`quality` mantém a escala padrão do Docling, custo e saída iguais aos de antes), guarda cada `PictureItem` como PNG e o Markdown passa a referenciá-lo: `![Image](/jobs/{job_id}/assets/{name})` (caminho relativo da API). Outro valor: `422`. |
| `page_images` | `false` (padrão) \| `true` | Só PDF: renderiza cada página como PNG com pypdfium2 (`CONVERSION_PAGE_IMAGE_DPI`, padrão 150). Não aparece no Markdown. Funciona com ou sem `image_mode`. |

Como o Markdown referencia as figuras: o worker percorre os `PictureItem` do documento
Docling na ordem do documento, grava cada PNG e põe a URL do asset em
`picture.image.uri`; o export é `export_to_markdown(image_mode=ImageRefMode.REFERENCED)`
(docling-core 2.100). Uma figura pulada fica com `image=None` e o export escreve o
placeholder; nenhuma figura sai como `data:` URI.

O resultado (`GET /jobs/{job_id}/result`) ganha:

```json
{
  "markdown": "## Aula 1\n\n![Image](/jobs/<job_id>/assets/p0001-img01-3f2a9c1b7d4e.png)",
  "assets": [
    {"name": "p0001-page-9b1c0d2e3f4a.png", "kind": "page", "page": 1, "bbox": null,
     "sha256": "9b1c…", "mime": "image/png", "width": 1275, "height": 1650,
     "size_bytes": 182311, "url": "/jobs/<job_id>/assets/p0001-page-9b1c0d2e3f4a.png"},
    {"name": "p0001-img01-3f2a9c1b7d4e.png", "kind": "picture", "page": 1,
     "bbox": {"l": 99.8, "t": 265.7, "r": 400.0, "b": 492.1, "coord_origin": "TOPLEFT",
              "page_width": 612.0, "page_height": 792.0},
     "sha256": "3f2a…", "mime": "image/png", "width": 601, "height": 453,
     "size_bytes": 48213, "url": "/jobs/<job_id>/assets/p0001-img01-3f2a9c1b7d4e.png"}
  ],
  "assets_skipped": {"too_small": 0, "count_limit": 0, "size_limit": 0, "unavailable": 0}
}
```

- Ordem: página, depois a página renderizada, depois as figuras na ordem do documento.
- Nomes: `p{página:04d}-img{índice:02d}-{sha256[:12]}.png` (índice 1-based na página) e
  `p{página:04d}-page-{sha256[:12]}.png`; página `0000` em formatos sem página (DOCX…).
- `bbox`: pontos PDF, origem no canto superior esquerdo, com o tamanho da página.
- Sem `image_mode`/`page_images`, `assets` e `assets_skipped` vêm `null` e o Markdown é
  idêntico ao de antes.
- Limites (`assets_skipped`): figura menor que `CONVERSION_ASSET_MIN_PX` (32) em qualquer
  lado → `too_small`; mais de `CONVERSION_ASSET_MAX_COUNT` (500) assets ou
  `CONVERSION_ASSET_MAX_TOTAL_MB` (200) por job → `count_limit` / `size_limit`;
  imagem que o Docling não entregou → `unavailable`. Figura pulada fica como placeholder.
- Uma página que é só uma imagem (escaneada) nem sempre vira `PictureItem` no Docling (o
  layout pode tratá-la como fundo): use `page_images=true` para ter a página inteira.

**Onde ficam:** bucket de resultados, `assets/{job_id_principal}/{name}`. A lista durável é
`jobs.assets_manifest` (gravada junto com o `completed`); o Elasticsearch guarda só o
Markdown. Baixe com `GET /jobs/{job_id}/assets/{name}` (ver
[jobs-api.md](jobs-api.md#get-jobsjob_idassetsname)).

**PDF dividido:** cada job de página extrai as próprias imagens com o número **absoluto**
da página e grava direto sob o job principal (URLs já em `/jobs/{principal}/assets/…`).
Os limites do job valem para todas as páginas juntas, em duas camadas:

1. **Reserva no Redis, antes de codificar e enviar** (`JobAssetBudget`): cada posição
   (`p0003-img02`, `p0003-page`) reserva uma vaga em `job:{id}:assets:slots` e seus bytes
   em `job:{id}:assets:bytes` (TTL 24 h). Esgotada a contagem ou os bytes, a página nem
   renderiza/codifica a imagem (`count_limit`/`size_limit`). Um retry da mesma página
   reaproveita a própria vaga. Quem fica com o orçamento depende da ordem em que as
   páginas terminam.
2. **O merge é a autoridade** (`combine_pages`, em ordem de página): o que passar do limite
   sai da lista, vira placeholder no Markdown e o PNG é apagado. Sem Redis, cada página
   aplica só os próprios limites e o merge corta o excedente.

**Opções duráveis:** `image_mode`/`page_images` ficam na configuração pedida do job
(`JobConfiguration.options`, só quando diferentes do padrão); o worker as relê do banco no
`process_conversion` e em cada página (retry de página e merge as respeitam mesmo que a
mensagem do Celery não as traga).

**Nunca URL sem manifesto:** o worker grava `jobs.assets_manifest` **antes** de publicar
qualquer resultado (Redis, Elasticsearch, páginas). Se essa gravação falhar, as referências
voltam a `<!-- image -->`, os PNGs são apagados e o resultado sai sem `assets`. O merge
lista as imagens que as páginas guardaram mesmo que não consiga ler as opções do job.

**Job que termina sem manifesto** (`failed`/`partial`, com ou sem `purge_source`): as
imagens das páginas que completaram e ainda têm resultado ganham um manifesto (ficam
baixáveis e seguem a retenção normal: um `partial` pode ser completado por retry de
página, que refaz o manifesto no merge); sem nada listável (documento único que falhou,
resultados de página expirados), `assets/{id}/` é apagado.

**Retenção:**

- Sem `purge_source`, as imagens duram o mesmo que o job (`DELETE /jobs/{id}` apaga
  `assets/{id}/`).
- Com `purge_source=true`, o original e os PDFs por página seguem a regra de sempre, mas
  as imagens **não** são apagadas quando o job termina (o cliente precisa baixá-las): o
  purge grava `jobs.assets_expire_at = agora + ASSET_RETENTION_SECONDS` (padrão 3600) e a
  task periódica `workers.image_full_tasks.reconcile` (no máximo uma vez por minuto em todo
  o cluster — lock Redis `assets:expiry:lock`; sem Redis, por processo —, até 20 jobs por
  vez, a expiração mais antiga primeiro, sob o lock da linha do job, idempotente) apaga
  `assets/{id}/` e grava `jobs.assets_deleted_at`. Uma exclusão que falha é adiada 5 min
  (`ASSET_EXPIRY_RETRY_SECONDS`), para não travar o lote. Uma duplicata com `purge_source=true` de um job já terminado
  agenda a mesma expiração.
- `DELETE /jobs/{job_id}/source` apaga as imagens na hora (também depois que o purge já
  levou o original).
- Depois de apagadas, `GET /jobs/{id}/assets/{name}` responde `410 SOURCE_PURGED`
  (`cause: ASSETS_PURGED`); `GET /jobs/{id}` informa `assets_available` e `assets_expire_at`.

**Deduplicação:** `image_mode` e `page_images` entram no `operation_key` (só quando
diferentes do padrão, então as chaves antigas continuam valendo): uma conversão
`referenced` nunca devolve um job `none`, nem um job sem chave (anterior às chaves), nem
um job cujas imagens já foram apagadas ou expiram em menos da metade de
`ASSET_RETENTION_SECONDS` (aí um job novo é criado, em vez de devolver URLs prestes a
responder 410).

**Na interface:** `/convert` oferece "Extract images" (`image_mode=referenced`) e "Render
each page as an image" (`page_images=true`) para documentos, nas quatro abas (File, URL,
Google Drive, Dropbox), com o aviso de retenção quando "Don't keep the original file after
converting" está marcado. A visualização do Markdown busca cada `/jobs/{id}/assets/{name}`
na API com a credencial da sessão e mostra a imagem por um blob URL (liberado ao sair);
imagem apagada ou inexistente aparece como "Image unavailable". A página do job ganha a aba
"Images" (miniaturas carregadas do mesmo jeito, página/tipo/tamanho, download de cada PNG e
"Download all (.zip)", `assets_expire_at` ou o estado de apagadas). O botão "Delete original
files" apaga também as imagens; depois que o original já foi apagado ele aparece como
"Delete extracted images" enquanto houver imagens.

```bash
curl -X POST http://localhost:8000/upload \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "file=@apostila.pdf" -F "project=Cursos" \
  -F "image_mode=referenced" -F "page_images=true" -F "purge_source=true"
```

### Descrição e OCR das figuras (`describe_images`, `ocr_images`)

Dois campos de form em `/upload` e `/convert` (padrão `false`):

| Campo | Efeito |
|---|---|
| `describe_images` | Cada figura (`PictureItem` do Docling) recebe uma legenda do Florence-2 (`CONVERSION_FIGURE_CAPTION_TASK`, padrão `<MORE_DETAILED_CAPTION>`). **As legendas saem em inglês** (decisão de 2026-10-08: a pilha de visão atual). |
| `ocr_images` | O texto dentro de cada figura é lido com a tarefa `<OCR>` do Florence-2. |

Só figuras, nunca as páginas renderizadas (`page_images`). Qualquer um dos dois liga
`generate_picture_images` no Docling (com `CONVERSION_IMAGES_SCALE`) mesmo com
`image_mode=none`, mas só `image_mode=referenced` publica PNGs e referências.

**Markdown**, na posição de cada figura (ordem do documento):

```markdown
![Image](/jobs/<job_id>/assets/p0001-img01-3f2a9c1b7d4e.png)

> **Figure (description, English):** A bar chart comparing revenue across four quarters ...
> **Text in figure (OCR):** Revenue 2024 Q1 Q2 Q3 Q4
```

- `image_mode=referenced`: a linha `![Image](...)` fica e o blockquote vem logo depois;
  `image_mode=none`: o placeholder `<!-- image -->` é trocado pelo blockquote.
- Linha cujo texto saiu vazio é omitida; figura sem nenhum texto (pulada ou falhou) fica
  exatamente como sem as opções (`<!-- image -->` ou só a referência).
- O texto é normalizado: caracteres de controle removidos, `\r\n` → `\n`, cada quebra de
  linha continua o blockquote com `> `, `<!--`/`-->` neutralizados, tokens `</s>` do
  Florence removidos, corte em `CONVERSION_FIGURE_MAX_CHARS` (4000) por texto.
- `GET /jobs/{job_id}/result` ganha `figures_described`, `figures_ocr` e `figures_skipped`
  (contados por posição de figura; `null` num job sem as opções) e cada item de `assets`
  ganha `description` / `ocr_text` (`null` quando não pedido, para páginas renderizadas
  ou quando falhou). As contagens ficam também em `metadata.figures` (o Elasticsearch,
  que recebe o Markdown final, guarda só markdown + metadata) e em
  `jobs.assets_manifest.figures`.

**Pipeline** ([figure_tasks.py](../../backend/workers/figure_tasks.py),
[figure_descriptions.py](../../backend/shared/figure_descriptions.py)):

1. Na extração, cada figura vira uma entrada (`name`, `page`, `sha256`, objeto no MinIO,
   âncora). Com `referenced` a figura é o próprio asset e a âncora é a URL dele; com
   `none` o PNG vai para uma área temporária (`figures/{job_id}/{sha256}.png` no bucket
   de resultados, um objeto por imagem distinta) e o Markdown recebe
   `<!-- figure:{name} -->` no lugar do placeholder. Num PDF dividido o limite
   `CONVERSION_FIGURE_MAX_COUNT` vale para o documento inteiro já antes do upload
   (reserva no Redis `job:{id}:figures:slots`, como a dos assets; a mesma imagem em
   várias páginas ocupa uma vaga só).
2. As saídas públicas de uma página (Markdown do resultado, Elasticsearch,
   `pages.markdown_content`, `results/{job}/page_N.md`) **nunca** têm os marcadores: saem
   com `<!-- image -->`. O Markdown marcado e as entradas ficam em campos privados do
   resultado da página no Redis (`_figure_markdown`, `_figures`), que só o merge lê.
3. Depois da conversão (documento único) ou do merge (PDF dividido) começa a etapa de
   descrição: o resultado pendente vai para `figures/{job_id}/pending.json` e o job
   ganha `jobs.figures_stage = "describing"` e o heartbeat `jobs.figures_stage_at`
   (migração `d4b80025f6c2`). As imagens únicas (sha256, ordem do documento) são
   enviadas aos poucos: no máximo `CONVERSION_FIGURE_WINDOW` (2) por job na fila de
   visão; quando uma termina, a próxima vai. Cada uma é colocada **na hora do envio**
   pelo mesmo `dispatch.place_now(feature="vision")` das rotas `/images/*` (rota, vagas
   de engine e contabilidade valem igual; sem rota, fila de visão como hoje). Rota sem
   vaga agora → nova tentativa com backoff (10 s … 300 s), nunca "pulada" por isso.
4. **Prioridade:** `workers.vision_tasks.describe_figure_task` vai para a fila de visão
   com prioridade 9 (Redis: `priority_steps` 0–9, a menor sai primeiro); as tarefas
   interativas (`/images/*`) não têm prioridade (0). Com `--concurrency=1`, prefetch 1
   e `acks_late`, um pedido interativo espera no máximo a figura em execução.
5. A task que conclui o conjunto (Redis `job:{id}:figures:results`) enfileira
   `workers.tasks.finalize_figures_task`, que reescreve o Markdown, atualiza o
   manifesto, grava o resultado (Redis, Elasticsearch, MySQL `completed`, marcador
   `finishing`) e depois roda, cada passo por conta própria e idempotente, o status no
   Redis, a limpeza de `figures/{job_id}/`, o `purge_source` e o callback. Um passo que
   falha deixa o marcador em `finishing` e é refeito pelo próximo finalize / varredura —
   sem refazer a reescrita.

Nenhum worker de conversão espera pela visão (a etapa anda por mensagens). O job fica
`processing` com progresso de 90 a 99% (`stage: describing_figures`,
`figures_done`/`figures_total` no status do Redis), e por isso `has_pending_work` segura
o purge até o texto entrar.

**Falhas e limites:** figura menor que `CONVERSION_ASSET_MIN_PX`, além do limite, ilegível,
ou cuja task falhou (modelo ausente, `CONVERSION_FIGURE_TIMEOUT_SECONDS` = 120 por figura)
fica sem texto e conta em `figures_skipped`; nunca derruba o job. A task de visão de um
job que já saiu da etapa não roda inferência nem recria o estado.

- **Watchdog:** a etapa termina com o que tiver quando nenhuma figura andou por
  `CONVERSION_FIGURE_STALL_SECONDS` (900) **e** nada do job está em voo ou a fila de visão
  está vazia (task perdida) — figuras só esperando atrás de uma fila ocupada estendem a
  etapa (e o heartbeat) —, ou depois de `CONVERSION_FIGURE_MAX_STAGE_SECONDS` (6 h) no
  total. O motivo fica em `metadata.figures.reason` (`stalled`, `deadline`, `stuck`…).
  A corrente do watchdog é rearmada pela varredura do beat (`detect_stuck_jobs` →
  `figure_tasks.sweep`) a partir do marcador durável.
- **Monitor de jobs travados:** usa `figures_stage_at` em vez de `started_at`; um job
  na etapa que mesmo assim passar do limite é **completado** com o que houver, nunca
  `failed`. A configuração exige `MONITORING_STUCK_JOB_THRESHOLD_MINUTES` × 60 >
  `CONVERSION_FIGURE_STALL_SECONDS`.
- **Finalize que falha:** o job é completado com as figuras como placeholder (todas em
  `figures_skipped`, `reason` com `finalize_failed`). Só um `pending.json` ilegível faz o
  job falhar (`FIGURES_FAILED`). Um job marcado `failed` por outro caminho enquanto a
  etapa rodava é completado do mesmo jeito: a conversão deu certo.
- **PDF dividido `partial`:** não passa pela etapa; as saídas das páginas já saem sem
  marcadores. As PNGs temporárias ficam para um retry de página completar o job (com
  `purge_source=true` são apagadas quando ele assenta). `DELETE /jobs/{id}` apaga
  `figures/{job_id}/` em qualquer caso.

**Duráveis e deduplicação:** as duas opções ficam em `JobConfiguration.options` (só quando
`true`), relidas por páginas, retries e merge, e entram no `operation_key` só quando
`true` — chaves antigas continuam valendo, e um pedido com descrição/OCR nunca reaproveita
um job sem elas.

```bash
curl -X POST http://localhost:8000/upload \
  -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "file=@relatorio.pdf" -F "project=Relatórios" \
  -F "image_mode=referenced" -F "describe_images=true" -F "ocr_images=true"
```

**Na interface:** `/convert` reúne para documentos, num grupo "PDF options", o preset do
Docling, "Extract images", "Render each page as an image", "Describe figures" (com o
aviso de que as descrições são em inglês), "OCR text in figures" e "Don't keep the
original file after converting". A aba "Images" do job mostra as contagens e o texto de
cada figura.

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
  como `queued` (MySQL `pending`) com a mensagem de erro, e só fica `failed` na última.
  `convert_page_task` tem `max_retries=3` (a página espera o retry como `pending`);
  `split_pdf_task` e `merge_pages_task`, 2 (durante o retry do merge o job continua
  `processing`).
- Quando todas as páginas de um PDF dividido terminaram e alguma falhou de vez, o job
  MAIN passa a **`partial`** (antes ficava `processing` para sempre), com
  `error_message` "N de M páginas falharam…" e `completed_at`. As páginas convertidas
  ficam disponíveis; o retry de página reabre o job (`processing`) e, se todas
  completarem, o merge o leva a `completed`.
- Um conversor Docling é reaproveitado por processo e por combinação de opções (o
  carregamento dos modelos de layout/tabela é caro).
- Ao concluir, os arquivos locais do job são apagados (`_remove_job_files`); o original
  continua no MinIO (salvo `purge_source`). Sobras de jobs que falharam são varridas pela task diária
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
| `CONVERSION_IMAGES_SCALE` | `2.0` | `images_scale` do Docling quando as figuras são geradas (`image_mode=referenced`, presets `balanced`/`quality`). |
| `CONVERSION_PAGE_IMAGE_DPI` | `150` | DPI das páginas renderizadas (`page_images=true`). |
| `CONVERSION_ASSET_MIN_PX` | `32` | Figura menor que isso em largura ou altura é pulada (`too_small`). |
| `CONVERSION_ASSET_MAX_COUNT` | `500` | Máximo de assets (figuras + páginas) por job. |
| `CONVERSION_ASSET_MAX_TOTAL_MB` | `200` | Máximo de bytes PNG por job. |
| `ASSET_RETENTION_SECONDS` | `3600` | Com `purge_source=true`, quanto tempo as imagens ficam depois do fim do job. |
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
