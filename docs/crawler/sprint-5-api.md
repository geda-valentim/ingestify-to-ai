# Sprint 5: API & Presentation Layer
**Duração:** Semanas 9-10
**Objetivo:** Endpoints REST completos

---

## 🌐 API Controllers

### CrawlerController
- [ ] Criar `backend/presentation/controllers/crawler_controller.py`
- [ ] Usar FastAPI Router:
  ```python
  from fastapi import APIRouter, Depends, HTTPException, status
  from backend.application.use_cases import *
  from backend.presentation.schemas import *

  router = APIRouter(prefix="/crawlers", tags=["Crawlers"])
  ```

---

## 📋 Endpoints - Crawler Management

### POST /crawlers
**Criar novo crawler agendado**

- [ ] Endpoint:
  ```python
  @router.post("/", response_model=CrawlerJobResponse, status_code=status.HTTP_201_CREATED)
  async def create_crawler(
      request: CreateCrawlerJobRequest,
      current_user: User = Depends(get_current_user),
      use_case: CreateCrawlerJobUseCase = Depends(get_create_crawler_job_use_case)
  ):
      dto = CreateCrawlerJobDTO(**request.dict(), user_id=current_user.id)
      result = use_case.execute(dto)
      return CrawlerJobResponse.from_dto(result)
  ```
- [ ] Request schema: `CreateCrawlerJobRequest`
- [ ] Response schema: `CrawlerJobResponse`
- [ ] Autenticação: JWT/API Key
- [ ] Validações:
  - [ ] URL válida
  - [ ] Cron expression válida (se CUSTOM)
  - [ ] Engine válida
  - [ ] Asset types válidos
- [ ] Error handling:
  - [ ] 400 Bad Request (validação)
  - [ ] 401 Unauthorized
  - [ ] 409 Conflict (duplicata - warning apenas)

### GET /crawlers
**Listar crawlers do usuário**

- [ ] Endpoint:
  ```python
  @router.get("/", response_model=CrawlerJobListResponse)
  async def list_crawlers(
      status: Optional[str] = None,
      search: Optional[str] = None,
      limit: int = 20,
      offset: int = 0,
      current_user: User = Depends(get_current_user),
      use_case: ListCrawlerJobsUseCase = Depends(get_list_crawler_jobs_use_case)
  ):
      filters = ListCrawlerJobsFilters(
          user_id=current_user.id,
          status=status,
          search=search,
          limit=limit,
          offset=offset
      )
      jobs = use_case.execute(filters)
      return CrawlerJobListResponse(
          jobs=[CrawlerJobResponse.from_dto(j) for j in jobs],
          total=len(jobs),
          limit=limit,
          offset=offset
      )
  ```
- [ ] Query parameters: status, search, limit, offset
- [ ] Response schema: `CrawlerJobListResponse`
- [ ] Paginação
- [ ] Filtros opcionais

### GET /crawlers/{id}
**Obter detalhes de um crawler**

- [ ] Endpoint:
  ```python
  @router.get("/{crawler_id}", response_model=CrawlerJobResponse)
  async def get_crawler(
      crawler_id: str,
      current_user: User = Depends(get_current_user),
      use_case: GetCrawlerJobUseCase = Depends(get_get_crawler_job_use_case)
  ):
      job = use_case.execute(crawler_id, current_user.id)
      if not job:
          raise HTTPException(status_code=404, detail="Crawler not found")
      return CrawlerJobResponse.from_dto(job)
  ```
- [ ] Path parameter: crawler_id
- [ ] Response schema: `CrawlerJobResponse`
- [ ] Error handling:
  - [ ] 404 Not Found
  - [ ] 403 Forbidden (outro usuário)

### PATCH /crawlers/{id}
**Atualizar configuração de crawler**

