# Sprint 3: Application Layer & Use Cases

> **Plano de sprint (crawler) — não concluído.** Estado real do crawler no código: [../features/crawler.md](../features/crawler.md).

**Duração:** Semanas 5-6
**Objetivo:** Lógica de negócio (Use Cases)

---

## 📦 DTOs (Data Transfer Objects)

### CrawlerJobDTO
- [ ] Criar `backend/application/dtos/crawler_job_dto.py`
- [ ] Propriedades (Pydantic BaseModel):
  - [ ] id, user_id, name, url, url_pattern
  - [ ] crawler_engine, use_proxy, proxy_config
  - [ ] crawl_type, max_depth, follow_external_links
  - [ ] download_assets, asset_types
  - [ ] file_extensions, extension_categories, pdf_handling
  - [ ] retry_enabled, max_retries, retry_strategy
  - [ ] schedule_type, schedule_frequency, cron_expression, timezone
  - [ ] next_run_at, is_active, status
  - [ ] total_executions, successful_executions, failed_executions
  - [ ] last_execution_at, created_at, updated_at
- [ ] Método `from_entity(crawler_job)` - Converter entity → DTO
- [ ] Método `to_entity()` - Converter DTO → entity

### CrawlerExecutionDTO
- [ ] Criar `backend/application/dtos/crawler_execution_dto.py`
- [ ] Propriedades:
  - [ ] id, crawler_job_id, celery_task_id
  - [ ] status, progress
  - [ ] pages_discovered, pages_downloaded, pages_failed
  - [ ] files_downloaded, files_failed, total_size_bytes
  - [ ] files_by_type, minio_folder_path
  - [ ] error_message, error_count
  - [ ] retry_count, current_retry_attempt, retry_history
  - [ ] engine_used, proxy_used
  - [ ] started_at, completed_at, created_at, updated_at
- [ ] Método `from_entity(execution)`
- [ ] Método `to_entity()`

### CrawledFileDTO
- [ ] Criar `backend/application/dtos/crawled_file_dto.py`
- [ ] Propriedades:
  - [ ] id, execution_id, url, filename
  - [ ] file_type, mime_type, size_bytes
  - [ ] minio_path, minio_bucket, public_url
  - [ ] status, error_message, downloaded_at
- [ ] Método `from_entity(file)`

### CreateCrawlerJobDTO
- [ ] Criar `backend/application/dtos/create_crawler_job_dto.py`
- [ ] Input DTO para criação de crawler
- [ ] Propriedades (apenas campos necessários):
  - [ ] user_id, name, url
  - [ ] crawler_engine (default: BEAUTIFULSOUP)
  - [ ] use_proxy (default: False)
  - [ ] proxy_config (optional)
  - [ ] crawl_type, max_depth, follow_external_links
  - [ ] download_assets, asset_types
  - [ ] file_extensions, extension_categories, pdf_handling
  - [ ] retry_enabled, max_retries, retry_strategy
  - [ ] schedule_type, schedule_frequency, cron_expression, timezone
- [ ] Validações Pydantic:
  - [ ] URL válida (HttpUrl)
  - [ ] crawler_engine válido
  - [ ] cron_expression válido (se CUSTOM)

### UpdateCrawlerJobDTO
- [ ] Criar `backend/application/dtos/update_crawler_job_dto.py`
- [ ] Input DTO para atualização
- [ ] Propriedades (todos opcionais):
  - [ ] name, cron_expression, file_extensions
  - [ ] is_active, max_retries, etc.
- [ ] Validações

---

## 🎯 Use Cases

### CreateCrawlerJobUseCase
- [ ] Criar `backend/application/use_cases/create_crawler_job_use_case.py`
- [ ] Dependências (constructor injection):
  - [ ] crawler_job_repository: CrawlerJobRepository
  - [ ] url_normalizer_service: URLNormalizerService
  - [ ] duplicate_detector_service: DuplicateDetectorService
  - [ ] crawler_job_index: CrawlerJobIndex (Elasticsearch)
  - [ ] celery_app: Celery
