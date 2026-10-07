# Crawler / web scraping — **planejado, não implementado**

> Verificado contra o código em 2026-10-04.

## Resumo

**Não existe crawler utilizável no Ingestify hoje.** Não há endpoint, task Celery, fila,
agendamento nem tela no frontend para rastrear sites. Para converter **uma** página ou
arquivo de uma URL, use `POST /convert` com `source_type=url` ([sources.md](sources.md)).

O que existe é código e esquema **dormentes**, trazidos pelo merge
`f1b5917` ("feat(crawler): integrate feature/crawler-integration into main (#8)"):

| Peça | Onde | Ligada ao sistema? |
|---|---|---|
| Entidades, value objects, serviços (normalização de URL, detecção de duplicatas) | `backend/domain/` | Não — só os testes em `backend/tests/domain/` importam. |
| DTOs, ports, use cases (create/get/update/delete crawler job) | `backend/application/` | Não. |
| Adapters BeautifulSoup e Playwright, proxy manager, merge de PDF, storage MinIO, índice ES, repositórios MySQL | `backend/infrastructure/` | Não. |
| Colunas `jobs.crawler_config` / `jobs.crawler_schedule` e tabela `crawled_files` | [backend/shared/models.py](../../backend/shared/models.py), `backend/migrations/002_*.sql`, `003_*.sql`; `init_db()` adiciona as colunas | Esquema criado, nada escreve nele. |
| `JobType.CRAWLER` | [backend/shared/schemas.py](../../backend/shared/schemas.py) | Nenhum código cria jobs desse tipo. |
| Bucket `ingestify-crawled` | criado por [minio_client.py](../../backend/shared/minio_client.py) no startup | Sempre vazio. |
| Índice `crawler_jobs` | criado por [elasticsearch_client.py](../../backend/shared/elasticsearch_client.py) | Nenhuma rota usa. |
| Variáveis `CRAWLER_*`, `PLAYWRIGHT_*`, `PROXY_*` | [backend/shared/config.py](../../backend/shared/config.py) | Lidas só pelo adapter dormente. |
| Dependências `playwright`, `python-socks`, `croniter`, `pytz` | `backend/requirements-base.txt` | Instaladas, sem uso em runtime. |

Observações:

- `backend/api/main.py` registra apenas os routers de auth, api-keys, admin, images, tags e
  conversão; o `/crawlers` previsto na sprint 5 (`presentation/controllers/crawler_controller.py`)
  não existe.
- Os Dockerfiles copiam só `api/`, `shared/`, `workers/` e `tests/`: as camadas
  `domain/`, `application/` e `infrastructure/` **nem chegam às imagens**.
- A spec 0001 removeu essas camadas em
  2026-08-26 (`9a6310d`); o merge do crawler, feito num ramo paralelo, recolocou nelas
  apenas os arquivos do crawler. O `CLAUDE.md` ainda descreve as camadas como removidas.

## Onde está o planejamento

O PRD, o plano de integração e os checklists de sprint são documentos de planejamento
privados, mantidos fora do repositório público.

Arquivos citados por sprint que existem hoje (levantamento de 2026-10-04): sprint 1, 8 de
10; sprint 2, 13 de 24; sprint 3, 3 de 26; sprint 4, 2 de 15; sprint 5, 0 de 13;
sprint 6, 0 de 3.

## Configuração declarada (sem efeito hoje)

`CRAWLER_ENABLED` (`true`), `CRAWLER_MAX_CONCURRENT_DOWNLOADS` (`5`),
`CRAWLER_MAX_CONCURRENT_ASSETS` (`10`), `CRAWLER_DOWNLOAD_TIMEOUT_SECONDS` (`60`),
`CRAWLER_USER_AGENT`, `CRAWLER_RESPECT_ROBOTS_TXT` (`true`, mas nada aplica robots.txt),
`CRAWLER_RATE_LIMIT_PER_SECOND` (`2`), `CRAWLER_DEFAULT_ENGINE` (`beautifulsoup`),
`PLAYWRIGHT_HEADLESS`, `PLAYWRIGHT_TIMEOUT_SECONDS` (`30`), `PLAYWRIGHT_WAIT_FOR_SELECTOR`,
`PLAYWRIGHT_BROWSER_TYPE` (`chromium`), `PROXY_ENABLED`, `PROXY_POOL_ENABLED`,
`PROXY_ROTATION_STRATEGY`, `CRAWLER_RETRY_ENABLED`, `CRAWLER_MAX_RETRIES` (`3`),
`CRAWLER_RETRY_DELAY_BASE_SECONDS` (`5`), `CRAWLER_RETRY_STRATEGY_DEFAULT`
(`conservative`), `MINIO_BUCKET_CRAWLED` (`ingestify-crawled`).

## Para levar adiante

Decidir (numa spec nova) se o crawler continua; se sim, onde ele
vive dado que a arquitetura em camadas foi abandonada pela spec 0001, e o que falta: router,
tasks/fila/agendamento, robots.txt, UI. Se não, remover o código dormente, as colunas e o
bucket.