- [ ] Endpoint:
  ```python
  @router.patch("/{crawler_id}", response_model=CrawlerJobResponse)
  async def update_crawler(
      crawler_id: str,
      request: UpdateCrawlerJobRequest,
      current_user: User = Depends(get_current_user),
      use_case: UpdateCrawlerJobUseCase = Depends(get_update_crawler_job_use_case)
  ):
      dto = UpdateCrawlerJobDTO(**request.dict(exclude_unset=True))
      result = use_case.execute(crawler_id, dto, current_user.id)
      return CrawlerJobResponse.from_dto(result)
  ```
- [ ] Request schema: `UpdateCrawlerJobRequest` (campos opcionais)
- [ ] Response schema: `CrawlerJobResponse`
- [ ] Validações:
  - [ ] Campos modificados apenas
  - [ ] Cron válido (se atualizado)
- [ ] Error handling:
  - [ ] 404 Not Found
  - [ ] 403 Forbidden

### DELETE /crawlers/{id}
**Deletar crawler**

- [ ] Endpoint:
  ```python
  @router.delete("/{crawler_id}", status_code=status.HTTP_204_NO_CONTENT)
  async def delete_crawler(
      crawler_id: str,
      current_user: User = Depends(get_current_user),
      use_case: DeleteCrawlerJobUseCase = Depends(get_delete_crawler_job_use_case)
  ):
      use_case.execute(crawler_id, current_user.id)
      return None
  ```
- [ ] Response: 204 No Content
- [ ] Error handling:
  - [ ] 404 Not Found
  - [ ] 403 Forbidden

### POST /crawlers/{id}/execute
**Executar crawler manualmente (run now)**

- [ ] Endpoint:
  ```python
  @router.post("/{crawler_id}/execute", response_model=CrawlerExecutionResponse)
  async def execute_crawler(
      crawler_id: str,
      current_user: User = Depends(get_current_user),
      use_case: ExecuteCrawlerJobUseCase = Depends(get_execute_crawler_job_use_case)
  ):
      execution = use_case.execute(crawler_id)
      return CrawlerExecutionResponse.from_dto(execution)
  ```
- [ ] Response schema: `CrawlerExecutionResponse`
- [ ] Error handling:
  - [ ] 400 Bad Request (crawler inativo)
  - [ ] 404 Not Found

### PATCH /crawlers/{id}/pause
**Pausar crawler (não executa mais)**

- [ ] Endpoint:
  ```python
  @router.patch("/{crawler_id}/pause", response_model=CrawlerJobResponse)
  async def pause_crawler(
      crawler_id: str,
      current_user: User = Depends(get_current_user),
      use_case: PauseCrawlerJobUseCase = Depends(get_pause_crawler_job_use_case)
  ):
      job = use_case.execute(crawler_id, current_user.id)
      return CrawlerJobResponse.from_dto(job)
  ```
- [ ] Response schema: `CrawlerJobResponse`
- [ ] Error handling: 404, 403

### PATCH /crawlers/{id}/resume
**Retomar crawler pausado**

- [ ] Endpoint:
  ```python
  @router.patch("/{crawler_id}/resume", response_model=CrawlerJobResponse)
  async def resume_crawler(
      crawler_id: str,
      current_user: User = Depends(get_current_user),
      use_case: ResumeCrawlerJobUseCase = Depends(get_resume_crawler_job_use_case)
  ):
      job = use_case.execute(crawler_id, current_user.id)
      return CrawlerJobResponse.from_dto(job)
  ```
- [ ] Response schema: `CrawlerJobResponse`

---

## 📋 Endpoints - Executions & History

### GET /crawlers/{id}/executions
**Listar execuções de um crawler**

- [ ] Endpoint:
  ```python
  @router.get("/{crawler_id}/executions", response_model=CrawlerExecutionListResponse)
  async def list_executions(
      crawler_id: str,
      status: Optional[str] = None,
      limit: int = 20,
      offset: int = 0,
      current_user: User = Depends(get_current_user),
      use_case: GetCrawlerExecutionHistoryUseCase = Depends(...)
  ):
      filters = ExecutionHistoryFilters(
          crawler_job_id=crawler_id,
          status=status,
          limit=limit,
          offset=offset
      )
      executions = use_case.execute(filters)
      return CrawlerExecutionListResponse(
          executions=[CrawlerExecutionResponse.from_dto(e) for e in executions],
          total=len(executions),
          limit=limit,
          offset=offset
      )
  ```
