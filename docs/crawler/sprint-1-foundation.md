# Sprint 1: Foundation & Data Models
**Duração:** Semanas 1-2
**Objetivo:** Estrutura de dados completa

---

## 📋 MySQL Models

### Tabela: crawler_jobs
- [ ] Criar modelo `CrawlerJob` em `backend/shared/models.py`
- [ ] Campo `id` (VARCHAR(36) PK - UUID)
- [ ] Campo `user_id` (VARCHAR(36) FK → users.id)
- [ ] Campo `name` (VARCHAR(255))
- [ ] Campo `url` (TEXT)
- [ ] Campo `url_pattern` (TEXT - para detecção de duplicatas)
- [ ] Campo `crawler_engine` (ENUM: BEAUTIFULSOUP / PLAYWRIGHT)
- [ ] Campo `use_proxy` (BOOLEAN)
- [ ] Campo `proxy_config` (JSON)
- [ ] Campo `crawl_type` (ENUM: PAGE_ONLY / PAGE_WITH_ALL / PAGE_WITH_FILTERED / FULL_WEBSITE)
- [ ] Campo `max_depth` (INTEGER)
- [ ] Campo `follow_external_links` (BOOLEAN)
- [ ] Campo `download_assets` (BOOLEAN)
- [ ] Campo `asset_types` (JSON - ["css", "js", "images", "fonts", "videos"])
- [ ] Campo `file_extensions` (JSON - ["pdf", "xlsx", "csv"])
- [ ] Campo `extension_categories` (JSON - ["documents", "images"])
- [ ] Campo `pdf_handling` (ENUM: INDIVIDUAL / COMBINED / BOTH)
- [ ] Campo `retry_enabled` (BOOLEAN)
- [ ] Campo `max_retries` (INTEGER)
- [ ] Campo `retry_strategy` (JSON - fallback de engines)
- [ ] Campo `schedule_type` (ENUM: ONE_TIME / RECURRING)
- [ ] Campo `schedule_frequency` (ENUM: HOURLY / DAILY / WEEKLY / MONTHLY / CUSTOM)
- [ ] Campo `cron_expression` (VARCHAR(100))
- [ ] Campo `timezone` (VARCHAR(50))
- [ ] Campo `next_run_at` (DATETIME)
- [ ] Campo `is_active` (BOOLEAN)
- [ ] Campo `status` (ENUM: ACTIVE / PAUSED / STOPPED / ERROR)
- [ ] Campo `total_executions` (INTEGER)
- [ ] Campo `successful_executions` (INTEGER)
- [ ] Campo `failed_executions` (INTEGER)
- [ ] Campo `last_execution_at` (DATETIME)
- [ ] Campos de auditoria: `created_at`, `updated_at`
- [ ] Foreign Key: `user_id` → `users.id`
- [ ] Relacionamento 1:N com `crawler_executions`

### Tabela: crawler_executions
- [ ] Criar modelo `CrawlerExecution` em `backend/shared/models.py`
- [ ] Campo `id` (VARCHAR(36) PK - UUID)
- [ ] Campo `crawler_job_id` (VARCHAR(36) FK → crawler_jobs.id)
- [ ] Campo `celery_task_id` (VARCHAR(36))
- [ ] Campo `status` (ENUM: PENDING / PROCESSING / COMPLETED / FAILED / CANCELLED)
- [ ] Campo `progress` (INTEGER - 0-100%)
- [ ] Campo `pages_discovered` (INTEGER)
- [ ] Campo `pages_downloaded` (INTEGER)
- [ ] Campo `pages_failed` (INTEGER)
- [ ] Campo `files_downloaded` (INTEGER)
- [ ] Campo `files_failed` (INTEGER)
- [ ] Campo `total_size_bytes` (INTEGER)
- [ ] Campo `files_by_type` (JSON - {"pdf": 10, "xlsx": 5})
- [ ] Campo `minio_folder_path` (VARCHAR(500))
- [ ] Campo `error_message` (TEXT)
- [ ] Campo `error_count` (INTEGER)
- [ ] Campo `retry_count` (INTEGER)
- [ ] Campo `current_retry_attempt` (INTEGER)
- [ ] Campo `retry_history` (JSON - histórico de tentativas)
- [ ] Campo `engine_used` (ENUM: BEAUTIFULSOUP / PLAYWRIGHT)
- [ ] Campo `proxy_used` (BOOLEAN)
- [ ] Campo `started_at` (DATETIME)
- [ ] Campo `completed_at` (DATETIME)
- [ ] Campos de auditoria: `created_at`, `updated_at`
- [ ] Foreign Key: `crawler_job_id` → `crawler_jobs.id`
- [ ] Relacionamento 1:N com `crawled_files`

