# Busca por conteúdo (Elasticsearch)

> Verificado contra o código em 2026-10-04. Fonte da verdade:
> [backend/api/routes.py](../../backend/api/routes.py) (`GET /search`),
> [backend/shared/elasticsearch_client.py](../../backend/shared/elasticsearch_client.py).

## O que faz

Busca texto no Markdown resultante dos jobs do usuário. Para buscar pelo **nome** do job
ou do arquivo, use `GET /jobs?q=...` ([jobs-api.md](jobs-api.md#get-jobs)), que consulta o
MySQL.

## Como usar

`GET /search?query=<texto>&limit=<n>`

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `query` | obrigatório | Texto livre (consulta `match` no campo `markdown_content`). |
| `limit` | `10` | Máximo 100. |

```bash
curl -G -H "X-API-Key: $INGESTIFY_API_KEY" http://localhost:8000/search \
  --data-urlencode "query=relatório financeiro" -d limit=20
```

Resposta:

```json
{
  "query": "relatório financeiro",
  "total": 2,
  "limit": 20,
  "results": [
    {"job_id": "<uuid>", "filename": "q3.pdf", "total_pages": 12, "char_count": 48211,
     "created_at": "...", "preview": "primeiros 200 caracteres..."}
  ]
}
```

`total` é o número de itens devolvidos (não o total de acertos no índice). A página de
listagem de jobs do frontend usa este endpoint.

## O que acontece por dentro

- Índices criados no primeiro uso do cliente (`_create_indices`):
  - `job_results` — um documento por job MAIN concluído: `job_id`, `user_id`,
    `markdown_content`, `filename`, `total_pages`, `char_count`, `created_at`,
    `metadata` (não indexado). Escrito por `process_conversion` (documento único),
    `merge_pages_task` (PDF dividido) e pela transcrição.
  - `page_results` — um documento por página (`{job_id}_page_{n}`). Não há endpoint de
    busca sobre ele (`search_pages` existe no cliente, mas nenhuma rota o usa).
  - `crawler_jobs` — criado mas não usado por nenhuma rota (ver [crawler.md](crawler.md)).
- A consulta é `bool.must = [match(markdown_content), term(user_id)]`, ordenada por
  `created_at` desc (não por relevância).
- `DELETE /jobs/{id}` remove o documento de `job_results` e as páginas de `page_results`.

## Configuração

| Variável | Default | Efeito |
|---|---|---|
| `ELASTICSEARCH_URL` | `http://elasticsearch:9200` | |
| `ELASTICSEARCH_USER` / `ELASTICSEARCH_PASSWORD` | vazio | Sem autenticação quando vazios. |
| `ELASTICSEARCH_VERIFY_CERTS` | `false` | |

O Elasticsearch é opcional para o startup da API (só loga um aviso) e para o `/health`
(sem ele o status fica `degraded`).

## Limites e lacunas conhecidas

- Erros do Elasticsearch são engolidos pelo cliente: com o ES fora do ar, `/search`
  responde `200` com `results: []` em vez de um erro.
- Ordenação por data, não por relevância; sem destaque (highlight), paginação ou filtros
  por tag/tipo.
- Analisador padrão do ES (sem analisador para português).
- Jobs de imagem (visão) não são indexados.
