# Tags de jobs

> Contratos dos endpoints revisados em 2026-10-06. Campos, modelos e autorização:
> [referência completa da API](../api-reference.md). As datas abaixo também registram revisões da implementação/operação.

> Verificado contra o código em 2026-10-04. Fonte da verdade:
> [backend/api/tag_routes.py](../../backend/api/tag_routes.py),
> [backend/shared/tags.py](../../backend/shared/tags.py),
> [backend/shared/models.py](../../backend/shared/models.py) (`JobTag`).
> Introduzido no commit `74fda74`.

## O que faz

Rótulos livres por job MAIN, para organizar e filtrar. Valem para qualquer tipo de job
(documento, transcrição, imagem).

## Como usar

### Na criação

Todos os endpoints que criam job aceitam tags:

- `POST /upload`, `POST /convert`, `POST /transcribe`, `POST /images/describe/upload`,
  `POST /images/ocr/upload`: campo de formulário `tags` com valores separados por vírgula.
- `POST /images/describe`, `POST /images/ocr` (JSON): campo `tags` como lista.
- `POST /transcribe/live/sessions` e `POST /datalakes/import` (JSON): `tags` como lista.

Se o upload for duplicado (mesmo checksum, ver [conversion.md](conversion.md#deduplicação-por-checksum)),
as tags enviadas são **somadas** às do job existente.

### Endpoints

| Método e caminho | Descrição |
|---|---|
| `GET /tags` | Tags do usuário com contagem de jobs: `{tags: [{tag, count}]}`, da mais usada para a menos usada (empate em ordem alfabética). |
| `PUT /jobs/{job_id}/tags` | JSON `{tags: [...]}` **substitui** todas as tags (`[]` remove todas). Devolve `{job_id, tags}`. |
| `GET /jobs?tag=a&tag=b` | Filtra a listagem; várias tags são combinadas com E. Ver [jobs-api.md](jobs-api.md#get-jobs). |

```bash
curl -X POST http://localhost:8000/upload -H "X-API-Key: $INGESTIFY_API_KEY" \
  -F "file=@nota.pdf" -F "project=Financeiro" -F "tags=Cliente-X, #financeiro"

curl -X PUT http://localhost:8000/jobs/$JOB_ID/tags -H "X-API-Key: $INGESTIFY_API_KEY" \
  -H "Content-Type: application/json" -d '{"tags":["cliente-x","2026"]}'

curl -H "X-API-Key: $INGESTIFY_API_KEY" http://localhost:8000/tags
```

O frontend usa estes endpoints na listagem de jobs e na página de detalhe.

## Regras de normalização

`parse_tags` / `normalize_tag`:

- remove espaços nas pontas e `#` inicial, colapsa espaços internos, converte para
  minúsculas (`"Cliente X"` e `"cliente x"` são a mesma tag);
- descarta vazias e repetidas, mantendo a ordem;
- máximo **50 caracteres** por tag e **20 tags** por job; acima disso, `422`.

## O que acontece por dentro

Tabela `job_tags` (`job_id`, `tag`) com chave primária composta e `ON DELETE CASCADE`
para `jobs`. Apagar um job apaga suas tags.

## Limites e lacunas conhecidas

- Só jobs com linha própria em `jobs` (MAIN) podem receber tags; `PUT` num job filho
  (página) devolve `404`.
- Não há renomear/apagar uma tag globalmente; é preciso editar job a job.
- Tags não são indexadas no Elasticsearch: `/search` não filtra por tag.