- [ ] Método `execute(dto: CreateCrawlerJobDTO) -> CrawlerJobDTO`:
  1. [ ] **Validar URL**:
     - [ ] Não permitir localhost, 127.0.0.1, IPs privados
     - [ ] Não permitir IPs de metadados cloud (169.254.169.254)
     - [ ] Protocolo http/https apenas
  2. [ ] **Normalizar URL**:
     - [ ] url_normalized = url_normalizer_service.normalize_url(dto.url)
     - [ ] url_pattern = url_normalizer_service.generate_pattern(dto.url)
  3. [ ] **Verificar duplicatas**:
     - [ ] duplicates = duplicate_detector_service.find_duplicates(url_pattern)
     - [ ] Se encontrar: adicionar warning na resposta (não bloqueia)
  4. [ ] **Criar entidade CrawlerJob**:
     - [ ] crawler_job = CrawlerJob(...) # preencher todos os campos
     - [ ] Gerar UUID
     - [ ] Calcular next_run_at (se recurring)
  5. [ ] **Salvar no MySQL**:
     - [ ] crawler_job_repository.save(crawler_job)
  6. [ ] **Indexar no Elasticsearch**:
     - [ ] crawler_job_index.index_crawler_job(crawler_job)
  7. [ ] **Registrar no Celery Beat** (se recurring):
     - [ ] celery_app.conf.beat_schedule[f'crawler-{job.id}'] = {
           'task': 'workers.crawler_tasks.schedule_crawler',
           'schedule': crontab(...),
           'args': (job.id,)
         }
     - [ ] Persist beat schedule
  8. [ ] **Retornar DTO**:
     - [ ] return CrawlerJobDTO.from_entity(crawler_job)
- [ ] Testes unitários (com mocks)

### ExecuteCrawlerJobUseCase
- [ ] Criar `backend/application/use_cases/execute_crawler_job_use_case.py`
- [ ] Dependências:
  - [ ] crawler_job_repository: CrawlerJobRepository
  - [ ] crawler_execution_repository: CrawlerExecutionRepository
  - [ ] celery_app: Celery
- [ ] Método `execute(crawler_job_id: str) -> CrawlerExecutionDTO`:
  1. [ ] **Buscar CrawlerJob**:
     - [ ] job = crawler_job_repository.find_by_id(crawler_job_id)
     - [ ] Se não existe: raise NotFoundError
  2. [ ] **Validar se está ativo**:
     - [ ] if not job.is_active: raise InvalidOperationError("Crawler is not active")
  3. [ ] **Criar CrawlerExecution**:
     - [ ] execution = CrawlerExecution(crawler_job_id=job.id, status=PENDING)
     - [ ] Gerar UUID
  4. [ ] **Salvar no MySQL**:
     - [ ] crawler_execution_repository.save(execution)
  5. [ ] **Disparar Celery task**:
     - [ ] task = celery_app.send_task(
           'workers.crawler_tasks.execute_crawler',
           args=(job.id, execution.id),
           queue='crawler'
         )
     - [ ] execution.celery_task_id = task.id
     - [ ] crawler_execution_repository.update(execution)
  6. [ ] **Retornar DTO**:
     - [ ] return CrawlerExecutionDTO.from_entity(execution)
- [ ] Testes unitários

### ListCrawlerJobsUseCase
- [ ] Criar `backend/application/use_cases/list_crawler_jobs_use_case.py`
- [ ] Dependências:
  - [ ] crawler_job_repository: CrawlerJobRepository
- [ ] Input DTO: `ListCrawlerJobsFilters`
  - [ ] user_id: str
  - [ ] status: Optional[str]
  - [ ] search: Optional[str] (busca por nome ou URL)
  - [ ] limit: int = 20
  - [ ] offset: int = 0
- [ ] Método `execute(filters: ListCrawlerJobsFilters) -> List[CrawlerJobDTO]`:
  1. [ ] **Query no repositório**:
     - [ ] jobs = crawler_job_repository.find_by_user_id(
           filters.user_id,
           status=filters.status,
           search=filters.search,
           limit=filters.limit,
           offset=filters.offset
         )
  2. [ ] **Ordenar por created_at DESC**
  3. [ ] **Converter para DTOs**:
     - [ ] return [CrawlerJobDTO.from_entity(job) for job in jobs]
- [ ] Testes unitários