- [ ] Query parameters: status, limit, offset
- [ ] Response schema: `CrawlerExecutionListResponse`
- [ ] Paginação

### GET /crawlers/{id}/executions/{exec_id}
**Obter detalhes de uma execução**

- [ ] Endpoint:
  ```python
  @router.get("/{crawler_id}/executions/{execution_id}", response_model=CrawlerExecutionDetailsResponse)
  async def get_execution(
      crawler_id: str,
      execution_id: str,
      current_user: User = Depends(get_current_user),
      use_case: GetCrawlerExecutionDetailsUseCase = Depends(...)
  ):
      details = use_case.execute(execution_id, current_user.id)
      return CrawlerExecutionDetailsResponse.from_dto(details)
  ```
- [ ] Response schema: `CrawlerExecutionDetailsResponse` (com files)
- [ ] Error handling: 404, 403

### GET /crawlers/{id}/executions/{exec_id}/files
**Listar arquivos baixados em uma execução**

- [ ] Endpoint:
  ```python
  @router.get("/{crawler_id}/executions/{execution_id}/files", response_model=CrawledFileListResponse)
  async def list_execution_files(
      crawler_id: str,
      execution_id: str,
      current_user: User = Depends(get_current_user),
      crawled_file_repository: CrawledFileRepository = Depends(...)
  ):
      files = crawled_file_repository.find_by_execution_id(execution_id)
      return CrawledFileListResponse(
          files=[CrawledFileResponse.from_entity(f) for f in files]
      )
  ```
- [ ] Response schema: `CrawledFileListResponse`

### GET /crawlers/{id}/executions/{exec_id}/progress
**Progresso em tempo real de uma execução**

- [ ] Endpoint:
  ```python
  @router.get("/{crawler_id}/executions/{execution_id}/progress", response_model=CrawlerProgressResponse)
  async def get_execution_progress(
      crawler_id: str,
      execution_id: str,
      current_user: User = Depends(get_current_user),
      crawler_metrics_index: CrawlerMetricsIndex = Depends(...)
  ):
      # Buscar última métrica do Elasticsearch
      metric = crawler_metrics_index.get_real_time_progress(execution_id)
      return CrawlerProgressResponse(**metric)
  ```
- [ ] Response schema: `CrawlerProgressResponse`
- [ ] Campos: progress_percentage, pages_processed, files_processed, download_speed_bps

### POST /crawlers/{id}/executions/{exec_id}/cancel
**Cancelar execução em andamento**

- [ ] Endpoint:
  ```python
  @router.post("/{crawler_id}/executions/{execution_id}/cancel", response_model=CrawlerExecutionResponse)
  async def cancel_execution(
      crawler_id: str,
      execution_id: str,
      current_user: User = Depends(get_current_user),
      use_case: CancelCrawlerExecutionUseCase = Depends(...)
  ):
      execution = use_case.execute(execution_id, current_user.id)
      return CrawlerExecutionResponse.from_dto(execution)
  ```
- [ ] Response schema: `CrawlerExecutionResponse`
- [ ] Error handling:
  - [ ] 400 Bad Request (execução não está rodando)

---

## 📋 Endpoints - Analytics & Search

### GET /crawlers/search
**Buscar crawlers por URL/padrão (fuzzy)**

- [ ] Endpoint:
  ```python
  @router.get("/search", response_model=CrawlerJobListResponse)
  async def search_crawlers(
      query: str,
      current_user: User = Depends(get_current_user),
      crawler_job_index: CrawlerJobIndex = Depends(...)
  ):
      # Busca fuzzy no Elasticsearch
      job_ids = crawler_job_index.search_by_url_pattern(query)
      jobs = crawler_job_repository.find_by_ids(job_ids, current_user.id)
      return CrawlerJobListResponse(
          jobs=[CrawlerJobResponse.from_dto(j) for j in jobs]
      )
  ```
