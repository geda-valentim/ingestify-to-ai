# Jobs: ciclo de vida e consulta

> Contratos dos endpoints revisados em 2026-10-06. Campos, modelos e autorização:
> [referência completa da API](../api-reference.md). As datas abaixo também registram revisões da implementação/operação.

> Verificado contra o código em 2026-10-06. Fonte da verdade:
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

### Imagens no `/convert`

O upload aceita PNG, JPEG, WEBP, BMP, GIF e TIFF. Ao selecionar uma imagem,
o formulário oferece descrição (`<CAPTION>`, `<DETAILED_CAPTION>` ou
`<MORE_DETAILED_CAPTION>`) ou OCR com regiões (`<OCR_WITH_REGION>` fixo).
`GET /images/capabilities` informa o limite de tamanho, as tarefas permitidas
e a tarefa padrão configurada. Projeto, pasta e tags acompanham o upload;
nome personalizado e destino datalake não são parâmetros dessas rotas.

A página do job exibe a imagem original com a descrição no nível escolhido,
ou o texto e as regiões detectadas pelo OCR. O worker mantém o status também
no MySQL e salva o resultado completo em `images/{job_id}/result.json` no
bucket de resultados, referenciado por `jobs.minio_result_path`. O resultado
JSON normal de `/jobs/{job_id}/result` inclui `markdown`, `metadata` e `image`,
com operação, tarefa, modelo, dimensões e imagem em base64. A leitura segue
disponível após expirar o cache; excluir o job remove esse objeto privado.

Se a espera síncrona retorna 504 com `job_id`, o frontend abre esse mesmo job
para acompanhar sua conclusão.

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
| `GET /jobs/{job_id}/pages/{n}/pdf/content` | PDF binário autenticado, `application/pdf`; não retorna JSON. |
| `POST /jobs/{job_id}/pages/{n}/retry` | Reprocessa uma página `failed` (máx. 3 vezes). |
| `PUT /jobs/{job_id}/tags` | Substitui as tags (ver [tags.md](tags.md)). |
| `DELETE /jobs/{job_id}` | Apaga o job. |
| `GET /jobs/{job_id}/transcript/partial` | Só para transcrições (fora do escopo deste doc). |
| `GET /jobs/{job_id}/datalake` | Status da entrega, valores congelados e caminhos reais dos artefatos/dataset. |
| `POST /jobs/{job_id}/datalake/retry` | Repete a entrega preservada sem repetir inferência. |
| `PATCH /jobs/{job_id}/location` | Move o MAIN para projeto/pasta próprios; veja [projects.md](projects.md). |
| `POST /jobs/move` | Move de 1 a 100 jobs atomicamente. |

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
| `project_id` | — | Filtra projeto próprio; ID alheio/inexistente retorna 404. |
| `folder_id` | — | Pasta própria ou `root` para jobs sem pasta; `root` exige `project_id`. |

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

`type` descreve a posição na hierarquia (MAIN/PAGE/etc.); `kind`, quando
disponível, identifica `document`, `transcription` ou `image`. São campos distintos.

Lê o status do **Redis**; se o cache expirou, usa a linha do próprio job no **MySQL**.
Jobs concluídos retornam progresso de 100% nesse fallback. Datas e nome vêm do MySQL
quando existem. A linha do pai de um job filho não substitui o status do filho.

Para jobs MAIN de PDF dividido, inclui `total_pages`, `pages_completed`, `pages_failed`,
`pages[]` (cada um com `page_number, job_id, status, url, error_message, retry_count`) e
`child_jobs` (`split_job_id`, `page_job_ids[]`, `merge_job_id`). Páginas ainda não criadas
pelo split aparecem como `queued` com `job_id: null`.

Paginação da lista de páginas: `?page_limit=50&page_offset=0` (sem `page_limit`, todas).

### `GET /jobs/{job_id}/result`

1. Status do Redis, com fallback para o próprio job no MySQL: `pending`/`queued`/
   `processing` ou `cancelled` → `400`; `failed` → `500` com o erro.
2. Transcrições: cache do Redis ou resultado completo no MinIO (`result.json`),
   com Markdown original, metadados e formato padrão. A leitura desses resultados
   e de VTT/SRT/TXT/JSON não exige Elasticsearch. Para jobs antigos que só têm
   `transcript.json`, o Markdown é reconstruído com idioma, duração e tamanho da
   origem; metadados ausentes, como device, não são recuperados.
3. Documentos e transcrições sem resultado no MinIO: Elasticsearch (`job_results`),
   depois Redis (`job:{id}:result`). Sem resultado, `404`.

Resposta: `{job_id, type, status: "completed", result: {markdown, metadata}, completed_at}`
e, para jobs PAGE, `page_number` e `parent_job_id`. O parâmetro `?format=` só tem efeito
em transcrições. Use `format=markdown` para solicitar explicitamente o envelope
JSON; sem formato vale o `output_format` escolhido no envio. VTT/SRT/TXT são
respostas de texto e `format=json` é o JSON bruto da transcrição, sem o envelope
`result`. Tipos de conteúdo constam na [referência](../api-reference.md).

