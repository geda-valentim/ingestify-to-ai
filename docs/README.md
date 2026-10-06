# Documentação do Ingestify

Índice de `docs/`. Os documentos em [features/](features/) foram verificados contra o código
em **2026-10-04** e são a referência atual; o código continua sendo a fonte da verdade.
A especificação interativa da API fica em `http://<api>/docs` (Swagger) e `/redoc`.

Legenda: **atual** = confere com o código · **parcial** = útil, mas com trechos antigos
(sinalizados no próprio arquivo) · **histórico** = registro do passado, não use como
referência · **planejado** = não implementado.

## Funcionalidades

| Doc | Conteúdo |
|---|---|
| [features/conversion.md](features/conversion.md) | Conversão Docling: `/upload`, `/convert`, presets, split → páginas → merge, GPU. |
| [features/jobs-api.md](features/jobs-api.md) | Ciclo de vida e consulta de jobs: `/jobs`, status, resultado, páginas, PDF por página, retry, exclusão. |
| [features/sources.md](features/sources.md) | Fontes: arquivo, URL (proteção SSRF), Google Drive e Dropbox (token do provedor em `X-Source-Token`). |
| [features/auth-and-api-keys.md](features/auth-and-api-keys.md) | JWT, refresh, API keys, rate limit de login/registro, autorização por dono, admins. |
| [features/tags.md](features/tags.md) | Tags de jobs: criação, `GET /tags`, `PUT /jobs/{id}/tags`, filtro. |
| [features/search.md](features/search.md) | Busca no conteúdo via Elasticsearch (`GET /search`). |
| [features/vision.md](features/vision.md) | Florence-2: `/images/describe`, `/images/ocr`, `/images/capabilities`. |
| [features/storage-and-retention.md](features/storage-and-retention.md) | MySQL, Elasticsearch, MinIO, chaves Redis, disco temporário, tarefas agendadas e retenção. |
| [features/monitoring-and-admin.md](features/monitoring-and-admin.md) | `/health`, rotas `/admin/*`, detecção de jobs travados e retry automático. |
| [features/engines.md](features/engines.md) | **Guia Compute do operador**: execução CPU/GPU, provider × motor, telas admin, diagnóstico, chaves, capacidade/VRAM, deploy Modal, rotas, orçamentos, benchmark e legendas parciais de arquivos. |
| [features/crawler.md](features/crawler.md) | **Planejado / não implementado**: o que existe de código dormente e onde está o plano. |
| Transcrição de áudio/vídeo (`POST /transcribe`) | Documentada à parte. Dispositivo e GPU do Whisper: [GPU.md](GPU.md) e [spec 0002](specs/0002-dispositivo-unico-e-migracao-do-whisper.md). |
| [features/whisperx.md](features/whisperx.md) | Canário WhisperX: perfis duráveis, falantes em arquivos, protocolo Modal 4, imagem isolada, gates e rollback. |
| [features/live-transcription.md](features/live-transcription.md) | Piloto opt-in de microfone: protocolo WebSocket, legendas provisórias/confirmadas, persistência, ativação e rollback. Desabilitado por padrão; [resultados e limites do piloto](benchmarks/live-transcribe-pilot.md). |

## Arquitetura

| Doc | Estado | Conteúdo |
|---|---|---|
| [../CLAUDE.md](../CLAUDE.md) | parcial | Visão geral do monorepo, padrões e chaves Redis. Desatualizado em dois pontos: cita `docker-compose.dev.yml` (não existe) e diz que `domain/`, `application/`, `infrastructure/` foram removidos (o crawler os recolocou, dormentes). |
| [ARCHITECTURE_JOBS.md](ARCHITECTURE_JOBS.md) | parcial | Hierarquia de jobs MAIN/SPLIT/PAGE/MERGE. Fórmula de progresso, estados e filas corrigidos em 2026-10-04. |
| [specs/0001-remover-clean-architecture-morta.md](specs/0001-remover-clean-architecture-morta.md) | atual (com ressalva) | Decisão de remover as camadas Clean Architecture. Ressalva: o merge `f1b5917` recolocou arquivos do crawler nessas pastas. |
| [specs/0002-dispositivo-unico-e-migracao-do-whisper.md](specs/0002-dispositivo-unico-e-migracao-do-whisper.md) | atual | `DEVICE` único para Docling, Whisper e Florence-2. |
| [specs/0003-motores-de-execucao-roteamento-e-orcamento.md](specs/0003-motores-de-execucao-roteamento-e-orcamento.md) | em implementação | Motores de execução, rotas por feature com orçamento (local + Modal). Fatias 0a–8 feitas, 4d pendente; operação em [features/engines.md](features/engines.md). |

## Operação e deploy

| Doc | Estado | Conteúdo |
|---|---|---|
| [GPU.md](GPU.md) | atual | CPU vs GPU, pré-requisitos NVIDIA, VRAM, pesos de modelos, troubleshooting. (inglês) |
| [SHARED_INFRASTRUCTURE.md](SHARED_INFRASTRUCTURE.md) | atual | Redis/MinIO/Elasticsearch compartilhados entre projetos (`start.sh`, `docker-compose.infra.yml`). (inglês) |
| [DOCKER_OPTIMIZATION.md](DOCKER_OPTIMIZATION.md) | parcial | Otimização de build. As menções a `docker-compose.dev.yml` são históricas. |
| [PYTHON_313_COMPATIBILITY.md](PYTHON_313_COMPATIBILITY.md) | parcial | Compatibilidade com Python 3.13 (já adotado nas imagens). (inglês) |
| [CHANGELOG_PYTHON313.md](CHANGELOG_PYTHON313.md) | histórico | Registro da migração para Python 3.13. (inglês) |
| [EXECUTE.md](EXECUTE.md) | histórico | Guia de execução da época "Doc2MD". Use o [README da raiz](../README.md) e a tabela abaixo. |