- [ ] Query parameter: query (URL ou padrão)
- [ ] Response schema: `CrawlerJobListResponse`

### GET /crawlers/stats
**Estatísticas gerais de crawlers do usuário**

- [ ] Endpoint:
  ```python
  @router.get("/stats", response_model=CrawlerStatsResponse)
  async def get_crawler_stats(
      current_user: User = Depends(get_current_user),
      crawler_job_repository: CrawlerJobRepository = Depends(...),
      crawler_execution_index: CrawlerExecutionIndex = Depends(...)
  ):
      # Agregações de crawlers ativos, execuções, success rate, etc.
      stats = {
          "total_crawlers": crawler_job_repository.count_by_user(current_user.id),
          "active_crawlers": crawler_job_repository.count_active(current_user.id),
          "total_executions": crawler_execution_index.count_by_user(current_user.id),
          "success_rate": crawler_execution_index.calculate_success_rate(current_user.id)
      }
      return CrawlerStatsResponse(**stats)
  ```
- [ ] Response schema: `CrawlerStatsResponse`

### GET /crawlers/{id}/stats
**Estatísticas de um crawler específico**

- [ ] Endpoint:
  ```python
  @router.get("/{crawler_id}/stats", response_model=CrawlerJobStatsResponse)
  async def get_crawler_job_stats(
      crawler_id: str,
      current_user: User = Depends(get_current_user),
      crawler_execution_index: CrawlerExecutionIndex = Depends(...)
  ):
      # Agregações de execuções deste crawler
      stats = crawler_execution_index.get_job_stats(crawler_id)
      return CrawlerJobStatsResponse(**stats)
  ```
- [ ] Response schema: `CrawlerJobStatsResponse`
- [ ] Campos: total_executions, success_rate, avg_duration, total_files_downloaded

---

## 📦 Request/Response Schemas (Pydantic)

### CreateCrawlerJobRequest
- [ ] Criar `backend/presentation/schemas/create_crawler_job_request.py`
- [ ] Campos (Pydantic BaseModel):
  ```python
  class CreateCrawlerJobRequest(BaseModel):
      name: str = Field(..., min_length=1, max_length=255)
      url: HttpUrl
      crawler_engine: CrawlerEngineEnum = CrawlerEngineEnum.BEAUTIFULSOUP
      use_proxy: bool = False
      proxy_config: Optional[ProxyConfigSchema] = None
      crawl_type: CrawlTypeEnum
      max_depth: int = Field(default=1, ge=1, le=10)
      follow_external_links: bool = False
      download_assets: bool = False
      asset_types: List[AssetTypeEnum] = []
      file_extensions: List[str] = []
      extension_categories: List[str] = []
      pdf_handling: PDFHandlingEnum = PDFHandlingEnum.INDIVIDUAL
      retry_enabled: bool = True
      max_retries: int = Field(default=3, ge=0, le=10)
      retry_strategy: Optional[List[RetryStrategyAttempt]] = None
      schedule_type: ScheduleTypeEnum
      schedule_frequency: Optional[ScheduleFrequencyEnum] = None
      cron_expression: Optional[str] = None
      timezone: str = "UTC"
  ```
- [ ] Validações:
  - [ ] cron_expression obrigatório se schedule_frequency == CUSTOM
  - [ ] asset_types válidos
  - [ ] proxy_config obrigatório se use_proxy == True

### UpdateCrawlerJobRequest
- [ ] Criar `backend/presentation/schemas/update_crawler_job_request.py`
- [ ] Todos os campos opcionais (allow partial updates)

### CrawlerJobResponse
- [ ] Criar `backend/presentation/schemas/crawler_job_response.py`
- [ ] Campos (espelhar DTO):
  ```python
  class CrawlerJobResponse(BaseModel):
      id: str
      user_id: str
      name: str
      url: str
      crawler_engine: CrawlerEngineEnum
      use_proxy: bool
      proxy_config: Optional[ProxyConfigSchema]
      crawl_type: CrawlTypeEnum
      # ... todos os campos
      next_run_at: Optional[datetime]
      is_active: bool
      status: CrawlerJobStatusEnum
      total_executions: int
      successful_executions: int
      failed_executions: int
      last_execution_at: Optional[datetime]
      created_at: datetime
      updated_at: datetime

      # Warnings (duplicatas)
      warnings: Optional[List[CrawlerWarning]] = []

      class Config:
          from_attributes = True
  ```