```bash
curl -H "X-API-Key: $INGESTIFY_API_KEY" http://localhost:8000/jobs/$JOB_ID/result \
  | jq -r .result.markdown > saida.md
```

### Páginas

- `GET /jobs/{id}/pages` — do MySQL (`pages`); se não houver linhas, cai para o Redis.
  `404` se o job não tem páginas (documento não dividido).
- `GET /jobs/{id}/pages/{n}/status` e `.../result` — dispensam conhecer o `page_job_id`.
  O resultado vem do Elasticsearch (`page_results`); se o índice estiver indisponível
  ou sem o resultado, usa o Markdown persistido em `pages.markdown_content`.
  Linhas antigas sem texto persistido ainda podem usar o Redis como último recurso.
- `GET /jobs/{id}/pages/{n}/pdf` — devolve **JSON**, não redirect:
  `{job_id, page_number, url, preview_url, expires_in: 900, expires_at}`. A `url` é assinada para o
  host que o navegador usa (`MINIO_PUBLIC_ENDPOINT`, ou o host da requisição) e não aceita
  parâmetros extras na query string (invalidaria a assinatura → `403` no MinIO).
  `preview_url` aponta para a API e exige `Authorization`; o front usa essa URL
  para funcionar em HTTPS mesmo quando o MinIO só tem endereço de LAN.
- `GET /jobs/{id}/pages/{n}/pdf/content` — transmite o PDF da página com autenticação
  e verificação do dono do job. Disponível também enquanto a conversão está em andamento.
- `POST /jobs/{id}/pages/{n}/retry` — só para página `failed` e com `retry_count < 3`.
  Gera um novo `page_job_id`; se a cópia local do PDF já foi apagada, restaura o original
  de `ingestify-uploads` antes de reextrair a página. Resposta inclui `new_page_job_id`,
  `retry_count` e `retry_limit: 3`.

O PDF de uma página pode ser aberto enquanto a conversão está em andamento;
o Markdown fica disponível quando aquela página termina. O split salva todas
as linhas em `pages` antes de enviar tarefas e falha/reexecuta se a persistência
for rejeitada. Ao esgotar as tentativas do split, o MAIN é marcado como `failed`,
sem deixar a interface esperando indefinidamente. `pages.page_job_id` não tem FK para `jobs`: jobs PAGE vivem no
Redis, e a relação de propriedade permanece em `pages.job_id → jobs.id`.
Instalações antigas com essa FK devem executar a migração direcionada, sem
aplicar revisões Alembic não relacionadas:

```bash
docker compose exec api python scripts/migrate_page_jobs.py
# Recupera linhas ausentes de um job concluído usando os resultados preservados:
docker compose exec api python scripts/migrate_page_jobs.py --repair-job <job_id>
```

A recuperação valida os PDFs e resultados de todas as páginas antes de salvar,
preserva linhas existentes e pode ser executada novamente sem duplicá-las.

### `DELETE /jobs/{job_id}`

Remove, nesta ordem: o resultado e as páginas no Elasticsearch; para transcrições, os
objetos de áudio/legendas no MinIO; as linhas do MySQL (`jobs` filhos, `pages`, o MAIN —
`job_tags` cai por cascade); e as chaves do Redis (MAIN, SPLIT, PAGEs, MERGE e o índice
`user:{id}:jobs`). Responde `{message, job_id, deleted_at}`.

**Lacuna:** para documentos, os objetos no MinIO **não** são apagados — o original
(`ingestify-uploads/uploads/{job_id}/…`), os PDFs por página
(`ingestify-pages/pages/{job_id}/…`) e os Markdown por página
(`ingestify-results/results/{job_id}/…`) permanecem.

## Configuração

| Variável | Default | Efeito |
|---|---|---|
| `RESULT_TTL_SECONDS` | `3600` | TTL de `job:{id}:result` no Redis. |
| (fixo no código) | 24 h | TTL de `job:{id}:status`, `job:{id}:owner`, `job:{id}:pages:total`. |
| (fixo no código) | 15 min | Validade da URL de `/pages/{n}/pdf` (`PAGE_PDF_URL_TTL_SECONDS`). |
| (fixo no código) | 3 | Limite de retries manuais por página. |

## Limites e lacunas conhecidas

- Jobs filhos sem linha própria em `jobs` ainda dependem do status do Redis em
  `GET /jobs/{id}` e `GET /jobs/{id}/result`; use os endpoints por número de página
  quando o cache do filho expirar.
- Não há cancelamento de job.
- `GET /jobs/{id}/pages/{n}/status` devolve `job_id: "page-{n}"` quando a linha da página
  não tem `page_job_id` (esse valor não é um id endereçável).