### UpdateCrawlerJobUseCase
- [ ] Criar `backend/application/use_cases/update_crawler_job_use_case.py`
- [ ] Dependências:
  - [ ] crawler_job_repository: CrawlerJobRepository
  - [ ] crawler_job_index: CrawlerJobIndex
  - [ ] celery_app: Celery
- [ ] Método `execute(job_id: str, dto: UpdateCrawlerJobDTO, user_id: str) -> CrawlerJobDTO`:
  1. [ ] **Buscar CrawlerJob**:
     - [ ] job = crawler_job_repository.find_by_id(job_id)
     - [ ] Se não existe: raise NotFoundError
  2. [ ] **Validar permissões**:
     - [ ] if job.user_id != user_id: raise UnauthorizedError
  3. [ ] **Atualizar campos**:
     - [ ] if dto.name: job.name = dto.name
     - [ ] if dto.cron_expression: job.cron_expression = dto.cron_expression
     - [ ] Etc. (atualizar apenas campos presentes no DTO)
  4. [ ] **Atualizar no MySQL**:
     - [ ] crawler_job_repository.save(job)
  5. [ ] **Atualizar Elasticsearch**:
     - [ ] crawler_job_index.update_crawler_job(job)
  6. [ ] **Atualizar Celery Beat** (se mudou cron):
     - [ ] if dto.cron_expression:
           celery_app.conf.beat_schedule[f'crawler-{job.id}']['schedule'] = crontab(...)
  7. [ ] **Retornar DTO**:
     - [ ] return CrawlerJobDTO.from_entity(job)
- [ ] Testes unitários

### PauseCrawlerJobUseCase
- [ ] Criar `backend/application/use_cases/pause_crawler_job_use_case.py`
- [ ] Dependências:
  - [ ] crawler_job_repository: CrawlerJobRepository
  - [ ] crawler_job_index: CrawlerJobIndex
  - [ ] celery_app: Celery
- [ ] Método `execute(job_id: str, user_id: str) -> CrawlerJobDTO`:
  1. [ ] **Buscar CrawlerJob**:
     - [ ] job = crawler_job_repository.find_by_id(job_id)
  2. [ ] **Validar permissões**:
     - [ ] if job.user_id != user_id: raise UnauthorizedError
  3. [ ] **Pausar crawler**:
     - [ ] job.pause() # is_active = False, status = PAUSED
  4. [ ] **Atualizar no MySQL**:
     - [ ] crawler_job_repository.save(job)
  5. [ ] **Atualizar Elasticsearch**:
     - [ ] crawler_job_index.update_crawler_job(job)
  6. [ ] **Remover do Celery Beat** (se recurring):
     - [ ] if job.schedule_type == RECURRING:
           del celery_app.conf.beat_schedule[f'crawler-{job.id}']
  7. [ ] **(Opcional) Cancelar execuções em andamento**:
     - [ ] executions = crawler_execution_repository.find_running()
     - [ ] for exec in executions:
           celery_app.control.revoke(exec.celery_task_id, terminate=True)
  8. [ ] **Retornar DTO**:
     - [ ] return CrawlerJobDTO.from_entity(job)
- [ ] Testes unitários

### ResumeCrawlerJobUseCase
- [ ] Criar `backend/application/use_cases/resume_crawler_job_use_case.py`
- [ ] Similar ao Pause, mas inverte (is_active = True, status = ACTIVE)
- [ ] Re-adicionar ao Celery Beat
- [ ] Testes unitários

### GetCrawlerExecutionHistoryUseCase
- [ ] Criar `backend/application/use_cases/get_crawler_execution_history_use_case.py`
- [ ] Dependências:
  - [ ] crawler_execution_repository: CrawlerExecutionRepository
- [ ] Input DTO: `ExecutionHistoryFilters`
  - [ ] crawler_job_id: str
  - [ ] status: Optional[str]
  - [ ] date_range: Optional[DateRange]
  - [ ] limit: int = 20
  - [ ] offset: int = 0
- [ ] Método `execute(filters: ExecutionHistoryFilters) -> List[CrawlerExecutionDTO]`:
  1. [ ] **Buscar execuções**:
     - [ ] executions = crawler_execution_repository.find_by_crawler_job_id(
           filters.crawler_job_id,
           status=filters.status,
           date_range=filters.date_range,
           limit=filters.limit,
           offset=filters.offset
         )
  2. [ ] **Ordenar por started_at DESC**
  3. [ ] **Enriquecer com estatísticas**:
     - [ ] Calcular success_rate
     - [ ] Calcular avg_duration
  4. [ ] **Converter para DTOs**:
     - [ ] return [CrawlerExecutionDTO.from_entity(exec) for exec in executions]