- [ ] Método `from_dto(dto: CrawlerJobDTO) -> CrawlerJobResponse`

### CrawlerExecutionResponse
- [ ] Criar `backend/presentation/schemas/crawler_execution_response.py`
- [ ] Campos:
  ```python
  class CrawlerExecutionResponse(BaseModel):
      id: str
      crawler_job_id: str
      celery_task_id: Optional[str]
      status: ExecutionStatusEnum
      progress: int
      pages_discovered: int
      pages_downloaded: int
      pages_failed: int
      files_downloaded: int
      files_failed: int
      total_size_bytes: int
      files_by_type: Dict[str, int]
      minio_folder_path: Optional[str]
      error_message: Optional[str]
      error_count: int
      retry_count: int
      current_retry_attempt: int
      retry_history: Optional[List[RetryHistoryEntry]]
      engine_used: Optional[CrawlerEngineEnum]
      proxy_used: Optional[bool]
      started_at: Optional[datetime]
      completed_at: Optional[datetime]
      created_at: datetime
      updated_at: datetime
  ```
- [ ] Método `from_dto(dto: CrawlerExecutionDTO) -> CrawlerExecutionResponse`

### CrawledFileResponse
- [ ] Criar `backend/presentation/schemas/crawled_file_response.py`
- [ ] Campos: id, execution_id, url, filename, file_type, size_bytes, public_url, status, downloaded_at

### Enums
- [ ] Criar `backend/presentation/schemas/enums.py`:
  ```python
  from enum import Enum

  class CrawlerEngineEnum(str, Enum):
      BEAUTIFULSOUP = "BEAUTIFULSOUP"
      PLAYWRIGHT = "PLAYWRIGHT"

  class CrawlTypeEnum(str, Enum):
      PAGE_ONLY = "PAGE_ONLY"
      PAGE_WITH_ALL = "PAGE_WITH_ALL"
      PAGE_WITH_FILTERED = "PAGE_WITH_FILTERED"
      FULL_WEBSITE = "FULL_WEBSITE"

  class AssetTypeEnum(str, Enum):
      CSS = "css"
      JS = "js"
      IMAGES = "images"
      FONTS = "fonts"
      VIDEOS = "videos"
      DOCUMENTS = "documents"

  class PDFHandlingEnum(str, Enum):
      INDIVIDUAL = "INDIVIDUAL"
      COMBINED = "COMBINED"
      BOTH = "BOTH"

  class ScheduleTypeEnum(str, Enum):
      ONE_TIME = "ONE_TIME"
      RECURRING = "RECURRING"

  class ScheduleFrequencyEnum(str, Enum):
      HOURLY = "HOURLY"
      DAILY = "DAILY"
      WEEKLY = "WEEKLY"
      MONTHLY = "MONTHLY"
      CUSTOM = "CUSTOM"

  class CrawlerJobStatusEnum(str, Enum):
      ACTIVE = "ACTIVE"
      PAUSED = "PAUSED"
      STOPPED = "STOPPED"
      ERROR = "ERROR"

  class ExecutionStatusEnum(str, Enum):
      PENDING = "PENDING"
      PROCESSING = "PROCESSING"
      COMPLETED = "COMPLETED"
      FAILED = "FAILED"
      CANCELLED = "CANCELLED"
  ```

---

## 🔐 Authentication & Authorization

### JWT/API Key
- [ ] Usar autenticação existente (JWT + API Key)
- [ ] Criar dependency `get_current_user`:
  ```python
  from backend.shared.auth import get_current_user_from_token

  async def get_current_user(
      token: str = Depends(oauth2_scheme)
  ) -> User:
      user = get_current_user_from_token(token)
      if not user:
          raise HTTPException(status_code=401, detail="Unauthorized")
      return user
  ```