### Perfis de deploy (docker compose)

| Arquivo | Para quê |
|---|---|
| `docker-compose.yml` | Base: `api` (:8000), `worker` (5 réplicas, fila `ingestify`), `worker-audio` (fila `ingestify-audio`), `worker-vision` (fila `ingestify-vision`), `beat`, `frontend` (:3000). Redis, Elasticsearch e MinIO ficam no profile `infra` e publicam só em `127.0.0.1`. MySQL **não** está no compose (padrão: `host.docker.internal`). |
| `docker-compose.gpu.yml` | Overlay opt-in de GPU (`make gpu`): `worker` vira 1 processo em CUDA, `worker-audio` com `AUDIO_WORKER_REPLICAS` (padrão 2) em CUDA, `worker-vision` em CUDA. Ver [GPU.md](GPU.md). |
| `docker-compose.live.yml` | Overlay opt-in de live com worker GPU privado e profile `live`. Exige migração explícita e validação antes de ativar em produção; ver [guia live](features/live-transcription.md). |
| `docker-compose.prod.yml` | Produção (`make prod`): `ENVIRONMENT=production` em todos os serviços (o base usa `development`), `uvicorn --workers 4`, `worker` com `--concurrency=4`, frontend sem volumes de dev. |
| `docker-compose.infra.yml` | Só a infraestrutura compartilhada (`make infra-start`). Ver [SHARED_INFRASTRUCTURE.md](SHARED_INFRASTRUCTURE.md). |
| `docker-compose.override.yml` | Overlay **local, fora do git**, aplicado automaticamente pelo `docker compose` quando existe (ex.: remapear portas). Não é parte do produto. |

Atalhos: `make start` (detecta infraestrutura compartilhada), `make dev`, `make prod`,
`make gpu`, `make scale n=10`, `make test`. Lista completa: `make help`.

## Revisões e specs

| Doc | Estado | Conteúdo |
|---|---|---|
| [SECURITY_REVIEW.md](SECURITY_REVIEW.md) | atual | Revisão de segurança de 2026-10-03 (âncoras de linha corrigidas em 2026-10-04). |
| [CODE_REVIEW.md](CODE_REVIEW.md) | histórico | Revisão de 2026-08-24; vários achados já corrigidos (anotados no texto). |
| [specs/README.md](specs/README.md) | atual | Convenção de specs (uma decisão por arquivo). Modelo: [specs/_TEMPLATE.md](specs/_TEMPLATE.md). |

## Histórico e planejamento (não usar como referência)

| Doc | Estado | Observação |
|---|---|---|
| [SPECS.md](SPECS.md) | histórico | Especificação original "Doc2MD" (out/2025). |
| [RF.md](RF.md) | histórico | Requisitos funcionais originais; várias marcações não batem com o código. |
| [RNF.md](RNF.md) | histórico | Requisitos não funcionais originais. |
| [STATUS.md](STATUS.md) | histórico | Status de out/2025. |
| [TASKS.md](TASKS.md) | histórico | Plano de implementação original (nenhuma caixa marcada). |
| [TEST_RESULTS.md](TEST_RESULTS.md) | histórico | Snapshot de testes de 2025-10-01. |
| [CHANGELOG.md](CHANGELOG.md) | histórico | Changelog de out/2025; para o resto, `git log`. |
| [WEBSCRAPPING_PRD.md](WEBSCRAPPING_PRD.md) | planejado | PRD do scraper; idêntico a `crawler/CRAWLER.md`. |
| [crawler/CRAWLER.md](crawler/CRAWLER.md) | planejado | PRD do crawler. |
| [crawler/CRAWLER_INTEGRATION_PLAN.md](crawler/CRAWLER_INTEGRATION_PLAN.md) | planejado | Plano de integração em camadas. |
| [crawler/sprint-1-foundation.md](crawler/sprint-1-foundation.md) … [sprint-6-testing.md](crawler/sprint-6-testing.md) | planejado | Checklists de sprint; só 1–2 parcialmente feitas. |

Fora de `docs/`: [../backend/docs/TEST_RESULTS.md](../backend/docs/TEST_RESULTS.md) (histórico:
resultados de testes das camadas Clean Architecture) e [../frontend/docs/doc2md_openapi.json](../frontend/docs/doc2md_openapi.json)
(snapshot do OpenAPI; falta `GET /jobs/{job_id}/transcript/partial` — regenere a partir de
`/openapi.json`).

## Onde escrever

Regras do [CLAUDE.md](../CLAUDE.md): docs gerais em `docs/`, específicos de backend em
`backend/docs/`, de frontend em `frontend/docs/`. Decisões novas viram uma spec em
[specs/](specs/). Ao documentar uma funcionalidade, verifique no código e registre a data
da verificação no topo do arquivo, como em `features/`.
