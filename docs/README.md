# Documentação do Ingestify

Índice de `docs/`. Os documentos em [features/](features/) foram verificados contra o código
em **2026-10-04** (perfis de execução e acesso: **2026-10-06**) e são a referência atual; o código continua sendo a fonte da verdade.
A especificação interativa da API fica em `http://<api>/docs` (Swagger) e `/redoc`.

Legenda: **atual** = confere com o código · **parcial** = útil, mas com trechos antigos
(sinalizados no próprio arquivo) · **histórico** = registro do passado, não use como
referência · **planejado** = não implementado.

## Uso da plataforma e planejamento comercial

A documentação pública distingue **Usar a plataforma**, **Integrar pela API** e **Administrar**. Os guias de uso mostram os passos nas telas e apontam para os contratos técnicos correspondentes; as URLs anteriores dos tópicos de API continuam disponíveis. Comece em [PT](https://dev.ingestify.ai/pt/docs/platform-start) ou [EN](https://dev.ingestify.ai/docs/platform-start).

| Documento | Estado | Conteúdo |
| --- | --- | --- |
| [Ingestify for Business](https://dev.ingestify.ai/business) | apresentação do produto | Capacidades disponíveis, casos de uso e links para começar pela interface ou API. |

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
| [features/execution-profiles.md](features/execution-profiles.md) | Biblioteca de perfis versionados, vinculação ao runtime existente e RBAC/ABAC por engine/recurso. Implementado com ativação opt-in; [validação](benchmarks/execution-profiles-validation.md). |
| [features/crawler.md](features/crawler.md) | **Planejado / não implementado**: o que existe de código dormente e onde está o plano. |
| Transcrição de áudio/vídeo (`POST /transcribe`) | Documentada à parte. Dispositivo e GPU do Whisper: [GPU.md](GPU.md) e spec 0002. |
| [features/whisperx.md](features/whisperx.md) | Canário WhisperX: perfis duráveis, falantes em arquivos, protocolo Modal 4, imagem isolada, gates e rollback. |
| [features/live-transcription.md](features/live-transcription.md) | Piloto opt-in de microfone: protocolo WebSocket, legendas provisórias/confirmadas, persistência, ativação e rollback. Desabilitado por padrão; [resultados e limites do piloto](benchmarks/live-transcribe-pilot.md). |

## Arquitetura

| Doc | Estado | Conteúdo |
|---|---|---|
| [../CLAUDE.md](../CLAUDE.md) | parcial | Visão geral do monorepo, padrões e chaves Redis. Desatualizado em dois pontos: cita `docker-compose.dev.yml` (não existe) e diz que `domain/`, `application/`, `infrastructure/` foram removidos (o crawler os recolocou, dormentes). |
| [ARCHITECTURE_JOBS.md](ARCHITECTURE_JOBS.md) | parcial | Hierarquia de jobs MAIN/SPLIT/PAGE/MERGE. Fórmula de progresso, estados e filas corrigidos em 2026-10-04. |

## Operação e deploy

| Doc | Estado | Conteúdo |
|---|---|---|
| [runbooks/execution-profiles-access.md](runbooks/execution-profiles-access.md) | atual | Migração 0009, ativação de acesso, qualificação de recursos, principal da CLI e rollback. |
| [GPU.md](GPU.md) | atual | CPU vs GPU, pré-requisitos NVIDIA, VRAM, pesos de modelos, troubleshooting. (inglês) |
| [SHARED_INFRASTRUCTURE.md](SHARED_INFRASTRUCTURE.md) | atual | Redis/MinIO/Elasticsearch compartilhados entre projetos (`scripts/dev/start.sh`, `docker-compose.infra.yml`). (inglês) |
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
| `docker-compose.engine-control.yml` | Overlay opt-in de controle de engines e RBAC/ABAC. Migração explícita antes de ativar; [runbook](runbooks/execution-profiles-access.md). |
| `docker-compose.prod.yml` | Produção (`make prod`): `ENVIRONMENT=production` em todos os serviços (o base usa `development`), `uvicorn --workers 4`, `worker` com `--concurrency=4`, frontend sem volumes de dev. |
| `docker-compose.infra.yml` | Só a infraestrutura compartilhada (`make infra-start`). Ver [SHARED_INFRASTRUCTURE.md](SHARED_INFRASTRUCTURE.md). |
| `docker-compose.override.yml` | Overlay **local, fora do git**, aplicado automaticamente pelo `docker compose` quando existe (ex.: remapear portas). Não é parte do produto. |

Atalhos: `make start` (detecta infraestrutura compartilhada), `make dev`, `make prod`,
`make gpu`, `make scale n=10`, `make test`. Lista completa: `make help`.

## Histórico e planejamento (não usar como referência)

| Doc | Estado | Observação |
|---|---|---|
| [TEST_RESULTS.md](TEST_RESULTS.md) | histórico | Snapshot de testes de 2025-10-01. |
| [CHANGELOG.md](CHANGELOG.md) | histórico | Changelog de out/2025; para o resto, `git log`. |

Fora de `docs/`: [../backend/docs/TEST_RESULTS.md](../backend/docs/TEST_RESULTS.md) (histórico:
resultados de testes das camadas Clean Architecture) e [../frontend/docs/doc2md_openapi.json](../frontend/docs/doc2md_openapi.json)
(snapshot do OpenAPI; falta `GET /jobs/{job_id}/transcript/partial` — regenere a partir de
`/openapi.json`).

## Onde escrever

Regras do [CLAUDE.md](../CLAUDE.md): docs gerais em `docs/`, específicos de backend em
`backend/docs/`, de frontend em `frontend/docs/`. Decisões novas viram uma spec privada
(`docs/specs/`, ignorada pelo git; versionada no repositório privado de docs). Ao documentar uma funcionalidade, verifique no código e registre a data
da verificação no topo do arquivo, como em `features/`.

### Guias públicos de engines e perfis

[/docs/compute](https://dev.ingestify.ai/pt/docs/compute) organiza
[engines](https://dev.ingestify.ai/pt/docs/engines),
[operações](https://dev.ingestify.ai/pt/docs/engine-operations),
[perfis](https://dev.ingestify.ai/pt/docs/execution-profiles) e
[acesso RBAC/ABAC](https://dev.ingestify.ai/pt/docs/engine-access).
Cada guia inclui requisitos funcionais, pré-condições, recursos, configuração, aplicações, API e erros.