- [ ] Aplicar em todos os endpoints via `Depends(get_current_user)`

### Permission Checks
- [ ] Verificar user_id em todos os endpoints:
  - [ ] GET /crawlers → filtrar por user_id
  - [ ] PATCH /crawlers/{id} → validar job.user_id == current_user.id
  - [ ] DELETE /crawlers/{id} → validar job.user_id == current_user.id

---

## 🛠️ Dependency Injection (FastAPI)

### Providers
- [ ] Criar `backend/presentation/dependencies.py`:
  ```python
  from fastapi import Depends
  from backend.application.container import Container

  container = Container()

  def get_create_crawler_job_use_case() -> CreateCrawlerJobUseCase:
      return container.create_crawler_job_use_case()

  def get_list_crawler_jobs_use_case() -> ListCrawlerJobsUseCase:
      return container.list_crawler_jobs_use_case()

  # ... outros use cases
  ```
- [ ] Injetar via `Depends()` nos endpoints

---

## 📄 OpenAPI Documentation

### Swagger UI
- [ ] Configurar tags em router:
  ```python
  router = APIRouter(prefix="/crawlers", tags=["Crawlers"])
  ```
- [ ] Adicionar descrições nos endpoints:
  ```python
  @router.post(
      "/",
      response_model=CrawlerJobResponse,
      status_code=status.HTTP_201_CREATED,
      summary="Create new crawler",
      description="Create a new scheduled crawler job with configurable options",
      responses={
          201: {"description": "Crawler created successfully"},
          400: {"description": "Invalid request"},
          401: {"description": "Unauthorized"},
          409: {"description": "Duplicate crawler detected (warning)"}
      }
  )
  ```
- [ ] Adicionar exemplos nos schemas:
  ```python
  class CreateCrawlerJobRequest(BaseModel):
      name: str = Field(..., example="Crawl Example.com PDFs")
      url: HttpUrl = Field(..., example="https://example.com/docs")
      # ...

      class Config:
          schema_extra = {
              "example": {
                  "name": "Crawl Example.com PDFs",
                  "url": "https://example.com/docs",
                  "crawl_type": "PAGE_WITH_FILTERED",
                  "file_extensions": ["pdf"],
                  "pdf_handling": "BOTH",
                  "schedule_type": "RECURRING",
                  "schedule_frequency": "DAILY",
                  "cron_expression": "0 9 * * *",
                  "timezone": "America/Sao_Paulo"
              }
          }
  ```
- [ ] Verificar Swagger UI em http://localhost:8000/docs

---

## 🧪 Error Handling

### Exception Handlers
- [ ] Criar `backend/presentation/exception_handlers.py`:
  ```python
  from fastapi import Request, status
  from fastapi.responses import JSONResponse
  from backend.application.exceptions import *

  async def not_found_exception_handler(request: Request, exc: NotFoundException):
      return JSONResponse(
          status_code=status.HTTP_404_NOT_FOUND,
          content={"detail": str(exc)}
      )

  async def unauthorized_exception_handler(request: Request, exc: UnauthorizedException):
      return JSONResponse(
          status_code=status.HTTP_403_FORBIDDEN,
          content={"detail": str(exc)}
      )

  async def validation_exception_handler(request: Request, exc: ValidationException):
      return JSONResponse(
          status_code=status.HTTP_400_BAD_REQUEST,
          content={"detail": str(exc)}
      )
  ```
- [ ] Registrar no FastAPI app:
  ```python
  app.add_exception_handler(NotFoundException, not_found_exception_handler)
  app.add_exception_handler(UnauthorizedException, unauthorized_exception_handler)
  app.add_exception_handler(ValidationException, validation_exception_handler)
  ```

### Standard Error Response
- [ ] Criar `backend/presentation/schemas/error_response.py`:
  ```python
  class ErrorResponse(BaseModel):
      detail: str
      error_code: Optional[str] = None
      timestamp: datetime = Field(default_factory=datetime.utcnow)
  ```