- [ ] Testes unitários

### GetCrawlerExecutionDetailsUseCase
- [ ] Criar `backend/application/use_cases/get_crawler_execution_details_use_case.py`
- [ ] Dependências:
  - [ ] crawler_execution_repository: CrawlerExecutionRepository
  - [ ] crawled_file_repository: CrawledFileRepository
- [ ] Método `execute(execution_id: str, user_id: str) -> CrawlerExecutionDetailsDTO`:
  1. [ ] **Buscar execução**:
     - [ ] execution = crawler_execution_repository.find_by_id(execution_id)
  2. [ ] **Validar permissões** (via crawler_job.user_id)
  3. [ ] **Buscar arquivos baixados**:
     - [ ] files = crawled_file_repository.find_by_execution_id(execution_id)
  4. [ ] **Montar DTO detalhado**:
     - [ ] return CrawlerExecutionDetailsDTO(execution=..., files=...)
- [ ] Testes unitários

### CancelCrawlerExecutionUseCase
- [ ] Criar `backend/application/use_cases/cancel_crawler_execution_use_case.py`
- [ ] Dependências:
  - [ ] crawler_execution_repository: CrawlerExecutionRepository
  - [ ] celery_app: Celery
- [ ] Método `execute(execution_id: str, user_id: str) -> CrawlerExecutionDTO`:
  1. [ ] **Buscar execução**
  2. [ ] **Validar permissões**
  3. [ ] **Verificar se está rodando**:
     - [ ] if not execution.is_running(): raise InvalidOperationError
  4. [ ] **Revogar Celery task**:
     - [ ] celery_app.control.revoke(execution.celery_task_id, terminate=True)
  5. [ ] **Atualizar status**:
     - [ ] execution.status = CANCELLED
     - [ ] crawler_execution_repository.update(execution)
  6. [ ] **Retornar DTO**
- [ ] Testes unitários

### DeleteCrawlerJobUseCase
- [ ] Criar `backend/application/use_cases/delete_crawler_job_use_case.py`
- [ ] Dependências:
  - [ ] crawler_job_repository: CrawlerJobRepository
  - [ ] crawler_job_index: CrawlerJobIndex
  - [ ] celery_app: Celery
  - [ ] minio_crawler_storage_adapter: MinioCrawlerStorageAdapter
- [ ] Método `execute(job_id: str, user_id: str) -> None`:
  1. [ ] **Buscar crawler**
  2. [ ] **Validar permissões**
  3. [ ] **Cancelar execuções em andamento**
  4. [ ] **Remover do Celery Beat**
  5. [ ] **Deletar do Elasticsearch**:
     - [ ] crawler_job_index.delete_job(job_id)
  6. [ ] **Deletar arquivos do MinIO** (todas as execuções):
     - [ ] executions = crawler_execution_repository.find_by_crawler_job_id(job_id)
     - [ ] for exec in executions:
           minio_crawler_storage_adapter.delete_execution_folder(exec.id)
  7. [ ] **Deletar do MySQL** (cascade para executions e files):
     - [ ] crawler_job_repository.delete(job_id)
- [ ] Testes unitários

---

## ✅ Testes Unitários

### Use Case Tests
- [ ] Criar `backend/tests/application/use_cases/test_create_crawler_job_use_case.py`
  - [ ] Mock todas as dependências (repositories, services, celery)
  - [ ] Teste criação bem-sucedida
  - [ ] Teste validação de URL (localhost bloqueado)
  - [ ] Teste detecção de duplicatas (warning)
  - [ ] Teste registro no Celery Beat (recurring)
- [ ] Criar `backend/tests/application/use_cases/test_execute_crawler_job_use_case.py`
  - [ ] Teste execução bem-sucedida
  - [ ] Teste crawler inativo (erro)
  - [ ] Teste crawler não encontrado (erro)