### Tabela: crawled_files
- [ ] Criar modelo `CrawledFile` em `backend/shared/models.py`
- [ ] Campo `id` (VARCHAR(36) PK - UUID)
- [ ] Campo `execution_id` (VARCHAR(36) FK → crawler_executions.id)
- [ ] Campo `url` (TEXT)
- [ ] Campo `filename` (VARCHAR(255))
- [ ] Campo `file_type` (VARCHAR(20) - pdf, xlsx, jpg, etc.)
- [ ] Campo `mime_type` (VARCHAR(100))
- [ ] Campo `size_bytes` (INTEGER)
- [ ] Campo `minio_path` (VARCHAR(500))
- [ ] Campo `minio_bucket` (VARCHAR(100))
- [ ] Campo `public_url` (TEXT)
- [ ] Campo `status` (ENUM: DOWNLOADED / FAILED / SKIPPED)
- [ ] Campo `error_message` (TEXT)
- [ ] Campo `downloaded_at` (DATETIME)
- [ ] Foreign Key: `execution_id` → `crawler_executions.id`

---

## 📝 Alembic Migrations

- [ ] Criar migration: `alembic revision --autogenerate -m "Add crawler tables"`
- [ ] Verificar migration gerada em `backend/alembic/versions/`
- [ ] Revisar script de migration (create tables, foreign keys, indexes)
- [ ] Adicionar índices necessários:
  - [ ] Index em `crawler_jobs.user_id`
  - [ ] Index em `crawler_jobs.url_pattern`
  - [ ] Index em `crawler_jobs.status`
  - [ ] Index em `crawler_jobs.is_active`
  - [ ] Index em `crawler_jobs.next_run_at`
  - [ ] Index em `crawler_executions.crawler_job_id`
  - [ ] Index em `crawler_executions.status`
  - [ ] Index em `crawler_executions.started_at`
  - [ ] Index em `crawled_files.execution_id`
- [ ] Aplicar migration: `alembic upgrade head`
- [ ] Verificar tabelas criadas no MySQL

---

## 🔍 Elasticsearch Indices

### Index: crawler-jobs-*
- [ ] Criar schema Elasticsearch em `backend/infrastructure/elasticsearch/`
- [ ] Definir mapping:
  - [ ] `job_id` (keyword)
  - [ ] `user_id` (keyword)
  - [ ] `name` (text + keyword)
  - [ ] `url` (keyword)
  - [ ] `url_pattern` (text com analyzer 'standard')
  - [ ] `crawl_type` (keyword)
  - [ ] `schedule_type`, `schedule_frequency` (keyword)
  - [ ] `is_active`, `status` (keyword)
  - [ ] `total_executions`, `successful_executions`, `failed_executions` (integer)
  - [ ] `last_execution_at`, `next_run_at`, `created_at`, `updated_at` (date)
  - [ ] `tags` (keyword multi-valued)
- [ ] Criar índice no Elasticsearch
- [ ] Configurar aliases: `crawler-jobs` → `crawler-jobs-*`

### Index: crawler-executions-* (time-series)
- [ ] Criar schema Elasticsearch (time-series)
- [ ] Definir mapping:
  - [ ] `execution_id` (keyword)
  - [ ] `crawler_job_id` (keyword)
  - [ ] `status` (keyword)
  - [ ] `progress` (integer)
  - [ ] `pages_discovered`, `pages_downloaded`, `pages_failed` (integer)
  - [ ] `files_downloaded`, `files_failed`, `total_size_bytes` (integer)
  - [ ] `files_by_type` (nested)
  - [ ] `duration_seconds` (integer)
  - [ ] `average_download_speed_mbps` (float)
  - [ ] `started_at`, `completed_at` (date)
- [ ] Configurar ILM (Index Lifecycle Management):
  - [ ] Rollover diário
  - [ ] Deleção após 90 dias
- [ ] Criar índice inicial