---

## ✅ API Tests

### Endpoint Tests
- [ ] Criar `backend/tests/presentation/test_crawler_controller.py`
  - [ ] Setup: TestClient (FastAPI)
  - [ ] Teste POST /crawlers:
    - [ ] Teste criação bem-sucedida (201)
    - [ ] Teste validação URL inválida (400)
    - [ ] Teste cron inválido (400)
    - [ ] Teste sem autenticação (401)
  - [ ] Teste GET /crawlers:
    - [ ] Teste listagem (200)
    - [ ] Teste paginação
    - [ ] Teste filtros (status, search)
  - [ ] Teste GET /crawlers/{id}:
    - [ ] Teste obter existente (200)
    - [ ] Teste não encontrado (404)
    - [ ] Teste outro usuário (403)
  - [ ] Teste PATCH /crawlers/{id}:
    - [ ] Teste atualização (200)
    - [ ] Teste permissões (403)
  - [ ] Teste DELETE /crawlers/{id}:
    - [ ] Teste deleção (204)
  - [ ] Teste POST /crawlers/{id}/execute:
    - [ ] Teste execução (200)
    - [ ] Teste crawler inativo (400)
  - [ ] Teste PATCH /crawlers/{id}/pause:
    - [ ] Teste pausar (200)
  - [ ] Teste GET /crawlers/{id}/executions:
    - [ ] Teste listagem de execuções (200)
  - [ ] Teste GET /crawlers/{id}/executions/{exec_id}:
    - [ ] Teste detalhes de execução (200)

### Integration Tests
- [ ] Criar `backend/tests/integration/test_crawler_api_flow.py`
  - [ ] Teste fluxo completo via API:
    - [ ] POST /crawlers (criar)
    - [ ] POST /crawlers/{id}/execute (executar)
    - [ ] GET /crawlers/{id}/executions/{exec_id}/progress (monitorar)
    - [ ] GET /crawlers/{id}/executions/{exec_id}/files (obter arquivos)
    - [ ] Verificar arquivos no MinIO

### Coverage
- [ ] Coverage >= 85% na presentation layer
- [ ] Rodar: `pytest backend/tests/presentation/ -v --cov=backend/presentation`

---

## 📋 API Documentation

### README da API
- [ ] Criar `docs/crawler/API.md`:
  - [ ] Visão geral dos endpoints
  - [ ] Autenticação (JWT/API Key)
  - [ ] Exemplos de requisições (curl, httpx)
  - [ ] Códigos de erro
  - [ ] Rate limiting (se aplicável)

### Postman Collection
- [ ] Criar collection do Postman:
  - [ ] Todos os endpoints
  - [ ] Exemplos de requests/responses
  - [ ] Variáveis de ambiente
  - [ ] Exportar JSON

---

## 🎯 Entregável Sprint 5

- [ ] ✅ Todos os endpoints implementados:
  - [ ] Crawler Management (7 endpoints)
  - [ ] Executions & History (5 endpoints)
  - [ ] Analytics & Search (3 endpoints)
- [ ] ✅ Request/Response schemas (Pydantic)
- [ ] ✅ Autenticação (JWT/API Key)
- [ ] ✅ Autorização (permission checks)
- [ ] ✅ Dependency injection configurado
- [ ] ✅ OpenAPI/Swagger documentation
- [ ] ✅ Error handling completo
- [ ] ✅ Coverage >= 85% de testes de API
- [ ] ✅ Documentação da API (API.md + Postman)
- [ ] ✅ Todos os endpoints testados (unit + integration)

---

## 📚 Referências

- [CRAWLER_INTEGRATION_PLAN.md](./CRAWLER_INTEGRATION_PLAN.md) - Seção 8 (API Endpoints)
- [backend/presentation/routes.py](../../backend/presentation/routes.py) - Exemplo de endpoints existentes
- FastAPI docs: https://fastapi.tiangolo.com/
- Pydantic docs: https://docs.pydantic.dev/
