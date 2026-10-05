# Tarefas de Implementação - Doc2MD API

> **Documento histórico (out/2025) — obsoleto.** Plano de implementação original; nenhuma caixa foi marcada, embora boa parte esteja implementada (com caminhos diferentes — ex.: o rate limit está em `backend/shared/rate_limit.py`, não em `api/middleware.py`). Estado atual: [README.md](README.md) e [features/](features/).

Este documento organiza todas as tarefas necessárias para implementar o sistema Doc2MD em fases incrementais.

## 📋 Índice

- [Fase 0: Setup Inicial](#fase-0-setup-inicial)
- [Fase 1: Core API](#fase-1-core-api)
- [Fase 2: Workers e Conversão](#fase-2-workers-e-conversão)
- [Fase 3: Source Handlers](#fase-3-source-handlers)
- [Fase 4: Containerização](#fase-4-containerização)
- [Fase 5: Features Avançadas](#fase-5-features-avançadas)
- [Fase 6: Testes e QA](#fase-6-testes-e-qa)

---

## Fase 0: Setup Inicial

### TASK-001: Estrutura de Diretórios
**Prioridade:** Alta
**Estimativa:** 15 min
**Dependências:** Nenhuma

**Descrição:** Criar estrutura base de diretórios do projeto

**Checklist:**
- [ ] Criar diretório `api/`
- [ ] Criar diretório `workers/`
- [ ] Criar diretório `shared/`
- [ ] Criar diretório `docker/`
- [ ] Criar diretório `tests/`
- [ ] Criar diretório `scripts/`
- [ ] Criar diretório `tmp/` (gitignored)

**Resultado Esperado:**
```
doc2md/
├── api/
├── workers/
├── shared/
├── docker/
├── tests/
├── scripts/
└── tmp/
```

---

### TASK-002: Requirements.txt
**Prioridade:** Alta
**Estimativa:** 30 min
**Dependências:** TASK-001

**Descrição:** Criar arquivo de dependências Python

**Checklist:**
- [ ] Adicionar FastAPI e Uvicorn
- [ ] Adicionar Celery e Redis client
- [ ] Adicionar Docling
- [ ] Adicionar Pydantic
- [ ] Adicionar httpx (async HTTP)
- [ ] Adicionar google-api-python-client
- [ ] Adicionar dropbox SDK
- [ ] Adicionar python-multipart (para upload)
- [ ] Adicionar structlog (logging)
- [ ] Adicionar pytest e pytest-asyncio

**Dependências:**
```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
celery==5.3.4
redis==5.0.1
docling==1.0.0
pydantic==2.5.0
pydantic-settings==2.1.0
httpx==0.25.2
google-api-python-client==2.108.0
google-auth==2.25.2
dropbox==11.36.2
python-multipart==0.0.6
structlog==23.2.0
pytest==7.4.3
pytest-asyncio==0.21.1
```

---

### TASK-003: Arquivos de Configuração Base
**Prioridade:** Alta
**Estimativa:** 30 min
**Dependências:** TASK-001

**Descrição:** Criar arquivos de configuração do projeto

**Checklist:**
- [ ] Criar `.gitignore`
- [ ] Criar `.env.example`
- [ ] Criar `pyproject.toml` (para black, ruff, mypy)
- [ ] Criar `pytest.ini`

---

### TASK-004: Módulo de Configuração Compartilhada
**Prioridade:** Alta
**Estimativa:** 45 min
**Dependências:** TASK-002

**Descrição:** Implementar `shared/config.py` com Pydantic Settings

**Checklist:**
- [ ] Criar classe `Settings` com BaseSettings
- [ ] Adicionar configurações de API (host, port, workers)
- [ ] Adicionar configurações de Redis
- [ ] Adicionar configurações de Celery
- [ ] Adicionar configurações de conversão (max size, timeout)
- [ ] Adicionar configurações de storage (TTL, cleanup)
- [ ] Implementar singleton `get_settings()`

**Arquivo:** `shared/config.py`

---

## Fase 1: Core API

### TASK-101: Schemas Pydantic
**Prioridade:** Alta
**Estimativa:** 1h
**Dependências:** TASK-004

**Descrição:** Implementar schemas de request/response em `shared/schemas.py`

**Checklist:**
- [ ] `ConversionOptions` - opções de conversão
- [ ] `ConvertRequest` - request de conversão
- [ ] `JobCreatedResponse` - resposta de job criado
- [ ] `JobStatusResponse` - resposta de status
- [ ] `DocumentMetadata` - metadata de documento
- [ ] `ConversionResult` - resultado da conversão
- [ ] `JobResultResponse` - resposta com resultado
- [ ] `HealthCheckResponse` - resposta de health check
- [ ] `ErrorResponse` - resposta de erro
- [ ] Adicionar validators onde necessário

**Arquivo:** `shared/schemas.py`

---

### TASK-102: Aplicação FastAPI Base
**Prioridade:** Alta
**Estimativa:** 1h
**Dependências:** TASK-004, TASK-101

**Descrição:** Criar aplicação FastAPI em `api/main.py`

**Checklist:**
- [ ] Criar app FastAPI com metadata
- [ ] Configurar CORS
- [ ] Configurar middleware de logging
- [ ] Configurar exception handlers
- [ ] Configurar startup/shutdown events
- [ ] Adicionar route para docs customizado

**Arquivo:** `api/main.py`

---

### TASK-103: Redis Client
**Prioridade:** Alta
**Estimativa:** 45 min
**Dependências:** TASK-004

**Descrição:** Implementar cliente Redis em `shared/redis_client.py`

**Checklist:**
- [ ] Criar classe `RedisClient` com connection pool
- [ ] Implementar métodos de job status (get, set, update)
- [ ] Implementar métodos de result (get, set, delete)
- [ ] Implementar TTL management
- [ ] Implementar health check (ping)
- [ ] Implementar close/cleanup

**Arquivo:** `shared/redis_client.py`

---

### TASK-104: Endpoint POST /convert
**Prioridade:** Alta
**Estimativa:** 2h
**Dependências:** TASK-102, TASK-103, TASK-101

**Descrição:** Implementar endpoint de conversão em `api/routes.py`

**Checklist:**
- [ ] Criar router para /convert
- [ ] Implementar validação de input
- [ ] Implementar geração de UUID para job_id
- [ ] Implementar lógica de enfileiramento (stub para Celery)
- [ ] Implementar storage de job status no Redis
- [ ] Implementar tratamento de erros
- [ ] Suportar multipart/form-data (file upload)
- [ ] Suportar application/json (url, gdrive, dropbox)
- [ ] Adicionar validação de tamanho de arquivo

**Arquivo:** `api/routes.py`

---

### TASK-105: Endpoint GET /jobs/{job_id}
**Prioridade:** Alta
**Estimativa:** 45 min
**Dependências:** TASK-104

**Descrição:** Implementar endpoint de consulta de status

**Checklist:**
- [ ] Criar endpoint GET /jobs/{job_id}
- [ ] Buscar status do Redis
- [ ] Retornar 404 se job não existe
- [ ] Retornar JobStatusResponse
- [ ] Adicionar cache de 5 segundos

**Arquivo:** `api/routes.py`

---

### TASK-106: Endpoint GET /jobs/{job_id}/result
**Prioridade:** Alta
**Estimativa:** 45 min
**Dependências:** TASK-105

**Descrição:** Implementar endpoint de recuperação de resultado

**Checklist:**
- [ ] Criar endpoint GET /jobs/{job_id}/result
- [ ] Buscar resultado do Redis
- [ ] Retornar 404 se resultado não existe ou expirou
- [ ] Retornar 400 se job ainda em processamento
- [ ] Retornar 500 se job falhou
- [ ] Retornar JobResultResponse com markdown

**Arquivo:** `api/routes.py`

---

### TASK-107: Endpoint GET /health
**Prioridade:** Alta
**Estimativa:** 30 min
**Dependências:** TASK-103

**Descrição:** Implementar health check

**Checklist:**
- [ ] Criar endpoint GET /health
- [ ] Verificar conexão com Redis (ping)
- [ ] Verificar workers ativos (Celery inspect)
- [ ] Retornar status healthy/degraded/unhealthy
- [ ] Retornar 200 ou 503 baseado no status

**Arquivo:** `api/routes.py`

---

### TASK-108: Exception Handlers
**Prioridade:** Média
**Estimativa:** 1h
**Dependências:** TASK-102

**Descrição:** Implementar tratamento global de exceções

**Checklist:**
- [ ] Handler para ValidationError (422)
- [ ] Handler para HTTPException
- [ ] Handler para exceções genéricas (500)
- [ ] Retornar ErrorResponse estruturado
- [ ] Logar exceções com contexto
- [ ] Não expor stack traces em produção

**Arquivo:** `api/main.py`

---

### TASK-109: Rate Limiting
**Prioridade:** Média
**Estimativa:** 1.5h
**Dependências:** TASK-103, TASK-104

**Descrição:** Implementar rate limiting em `api/middleware.py`

**Checklist:**
- [ ] Criar middleware de rate limiting
- [ ] Implementar contador no Redis (por IP)
- [ ] Implementar janela deslizante (1 minuto)
- [ ] Retornar 429 quando exceder limite
- [ ] Adicionar headers X-RateLimit-*
- [ ] Configurar limite via environment

**Arquivo:** `api/middleware.py`

---

## Fase 2: Workers e Conversão

### TASK-201: Celery App Configuration
**Prioridade:** Alta
**Estimativa:** 1h
**Dependências:** TASK-004

**Descrição:** Configurar Celery em `workers/celery_app.py`

**Checklist:**
- [ ] Criar instância Celery com config
- [ ] Configurar broker (Redis)
- [ ] Configurar result backend (Redis)
- [ ] Configurar task serializer (json)
- [ ] Configurar acks_late=True
- [ ] Configurar task timeout (5 min)
- [ ] Configurar max retries (3)
- [ ] Configurar prefetch_multiplier=1

**Arquivo:** `workers/celery_app.py`

---

### TASK-202: Integração Docling Base
**Prioridade:** Alta
**Estimativa:** 2h
**Dependências:** TASK-201

**Descrição:** Implementar wrapper do Docling em `workers/converter.py`

**Checklist:**
- [ ] Criar classe `DoclingConverter`
- [ ] Inicializar DocumentConverter com config
- [ ] Implementar método `convert_to_markdown(file_path, options)`
- [ ] Implementar detecção de formato
- [ ] Implementar extração de metadata
- [ ] Implementar tratamento de erros
- [ ] Adicionar suporte a opções (include_images, preserve_tables)
- [ ] Implementar logging de progresso

**Arquivo:** `workers/converter.py`

---

### TASK-203: Task de Conversão Principal
**Prioridade:** Alta
**Estimativa:** 2h
**Dependências:** TASK-201, TASK-202

**Descrição:** Implementar task Celery em `workers/tasks.py`

**Checklist:**
- [ ] Criar task `process_conversion`
- [ ] Implementar download de arquivo (stub)
- [ ] Implementar chamada ao converter
- [ ] Implementar atualização de status
- [ ] Implementar storage de resultado no Redis
- [ ] Implementar cleanup de arquivos temporários
- [ ] Implementar retry logic
- [ ] Implementar error handling
- [ ] Adicionar logging estruturado

**Arquivo:** `workers/tasks.py`

---

### TASK-204: Integração API → Celery
**Prioridade:** Alta
**Estimativa:** 1h
**Dependências:** TASK-104, TASK-203

**Descrição:** Conectar API ao Celery para enfileirar jobs

**Checklist:**
- [ ] Importar Celery app na API
- [ ] Chamar `process_conversion.delay()` no endpoint /convert
- [ ] Passar job_id, source_type, source, options
- [ ] Testar enfileiramento end-to-end
- [ ] Testar recuperação de resultado

**Arquivo:** `api/routes.py`

---

### TASK-205: Gestão de Arquivos Temporários
**Prioridade:** Alta
**Estimativa:** 1h
**Dependências:** TASK-203

**Descrição:** Implementar gerenciamento de arquivos temp em `shared/file_manager.py`

**Checklist:**
- [ ] Criar função `create_temp_dir(job_id)`
- [ ] Criar função `save_upload_file(upload_file, temp_dir)`
- [ ] Criar função `cleanup_temp_dir(job_id)`
- [ ] Criar função `get_temp_path(job_id)`
- [ ] Implementar tratamento de erros (disk full, etc)
- [ ] Adicionar logging

**Arquivo:** `shared/file_manager.py`

---

## Fase 3: Source Handlers

### TASK-301: Interface Base SourceHandler
**Prioridade:** Alta
**Estimativa:** 30 min
**Dependências:** Nenhuma

**Descrição:** Criar interface abstrata em `workers/sources.py`

**Checklist:**
- [ ] Criar classe abstrata `SourceHandler`
- [ ] Definir método abstrato `download(source, temp_path, **kwargs)`
- [ ] Definir método abstrato `validate(source, **kwargs)`
- [ ] Adicionar type hints

**Arquivo:** `workers/sources.py`

---

### TASK-302: FileHandler
**Prioridade:** Alta
**Estimativa:** 1h
**Dependências:** TASK-301, TASK-205

**Descrição:** Implementar handler para upload de arquivos

**Checklist:**
- [ ] Criar classe `FileHandler(SourceHandler)`
- [ ] Implementar `validate()` - validar tamanho, MIME type
- [ ] Implementar `download()` - salvar arquivo em temp_path
- [ ] Implementar validação de extensão
- [ ] Adicionar tratamento de erros

**Arquivo:** `workers/sources.py`

---

### TASK-303: URLHandler
**Prioridade:** Alta
**Estimativa:** 2h
**Dependências:** TASK-301, TASK-205

**Descrição:** Implementar handler para download de URLs

**Checklist:**
- [ ] Criar classe `URLHandler(SourceHandler)`
- [ ] Implementar `validate()` - validar formato URL, protocolo
- [ ] Implementar `download()` - download com httpx
- [ ] Implementar timeout (30s)
- [ ] Implementar limite de redirecionamentos (5)
- [ ] Implementar validação de Content-Type
- [ ] Implementar validação de Content-Length
- [ ] Bloquear IPs privados em produção
- [ ] Adicionar tratamento de erros

**Arquivo:** `workers/sources.py`

---

### TASK-304: GoogleDriveHandler
**Prioridade:** Alta
**Estimativa:** 3h
**Dependências:** TASK-301, TASK-205

**Descrição:** Implementar handler para Google Drive

**Checklist:**
- [ ] Criar classe `GoogleDriveHandler(SourceHandler)`
- [ ] Implementar autenticação com Bearer token
- [ ] Implementar `validate()` - validar token e file_id
- [ ] Implementar `download()` - download via Drive API
- [ ] Implementar conversão de Google Docs (export)
- [ ] Implementar tratamento de permissões
- [ ] Adicionar tratamento de erros (401, 403, 404)

**Arquivo:** `workers/sources.py`

---

### TASK-305: DropboxHandler
**Prioridade:** Alta
**Estimativa:** 2h
**Dependências:** TASK-301, TASK-205

**Descrição:** Implementar handler para Dropbox

**Checklist:**
- [ ] Criar classe `DropboxHandler(SourceHandler)`
- [ ] Implementar autenticação com Bearer token
- [ ] Implementar `validate()` - validar token e path
- [ ] Implementar `download()` - download via Dropbox SDK
- [ ] Implementar verificação de existência do arquivo
- [ ] Adicionar tratamento de erros (401, 404)

**Arquivo:** `workers/sources.py`

---

### TASK-306: Source Handler Factory
**Prioridade:** Alta
**Estimativa:** 30 min
**Dependências:** TASK-302, TASK-303, TASK-304, TASK-305

**Descrição:** Criar factory para source handlers

**Checklist:**
- [ ] Criar função `get_source_handler(source_type) -> SourceHandler`
- [ ] Mapear source_type para classe handler
- [ ] Retornar instância do handler
- [ ] Lançar erro se source_type inválido

**Arquivo:** `workers/sources.py`

---

### TASK-307: Integração Source Handlers com Task
**Prioridade:** Alta
**Estimativa:** 1h
**Dependências:** TASK-306, TASK-203

**Descrição:** Integrar handlers na task de conversão

**Checklist:**
- [ ] Substituir stub de download por get_source_handler()
- [ ] Passar auth_token quando necessário
- [ ] Implementar tratamento de erros de download
- [ ] Testar cada source type end-to-end

**Arquivo:** `workers/tasks.py`

---

## Fase 4: Containerização

### TASK-401: Dockerfile para API
**Prioridade:** Alta
**Estimativa:** 1h
**Dependências:** TASK-102

**Descrição:** Criar Dockerfile otimizado para API

**Checklist:**
- [ ] Base image: python:3.10-slim
- [ ] Instalar dependências do sistema
- [ ] Copiar requirements.txt e instalar
- [ ] Copiar código da aplicação (api/, shared/)
- [ ] Expor porta 8000
- [ ] CMD com uvicorn
- [ ] Multi-stage build (se possível)
- [ ] Otimizar camadas de cache

**Arquivo:** `docker/Dockerfile.api`

---

### TASK-402: Dockerfile para Worker
**Prioridade:** Alta
**Estimativa:** 1.5h
**Dependências:** TASK-201, TASK-202

**Descrição:** Criar Dockerfile para workers Celery

**Checklist:**
- [ ] Base image: python:3.10-slim
- [ ] Instalar dependências do sistema (poppler, tesseract para Docling)
- [ ] Copiar requirements.txt e instalar
- [ ] Copiar código da aplicação (workers/, shared/)
- [ ] CMD com celery worker
- [ ] Configurar concurrency=2
- [ ] Otimizar camadas de cache

**Arquivo:** `docker/Dockerfile.worker`

---

### TASK-403: docker-compose.yml
**Prioridade:** Alta
**Estimativa:** 1h
**Dependências:** TASK-401, TASK-402

**Descrição:** Criar orquestração com Docker Compose

**Checklist:**
- [ ] Definir serviço redis (redis:7-alpine)
- [ ] Definir serviço api (build + ports + env)
- [ ] Definir serviço worker (build + env + replicas=3)
- [ ] Configurar networks
- [ ] Configurar volumes (redis_data, tmp)
- [ ] Configurar depends_on
- [ ] Configurar restart policies
- [ ] Adicionar health checks

**Arquivo:** `docker/docker-compose.yml`

---

### TASK-404: Scripts de Build e Deploy
**Prioridade:** Média
**Estimativa:** 1h
**Dependências:** TASK-403

**Descrição:** Criar scripts auxiliares

**Checklist:**
- [ ] Script `scripts/build.sh` - build de imagens
- [ ] Script `scripts/dev.sh` - iniciar em modo dev
- [ ] Script `scripts/prod.sh` - iniciar em modo prod
- [ ] Script `scripts/cleanup.sh` - limpar containers e volumes
- [ ] Script `scripts/logs.sh` - tail logs de serviços
- [ ] Documentar no README

**Arquivos:** `scripts/*.sh`

---

### TASK-405: Testes de Integração Docker
**Prioridade:** Alta
**Estimativa:** 1h
**Dependências:** TASK-403

**Descrição:** Testar setup completo com Docker

**Checklist:**
- [ ] Testar `docker-compose up`
- [ ] Testar health check da API
- [ ] Testar conversão end-to-end (file upload)
- [ ] Testar conversão de URL
- [ ] Verificar logs de workers
- [ ] Testar escalabilidade (scale worker=5)
- [ ] Testar restart de containers

---

## Fase 5: Features Avançadas

### TASK-501: Webhook de Callback
**Prioridade:** Baixa
**Estimativa:** 2h
**Dependências:** TASK-203

**Descrição:** Implementar notificação por webhook

**Checklist:**
- [ ] Adicionar função `send_callback()` em `workers/tasks.py`
- [ ] Implementar POST para callback_url
- [ ] Implementar retry com backoff (3x)
- [ ] Implementar timeout (10s)
- [ ] Não falhar job se callback falhar
- [ ] Logar tentativas de callback

**Arquivo:** `workers/tasks.py`

---

### TASK-502: Celery Beat para Cleanup
**Prioridade:** Média
**Estimativa:** 2h
**Dependências:** TASK-203

**Descrição:** Implementar cleanup automático periódico

**Checklist:**
- [ ] Criar task `cleanup_expired_jobs`
- [ ] Implementar remoção de arquivos temp antigos (>24h)
- [ ] Implementar remoção de jobs expirados do Redis
- [ ] Configurar Celery beat schedule (1 hora)
- [ ] Adicionar logging de estatísticas
- [ ] Adicionar serviço beat no docker-compose

**Arquivo:** `workers/tasks.py`

---

### TASK-503: Endpoint de Métricas (Prometheus)
**Prioridade:** Baixa
**Estimativa:** 2h
**Dependências:** TASK-102

**Descrição:** Expor métricas para Prometheus

**Checklist:**
- [ ] Instalar prometheus-client
- [ ] Criar Counter `conversions_total`
- [ ] Criar Histogram `conversion_duration_seconds`
- [ ] Criar Gauge `active_jobs`
- [ ] Criar Gauge `queue_size`
- [ ] Criar endpoint GET /metrics
- [ ] Integrar métricas na task de conversão

**Arquivo:** `api/metrics.py`

---

### TASK-504: Chunking de Documentos Grandes
**Prioridade:** Baixa
**Estimativa:** 3h
**Dependências:** TASK-202

**Descrição:** Implementar divisão de documentos grandes em chunks

**Checklist:**
- [ ] Adicionar lógica de chunking em `converter.py`
- [ ] Dividir documento por páginas ou tamanho
- [ ] Processar chunks em paralelo (subtasks)
- [ ] Combinar resultados
- [ ] Atualizar progress por chunk
- [ ] Adicionar opção `chunk_size` em ConversionOptions

**Arquivo:** `workers/converter.py`

---

### TASK-505: Logging Estruturado
**Prioridade:** Média
**Estimativa:** 2h
**Dependências:** TASK-102, TASK-203

**Descrição:** Implementar logging estruturado com structlog

**Checklist:**
- [ ] Configurar structlog na API
- [ ] Configurar structlog nos workers
- [ ] Adicionar correlation ID (job_id)
- [ ] Adicionar contexto (source_type, file_size, etc)
- [ ] Mascarar dados sensíveis (tokens)
- [ ] Configurar output JSON para produção

**Arquivos:** `api/main.py`, `workers/celery_app.py`

---

## Fase 6: Testes e QA

### TASK-601: Testes Unitários - API
**Prioridade:** Alta
**Estimativa:** 3h
**Dependências:** TASK-107

**Descrição:** Criar testes para endpoints da API

**Checklist:**
- [ ] Testar POST /convert (sucesso e erros)
- [ ] Testar GET /jobs/{job_id} (sucesso, 404)
- [ ] Testar GET /jobs/{job_id}/result (sucesso, 404, 400)
- [ ] Testar GET /health
- [ ] Testar validações (tamanho, formato, etc)
- [ ] Testar rate limiting
- [ ] Usar mocks para Redis e Celery

**Arquivo:** `tests/test_api.py`

---

### TASK-602: Testes Unitários - Converter
**Prioridade:** Alta
**Estimativa:** 2h
**Dependências:** TASK-202

**Descrição:** Criar testes para conversor

**Checklist:**
- [ ] Testar conversão de PDF
- [ ] Testar conversão de DOCX
- [ ] Testar conversão de HTML
- [ ] Testar opções (include_images, preserve_tables)
- [ ] Testar extração de metadata
- [ ] Testar tratamento de erros
- [ ] Usar arquivos de exemplo em tests/fixtures/

**Arquivo:** `tests/test_converter.py`

---

### TASK-603: Testes Unitários - Source Handlers
**Prioridade:** Alta
**Estimativa:** 3h
**Dependências:** TASK-306

**Descrição:** Criar testes para source handlers

**Checklist:**
- [ ] Testar FileHandler (validação, salvamento)
- [ ] Testar URLHandler (download, timeout, redirects)
- [ ] Testar GoogleDriveHandler (mock API)
- [ ] Testar DropboxHandler (mock SDK)
- [ ] Testar validações de cada handler
- [ ] Testar tratamento de erros

**Arquivo:** `tests/test_sources.py`

---

### TASK-604: Testes de Integração
**Prioridade:** Média
**Estimativa:** 4h
**Dependências:** TASK-405

**Descrição:** Criar testes end-to-end

**Checklist:**
- [ ] Testar fluxo completo: upload → conversão → resultado
- [ ] Testar fluxo com URL pública
- [ ] Testar múltiplos jobs em paralelo
- [ ] Testar retry de jobs falhados
- [ ] Testar expiração de resultados
- [ ] Testar cleanup automático
- [ ] Usar docker-compose para ambiente de teste

**Arquivo:** `tests/test_integration.py`

---

### TASK-605: Testes de Performance
**Prioridade:** Baixa
**Estimativa:** 3h
**Dependências:** TASK-604

**Descrição:** Criar testes de carga e performance

**Checklist:**
- [ ] Testar latência da API (p95 < 200ms)
- [ ] Testar throughput (50 conversões/min)
- [ ] Testar comportamento sob carga alta
- [ ] Testar tempo de conversão por tipo de documento
- [ ] Usar locust ou pytest-benchmark
- [ ] Documentar resultados

**Arquivo:** `tests/test_performance.py`

---

### TASK-606: Cobertura de Testes
**Prioridade:** Média
**Estimativa:** 2h
**Dependências:** TASK-601, TASK-602, TASK-603

**Descrição:** Configurar e atingir cobertura > 70%

**Checklist:**
- [ ] Instalar pytest-cov
- [ ] Configurar coverage em pytest.ini
- [ ] Rodar testes com coverage report
- [ ] Identificar áreas não cobertas
- [ ] Adicionar testes faltantes
- [ ] Configurar CI para verificar cobertura

---

### TASK-607: Documentação de Testes
**Prioridade:** Baixa
**Estimativa:** 1h
**Dependências:** TASK-606

**Descrição:** Documentar como rodar e escrever testes

**Checklist:**
- [ ] Adicionar seção "Testing" no README
- [ ] Documentar como rodar testes localmente
- [ ] Documentar como rodar testes no Docker
- [ ] Documentar fixtures disponíveis
- [ ] Documentar mocks e estratégias de teste

**Arquivo:** `README.md`, `tests/README.md`

---

## Resumo de Fases

| Fase | Tasks | Tempo Estimado | Prioridade |
|------|-------|----------------|------------|
| Fase 0: Setup Inicial | 4 tasks | ~2h | Alta |
| Fase 1: Core API | 9 tasks | ~10h | Alta |
| Fase 2: Workers e Conversão | 5 tasks | ~8h | Alta |
| Fase 3: Source Handlers | 7 tasks | ~10h | Alta |
| Fase 4: Containerização | 5 tasks | ~5.5h | Alta |
| Fase 5: Features Avançadas | 5 tasks | ~11h | Média/Baixa |
| Fase 6: Testes e QA | 7 tasks | ~18h | Alta/Média |
| **TOTAL** | **42 tasks** | **~64.5h** | - |

---

## Ordem de Execução Sugerida

### Sprint 1 (MVP - ~20h)
1. Fase 0 completa (TASK-001 a TASK-004)
2. TASK-101, TASK-102, TASK-103 (schemas, app, redis)
3. TASK-104, TASK-105, TASK-106, TASK-107 (endpoints básicos)
4. TASK-201, TASK-202, TASK-203 (celery, converter, task)
5. TASK-204 (integração API → Celery)
6. TASK-302, TASK-303 (file e url handlers)
7. TASK-307 (integração handlers)

**Resultado:** API funcional com upload e URL

### Sprint 2 (Containerização - ~10h)
1. Fase 4 completa (TASK-401 a TASK-405)
2. TASK-304, TASK-305, TASK-306 (gdrive, dropbox handlers)

**Resultado:** Sistema containerizado com todas fontes

### Sprint 3 (Qualidade - ~15h)
1. TASK-108, TASK-109 (exception handlers, rate limiting)
2. TASK-205 (gestão de arquivos temp)
3. TASK-601, TASK-602, TASK-603 (testes unitários)
4. TASK-604 (testes de integração)

**Resultado:** Sistema testado e robusto

### Sprint 4 (Features Extras - ~10h)
1. TASK-501 (webhooks)
2. TASK-502 (cleanup automático)
3. TASK-505 (logging estruturado)
4. TASK-606, TASK-607 (cobertura e docs de teste)

**Resultado:** Sistema pronto para produção

---

## Checklist de Conclusão

### MVP Completo ✓
- [ ] API aceita upload de arquivos
- [ ] API aceita URLs
- [ ] Conversão para markdown funciona
- [ ] Jobs são processados assincronamente
- [ ] Resultados são recuperáveis
- [ ] Sistema roda com Docker Compose

### Produção Ready ✓
- [ ] Todas fontes implementadas (file, url, gdrive, dropbox)
- [ ] Rate limiting configurado
- [ ] Logging estruturado
- [ ] Testes com cobertura > 70%
- [ ] Health checks funcionando
- [ ] Cleanup automático funcionando
- [ ] Documentação completa
- [ ] README com quickstart

### Nice to Have ✓
- [ ] Métricas Prometheus
- [ ] Webhooks de callback
- [ ] Chunking de documentos grandes
- [ ] Testes de performance
- [ ] Monitoring dashboard (Flower)