### Index: crawler-metrics-YYYY.MM.DD (métricas tempo real)
- [ ] Criar schema Elasticsearch (métricas tempo real)
- [ ] Definir mapping:
  - [ ] `execution_id` (keyword)
  - [ ] `timestamp` (date)
  - [ ] `progress_percentage` (float)
  - [ ] `pages_processed`, `files_processed`, `bytes_downloaded` (integer)
  - [ ] `download_speed_bps`, `response_time_ms` (float)
  - [ ] `memory_mb`, `cpu_percent` (float)
  - [ ] `error_count` (integer)
  - [ ] `errors` (text multi-valued)
- [ ] Configurar settings:
  - [ ] `refresh_interval: 5s` (near real-time)
  - [ ] `number_of_shards: 1`
- [ ] Configurar ILM:
  - [ ] Rollover diário
  - [ ] Deleção após 7 dias

---

## 🎯 Domain Entities

### Entity: CrawlerJob
- [ ] Criar `backend/domain/entities/crawler_job.py`
- [ ] Propriedades: id, user_id, name, url, url_pattern, etc.
- [ ] Método `activate()` - Ativar crawler
- [ ] Método `pause()` - Pausar crawler
- [ ] Método `stop()` - Parar permanentemente
- [ ] Método `update_schedule(cron)` - Atualizar agendamento
- [ ] Método `record_execution(success)` - Registrar execução
- [ ] Validações:
  - [ ] URL não pode ser localhost/127.0.0.1/IPs privados
  - [ ] Cron expression válida
  - [ ] Engine válida (BEAUTIFULSOUP / PLAYWRIGHT)
  - [ ] Asset types válidos

### Entity: CrawlerExecution
- [ ] Criar `backend/domain/entities/crawler_execution.py`
- [ ] Propriedades: id, crawler_job_id, status, progress, etc.
- [ ] Método `is_running()` - Verificar se está em execução
- [ ] Método `is_completed()` - Verificar se finalizou
- [ ] Método `mark_failed(error)` - Marcar como falho
- [ ] Método `update_progress(percentage)` - Atualizar progresso (0-100)
- [ ] Validações:
  - [ ] Progress entre 0-100
  - [ ] Status válido

### Entity: CrawledFile
- [ ] Criar `backend/domain/entities/crawled_file.py`
- [ ] Propriedades: id, execution_id, url, filename, file_type, etc.
- [ ] Validações:
  - [ ] URL válida
  - [ ] File type permitido

---

## 💎 Value Objects