- [ ] Criar `backend/tests/application/use_cases/test_list_crawler_jobs_use_case.py`
  - [ ] Teste listagem com filtros
  - [ ] Teste paginação
- [ ] Criar `backend/tests/application/use_cases/test_update_crawler_job_use_case.py`
  - [ ] Teste atualização bem-sucedida
  - [ ] Teste permissões (outro usuário)
  - [ ] Teste atualização de cron (Celery Beat update)
- [ ] Criar `backend/tests/application/use_cases/test_pause_crawler_job_use_case.py`
  - [ ] Teste pausar crawler
  - [ ] Teste remoção do Celery Beat
  - [ ] Teste cancelamento de execuções
- [ ] Criar `backend/tests/application/use_cases/test_get_crawler_execution_history_use_case.py`
- [ ] Criar `backend/tests/application/use_cases/test_cancel_crawler_execution_use_case.py`
- [ ] Criar `backend/tests/application/use_cases/test_delete_crawler_job_use_case.py`

### DTO Tests
- [ ] Criar `backend/tests/application/dtos/test_crawler_job_dto.py`
  - [ ] Teste `from_entity()` e `to_entity()`
  - [ ] Teste serialização JSON (Pydantic)
- [ ] Criar `backend/tests/application/dtos/test_create_crawler_job_dto.py`
  - [ ] Teste validações Pydantic
  - [ ] Teste URL inválida
  - [ ] Teste cron inválido

### Coverage
- [ ] Coverage >= 90% na application layer
- [ ] Rodar: `pytest backend/tests/application/ -v --cov=backend/application`

---

## 📋 Dependency Injection

### Container Setup
- [ ] Criar `backend/application/container.py` (ou usar framework DI)
- [ ] Registrar todas as dependências:
  - [ ] Repositories (MySQL implementations)
  - [ ] Adapters (Elasticsearch, MinIO, Crawler)
  - [ ] Services (domain services)
  - [ ] Use Cases
- [ ] Exemplo:
  ```python
  from dependency_injector import containers, providers

  class Container(containers.DeclarativeContainer):
      # Repositories
      crawler_job_repository = providers.Singleton(MySQLCrawlerJobRepository)
      crawler_execution_repository = providers.Singleton(MySQLCrawlerExecutionRepository)

      # Adapters
      crawler_job_index = providers.Singleton(CrawlerJobIndex)

      # Services
      url_normalizer_service = providers.Singleton(URLNormalizerService)
      duplicate_detector_service = providers.Factory(
          DuplicateDetectorService,
          crawler_job_index=crawler_job_index
      )

      # Use Cases
      create_crawler_job_use_case = providers.Factory(
          CreateCrawlerJobUseCase,
          crawler_job_repository=crawler_job_repository,
          url_normalizer_service=url_normalizer_service,
          duplicate_detector_service=duplicate_detector_service,
          crawler_job_index=crawler_job_index
      )
  ```
- [ ] Integrar com FastAPI (via Depends)

---

## 🎯 Entregável Sprint 3

- [ ] ✅ Todos os DTOs implementados e validados
- [ ] ✅ Todos os Use Cases implementados:
  - [ ] CreateCrawlerJobUseCase
  - [ ] ExecuteCrawlerJobUseCase
  - [ ] ListCrawlerJobsUseCase
  - [ ] UpdateCrawlerJobUseCase
  - [ ] PauseCrawlerJobUseCase
  - [ ] ResumeCrawlerJobUseCase
  - [ ] GetCrawlerExecutionHistoryUseCase
  - [ ] GetCrawlerExecutionDetailsUseCase
  - [ ] CancelCrawlerExecutionUseCase
  - [ ] DeleteCrawlerJobUseCase
- [ ] ✅ Dependency injection configurado
- [ ] ✅ Coverage >= 90% de testes unitários
- [ ] ✅ Todos os use cases testados com mocks
- [ ] ✅ Documentação atualizada (application layer)

---

## 📚 Referências

- [CRAWLER_INTEGRATION_PLAN.md](./CRAWLER_INTEGRATION_PLAN.md) - Seção 5 (Application Layer)
- [backend/docs/CLEAN_ARCHITECTURE.md](../../backend/docs/CLEAN_ARCHITECTURE.md) - Use Cases guide
- Pydantic docs: https://docs.pydantic.dev/