### URLPattern
- [ ] Criar `backend/domain/value_objects/url_pattern.py`
- [ ] Método `normalize_url(url)` - Normalizar URL
- [ ] Método `generate_pattern(url)` - Gerar padrão para fuzzy matching
- [ ] Regras de normalização:
  - [ ] Lowercase domain
  - [ ] Remove trailing slash
  - [ ] Sort query parameters
  - [ ] Substituir valores de params por wildcards
  - [ ] Remove fragment (#)
- [ ] Validações:
  - [ ] Protocolo http/https apenas
  - [ ] Não permitir localhost/IPs privados

### CrawlerSchedule
- [ ] Criar `backend/domain/value_objects/crawler_schedule.py`
- [ ] Validar `schedule_type` (one_time, recurring)
- [ ] Validar `cron_expression` (usando croniter)
- [ ] Método `calculate_next_run(timezone)` - Calcular próxima execução
- [ ] Conversão de timezone

### CrawlerEngine
- [ ] Criar `backend/domain/value_objects/crawler_engine.py`
- [ ] ENUM: BEAUTIFULSOUP / PLAYWRIGHT
- [ ] Validação de engine

### ProxyConfig
- [ ] Criar `backend/domain/value_objects/proxy_config.py`
- [ ] Propriedades: host, port, username, password, protocol
- [ ] Validações:
  - [ ] Protocol válido (http, https, socks5)
  - [ ] Port válido (1-65535)

### AssetTypes
- [ ] Criar `backend/domain/value_objects/asset_types.py`
- [ ] Lista de tipos: css, js, images, fonts, videos, documents
- [ ] Validação de tipos permitidos
- [ ] Método `get_extensions(type)` - Retornar extensões por tipo

### DownloadConfig
- [ ] Criar `backend/domain/value_objects/download_config.py`
- [ ] Validar `crawl_type`
- [ ] Validar `file_extensions`
- [ ] Validar `pdf_handling` (INDIVIDUAL / COMBINED / BOTH)

---

## 🛠️ Domain Services

### URLNormalizerService
- [ ] Criar `backend/domain/services/url_normalizer_service.py`
- [ ] Método `normalize_url(url)` - Normalizar para comparação exata
- [ ] Método `generate_pattern(url)` - Gerar padrão para fuzzy matching
- [ ] Testes unitários

### DuplicateDetectorService
- [ ] Criar `backend/domain/services/duplicate_detector_service.py`
- [ ] Método `find_duplicates(url)` - Buscar crawlers com URL similar
- [ ] Método `has_duplicate(url)` - Verificar se existe duplicata
- [ ] Integração com Elasticsearch (fuzzy match em `url_pattern`)
- [ ] Testes unitários

### CrawlerProgressService
- [ ] Criar `backend/domain/services/crawler_progress_service.py`
- [ ] Método `calculate_progress(execution)` - Calcular progresso baseado em:
  - [ ] Páginas processadas
  - [ ] Arquivos baixados
  - [ ] Etapa atual (crawling 0-20%, downloading 20-80%, merging 80-90%, uploading 90-100%)
- [ ] Testes unitários

---

## 📁 Repository Interfaces

### CrawlerJobRepository
- [ ] Criar interface `backend/domain/repositories/crawler_job_repository.py`
- [ ] Método abstrato `save(crawler_job)`
- [ ] Método abstrato `find_by_id(id)`
- [ ] Método abstrato `find_by_user_id(user_id)`
- [ ] Método abstrato `find_by_url_pattern(pattern)`
- [ ] Método abstrato `find_active()`
- [ ] Método abstrato `delete(id)`

### CrawlerExecutionRepository
- [ ] Criar interface `backend/domain/repositories/crawler_execution_repository.py`
- [ ] Método abstrato `save(execution)`
- [ ] Método abstrato `update(execution)`
- [ ] Método abstrato `find_by_id(id)`
- [ ] Método abstrato `find_by_crawler_job_id(job_id)`
- [ ] Método abstrato `find_running()`

### CrawledFileRepository
- [ ] Criar interface `backend/domain/repositories/crawled_file_repository.py`
- [ ] Método abstrato `save(file)`
- [ ] Método abstrato `find_by_execution_id(execution_id)`
- [ ] Método abstrato `count_by_type(execution_id)`

---

## ✅ Testes Unitários

### Domain Entities
- [ ] Testes para `CrawlerJob` entity
  - [ ] Teste `activate()`, `pause()`, `stop()`
  - [ ] Teste `update_schedule()`
  - [ ] Teste `record_execution()`
  - [ ] Teste validações
- [ ] Testes para `CrawlerExecution` entity
  - [ ] Teste `is_running()`, `is_completed()`
  - [ ] Teste `mark_failed()`
  - [ ] Teste `update_progress()`
- [ ] Testes para `CrawledFile` entity

### Value Objects
- [ ] Testes para `URLPattern`
  - [ ] Teste normalização
  - [ ] Teste geração de padrão
  - [ ] Teste validações
- [ ] Testes para `CrawlerSchedule`
  - [ ] Teste validação de cron
  - [ ] Teste cálculo de next_run
- [ ] Testes para `ProxyConfig`, `AssetTypes`, `DownloadConfig`

### Domain Services
- [ ] Testes para `URLNormalizerService`
- [ ] Testes para `DuplicateDetectorService` (com mock Elasticsearch)
- [ ] Testes para `CrawlerProgressService`

### Coverage
- [ ] Coverage >= 90% no domain layer
- [ ] Rodar: `pytest backend/tests/domain/ -v --cov=backend/domain`

---

## 🎯 Entregável Sprint 1

- [ ] ✅ Todos os modelos MySQL criados e migrados
- [ ] ✅ Todos os índices Elasticsearch configurados
- [ ] ✅ Todas as entidades de domínio implementadas
- [ ] ✅ Todos os value objects implementados
- [ ] ✅ Todos os domain services implementados
- [ ] ✅ Todas as interfaces de repositórios definidas
- [ ] ✅ Coverage >= 90% de testes unitários
- [ ] ✅ Documentação atualizada (domain layer)

---

## 📚 Referências

- [CRAWLER_INTEGRATION_PLAN.md](./CRAWLER_INTEGRATION_PLAN.md) - Plano completo
- [CRAWLER.md](./CRAWLER.md) - PRD original
- [backend/docs/CLEAN_ARCHITECTURE.md](../../backend/docs/CLEAN_ARCHITECTURE.md) - Guia de arquitetura
