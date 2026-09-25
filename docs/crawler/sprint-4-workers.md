# Sprint 4: Workers Celery
**Duração:** Semanas 7-8
**Objetivo:** Execução de crawls com Celery

---

## 🚀 Celery Tasks

### Task: execute_crawler
- [ ] Criar `backend/workers/crawler_tasks.py`
- [ ] Definir task `execute_crawler`:
  ```python
  @celery_app.task(
      name='workers.crawler_tasks.execute_crawler',
      bind=True,
      max_retries=0,  # Retry controlado manualmente
      time_limit=3600,  # 1 hora
      soft_time_limit=3300  # 55 minutos
  )
  def execute_crawler(self, crawler_job_id: str, execution_id: str):
      # Orquestração do crawl
  ```
- [ ] Fluxo da task:
  1. [ ] **Buscar CrawlerJob e CrawlerExecution** no MySQL
  2. [ ] **Atualizar status** para PROCESSING
  3. [ ] **Instanciar CrawlerScraper**
  4. [ ] **Executar crawl completo** (ver seção CrawlerScraper)
  5. [ ] **Tratar erros** e retry (ver seção RetryManager)
  6. [ ] **Atualizar estatísticas** do crawler_job
  7. [ ] **Indexar métricas** no Elasticsearch
  8. [ ] **Cleanup** arquivos temporários
- [ ] Error handling:
  - [ ] Try/catch global
  - [ ] Logar erro estruturado (JSON)
  - [ ] Atualizar execution.status = FAILED
  - [ ] Salvar error_message
- [ ] Fila: `crawler` (isolada)

### Task: schedule_crawler
- [ ] Definir task `schedule_crawler`:
  ```python
  @celery_app.task(name='workers.crawler_tasks.schedule_crawler')
  def schedule_crawler(crawler_job_id: str):
      # Triggered by Celery Beat
  ```
- [ ] Fluxo da task:
  1. [ ] **Buscar CrawlerJob** no MySQL
  2. [ ] **Verificar is_active** == True
  3. [ ] **Criar nova CrawlerExecution** (status=PENDING)
  4. [ ] **Salvar no MySQL**
  5. [ ] **Disparar execute_crawler.apply_async()**
  6. [ ] **Atualizar next_run_at** do crawler_job
- [ ] Fila: `beat` (Celery Beat)

---

## 🛠️ Worker Logic

### CrawlerScraper (Orquestrador)
- [ ] Criar `backend/workers/crawler_scraper.py`
- [ ] Classe `CrawlerScraper`:
  ```python
  class CrawlerScraper:
      def __init__(
          self,
          crawler_job: CrawlerJob,
          execution: CrawlerExecution,
          crawler_adapter: CrawlerAdapter,
          file_downloader: FileDownloader,
          pdf_processor: PDFProcessor,
          progress_tracker: ProgressTracker,
          minio_storage: MinioCrawlerStorageAdapter,
          retry_manager: RetryManager
      ):
          ...
  ```
- [ ] Método `run()` - Orquestração completa do crawl:
  1. [ ] **[0-10%] Crawl página principal**:
     - [ ] `links = crawler_adapter.crawl_page(url, file_extensions)`
     - [ ] `asset_urls = crawler_adapter.extract_assets(html, asset_types)` (se download_assets=True)
     - [ ] Atualizar progress (10%)
     - [ ] Salvar HTML no MinIO (opcional)
  2. [ ] **[10-20%] Filtrar links por extensão**:
     - [ ] Filtrar por file_extensions config
     - [ ] Filtrar por extension_categories
     - [ ] Remover duplicatas
     - [ ] Atualizar execution.pages_discovered
  3. [ ] **[20-70%] Download arquivos em paralelo**:
     - [ ] `file_downloader.download_all(links, temp_folder)`
     - [ ] Para cada arquivo:
       - [ ] Registrar CrawledFile no MySQL
       - [ ] Atualizar progress
       - [ ] Indexar métricas no Elasticsearch (bulk a cada 5s)
  4. [ ] **[70-80%] Download assets** (se download_assets=True):
     - [ ] `file_downloader.download_assets(asset_urls, temp_folder)`
     - [ ] Organizar por tipo (css/, js/, images/, etc.)
  5. [ ] **[80-90%] Processar PDFs** (se pdf_handling != INDIVIDUAL):
     - [ ] `pdf_processor.merge_pdfs(pdf_files, output_path)`
     - [ ] Adicionar bookmarks
  6. [ ] **[90-100%] Upload para MinIO**:
     - [ ] Para cada arquivo em /tmp:
       - [ ] `minio_storage.upload_crawled_file(execution_id, filename, file_path)`
       - [ ] Gerar public_url
       - [ ] Atualizar CrawledFile.public_url no MySQL
     - [ ] Upload merged PDF (se existir)
     - [ ] Upload assets por tipo
  7. [ ] **[100%] Finalizar**:
     - [ ] execution.status = COMPLETED
     - [ ] execution.completed_at = now()
     - [ ] crawler_job.total_executions += 1
     - [ ] crawler_job.successful_executions += 1
     - [ ] Commit MySQL
     - [ ] Indexar execução completa no Elasticsearch
     - [ ] Cleanup /tmp
- [ ] Método `_select_crawler_adapter()`:
  - [ ] Retornar BeautifulSoupCrawlerAdapter ou PlaywrightCrawlerAdapter
  - [ ] Baseado em crawler_engine e retry_attempt
- [ ] Integrar com RetryManager para fallback de engines
- [ ] Testes end-to-end

### RetryManager (Gerenciamento de Retries)
- [ ] Criar `backend/workers/retry_manager.py`
- [ ] Classe `RetryManager`:
  ```python
  class RetryManager:
      def __init__(
          self,
          crawler_job: CrawlerJob,
          execution: CrawlerExecution,
          crawler_execution_repository: CrawlerExecutionRepository
      ):
          self.retry_strategy = crawler_job.retry_strategy
          self.max_retries = crawler_job.max_retries
          ...
  ```
- [ ] Método `execute_with_retry(crawl_fn)`:
  - [ ] Iterar por retry_strategy (lista de tentativas)
  - [ ] Para cada attempt:
    1. [ ] **Aguardar delay** (backoff exponencial):
       - [ ] `sleep(attempt['delay_seconds'])`
    2. [ ] **Atualizar execution.current_retry_attempt**
    3. [ ] **Selecionar engine e proxy**:
       - [ ] `engine = attempt['engine']`
       - [ ] `use_proxy = attempt['use_proxy']`
    4. [ ] **Executar crawl**:
       - [ ] `result = crawl_fn(engine, use_proxy)`
    5. [ ] **Se sucesso**:
       - [ ] `execution.engine_used = engine`
       - [ ] `execution.proxy_used = use_proxy`
       - [ ] `execution.status = COMPLETED`
       - [ ] Registrar tentativa no retry_history (SUCCESS)
       - [ ] `return result`
    6. [ ] **Se falha**:
       - [ ] Registrar tentativa no retry_history (FAILED)
       - [ ] `execution.retry_count += 1`
       - [ ] Se última tentativa: raise erro
       - [ ] Continuar para próxima tentativa
  - [ ] Se todas as tentativas falharem:
    - [ ] `execution.status = FAILED`
    - [ ] `execution.error_message = "All retries exhausted"`
    - [ ] Salvar no MySQL
    - [ ] `raise AllRetriesExhaustedError`
- [ ] Método `_log_retry_attempt(attempt_num, status, error=None)`:
  - [ ] Adicionar entrada no retry_history:
    ```json
    {
      "attempt": 0,
      "engine": "BEAUTIFULSOUP",
      "use_proxy": false,
      "started_at": "...",
      "completed_at": "...",
      "status": "FAILED",
      "error_type": "TIMEOUT",
      "error_message": "...",
      "duration_seconds": 5
    }
    ```
  - [ ] Atualizar execution.retry_history no MySQL
- [ ] Testes unitários

### FileDownloader (Download Paralelo)
- [ ] Criar `backend/workers/file_downloader.py`
- [ ] Classe `FileDownloader`:
  ```python
  class FileDownloader:
      def __init__(
          self,
          max_concurrent_downloads: int = 5,
          download_timeout_seconds: int = 60,
          user_agent: str = "IngestifyBot/1.0"
      ):
          self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
          self.client = httpx.AsyncClient(timeout=download_timeout_seconds)
          ...
  ```
- [ ] Método `download_all(urls: List[str], destination_folder: str)`:
  - [ ] `asyncio.gather(*[self._download_file(url, folder) for url in urls])`
  - [ ] Download assíncrono de todos os arquivos
  - [ ] Retornar lista de (url, filepath, success, error)
- [ ] Método `_download_file(url, destination)`:
  - [ ] `async with self.semaphore:` (limitar concorrência)
  - [ ] Retry automático (3 tentativas):
    ```python
    for attempt in range(3):
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            filepath = os.path.join(destination, filename)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            return (url, filepath, True, None)
        except Exception as e:
            if attempt == 2:
                return (url, None, False, str(e))
            await asyncio.sleep(2 ** attempt)  # Backoff exponencial
    ```
  - [ ] Progress tracking (bytes downloaded)
  - [ ] Error handling
- [ ] Método `download_assets(asset_urls: Dict[str, List[str]], destination_folder: str)`:
  - [ ] Organizar por tipo (css/, js/, images/, etc.)
  - [ ] Download paralelo por tipo
  - [ ] Retornar estatísticas: `{"css": 5, "js": 12, "images": 34}`
- [ ] Método `close()`:
  - [ ] `await self.client.aclose()`
- [ ] Testes unitários (com mock httpx)

### PDFProcessor (Merge de PDFs)
- [ ] Criar `backend/workers/pdf_processor.py`
- [ ] Classe `PDFProcessor`:
  ```python
  class PDFProcessor:
      def __init__(self, pdf_merger_adapter: PyPDFMergerAdapter):
          self.merger = pdf_merger_adapter
  ```
- [ ] Método `process_pdfs(pdf_files: List[str], pdf_handling: str, output_folder: str)`:
  - [ ] Se pdf_handling == INDIVIDUAL:
    - [ ] Retornar lista de PDFs sem merge
  - [ ] Se pdf_handling == COMBINED:
    - [ ] `merged_path = self.merger.merge_pdfs(pdf_files, output_folder)`
    - [ ] Retornar [merged_path]
  - [ ] Se pdf_handling == BOTH:
    - [ ] `merged_path = self.merger.merge_pdfs(pdf_files, output_folder)`
    - [ ] Retornar pdf_files + [merged_path]
- [ ] Método `validate_pdfs(pdf_files: List[str])`:
  - [ ] Para cada PDF:
    - [ ] `self.merger.validate_pdf(pdf_file)`
    - [ ] Se inválido: logar warning e skip
  - [ ] Retornar lista de PDFs válidos
- [ ] Testes unitários

### ProgressTracker (Rastreamento de Progresso)
- [ ] Criar `backend/workers/progress_tracker.py`
- [ ] Classe `ProgressTracker`:
  ```python
  class ProgressTracker:
      def __init__(
          self,
          execution: CrawlerExecution,
          crawler_execution_repository: CrawlerExecutionRepository,
          crawler_metrics_index: CrawlerMetricsIndex
      ):
          self.execution = execution
          self.repo = crawler_execution_repository
          self.metrics_index = crawler_metrics_index
          self.metrics_buffer = []  # Bulk indexing
          self.last_flush = time.time()
  ```
- [ ] Método `update_progress(percentage: int, **kwargs)`:
  - [ ] Atualizar execution.progress
  - [ ] Atualizar outros campos (pages_downloaded, files_downloaded, etc.)
  - [ ] Salvar no MySQL (debounce: máximo a cada 5s)
  - [ ] Indexar métrica no Elasticsearch (bulk)
- [ ] Método `_index_metric(**data)`:
  - [ ] Adicionar ao buffer:
    ```python
    self.metrics_buffer.append({
        "execution_id": self.execution.id,
        "timestamp": datetime.utcnow(),
        "progress_percentage": self.execution.progress,
        "pages_processed": self.execution.pages_downloaded,
        ...
    })
    ```
  - [ ] Se buffer >= 100 docs OU elapsed > 5s:
    - [ ] `self._flush_metrics()`
- [ ] Método `_flush_metrics()`:
  - [ ] `self.metrics_index.bulk_index_metrics(self.metrics_buffer)`
  - [ ] `self.metrics_buffer.clear()`
  - [ ] `self.last_flush = time.time()`
- [ ] Método `finalize()`:
  - [ ] Flush remaining metrics
  - [ ] Indexar execução completa no Elasticsearch
- [ ] Testes unitários

---

## 📊 Celery Beat Integration

### Dynamic Schedule Registration
- [ ] Criar `backend/workers/crawler_scheduler.py`
- [ ] Função `register_crawler_schedule(crawler_job: CrawlerJob)`:
  - [ ] Adicionar ao beat_schedule:
    ```python
    from celery.schedules import crontab
    from croniter import croniter

    celery_app.conf.beat_schedule[f'crawler-{crawler_job.id}'] = {
        'task': 'workers.crawler_tasks.schedule_crawler',
        'schedule': crontab(...),  # Parse from crawler_job.cron_expression
        'args': (crawler_job.id,),
        'options': {
            'expires': 3600,  # Task expires after 1h if not picked up
        }
    }
    ```
  - [ ] Persist beat schedule (Celery Beat Scheduler)
- [ ] Função `unregister_crawler_schedule(crawler_job_id: str)`:
  - [ ] `del celery_app.conf.beat_schedule[f'crawler-{crawler_job_id}']`
- [ ] Função `update_crawler_schedule(crawler_job: CrawlerJob)`:
  - [ ] Unregister + register
- [ ] Função `load_all_active_crawlers()`:
  - [ ] Buscar todos os crawlers ativos no MySQL
  - [ ] Registrar no beat_schedule
  - [ ] Chamar no startup do worker
- [ ] Integrar com CreateCrawlerJobUseCase, UpdateCrawlerJobUseCase, PauseCrawlerJobUseCase

### Celery Beat Startup
- [ ] Atualizar `backend/workers/celery_app.py`:
  - [ ] Adicionar startup script:
    ```python
    @celery_app.on_after_configure.connect
    def setup_crawler_schedules(sender, **kwargs):
        from workers.crawler_scheduler import load_all_active_crawlers
        load_all_active_crawlers()
    ```

---

## 🔧 Worker Configuration

### Celery App Updates
- [ ] Atualizar `backend/workers/celery_app.py`:
  - [ ] Adicionar fila `crawler`:
    ```python
    task_routes = {
        'workers.crawler_tasks.execute_crawler': {'queue': 'crawler'},
        'workers.crawler_tasks.schedule_crawler': {'queue': 'beat'},
    }
    ```
  - [ ] Configurar workers dedicados:
    ```bash
    # Worker for crawler tasks
    celery -A workers.celery_app worker -Q crawler -n crawler@%h

    # Worker for beat tasks
    celery -A workers.celery_app worker -Q beat -n beat@%h

    # Beat scheduler
    celery -A workers.celery_app beat
    ```

### Docker Compose
- [ ] Atualizar `docker-compose.yml`:
  - [ ] Adicionar serviço `crawler-worker`:
    ```yaml
    crawler-worker:
      build:
        context: .
        dockerfile: docker/Dockerfile.worker
      command: celery -A workers.celery_app worker -Q crawler -n crawler@%h --concurrency=2
      depends_on:
        - redis
        - mysql
      environment:
        - CELERY_BROKER_URL=redis://redis:6379/0
        - DATABASE_URL=mysql+pymysql://root:root@mysql/ingestify
    ```
  - [ ] Adicionar serviço `beat-scheduler`:
    ```yaml
    beat:
      build:
        context: .
        dockerfile: docker/Dockerfile.worker
      command: celery -A workers.celery_app beat
      depends_on:
        - redis
        - mysql
    ```
  - [ ] Escalar crawler-worker: `docker compose up -d --scale crawler-worker=3`

---

## ✅ Testes End-to-End

### Worker Tests
- [ ] Criar `backend/tests/workers/test_execute_crawler_task.py`
  - [ ] Setup: criar job e execution no MySQL
  - [ ] Teste execução completa (HTML only):
    - [ ] Mock BeautifulSoupCrawlerAdapter
    - [ ] Verificar download de arquivos
    - [ ] Verificar upload para MinIO
    - [ ] Verificar atualização de status
  - [ ] Teste com assets:
    - [ ] Verificar download de CSS, JS, images
    - [ ] Verificar organização em subpastas
  - [ ] Teste com retry:
    - [ ] Mock falhas
    - [ ] Verificar fallback de engines
    - [ ] Verificar retry_history
  - [ ] Teste com merge de PDFs:
    - [ ] Verificar merged PDF no MinIO
  - [ ] Teste timeout:
    - [ ] Verificar soft_time_limit
  - [ ] Teardown: limpar database e MinIO

- [ ] Criar `backend/tests/workers/test_schedule_crawler_task.py`
  - [ ] Teste agendamento
  - [ ] Verificar criação de execution
  - [ ] Verificar dispatch de execute_crawler

- [ ] Criar `backend/tests/workers/test_crawler_scraper.py`
  - [ ] Teste orquestração completa
  - [ ] Mock todos os adapters
  - [ ] Verificar progresso (0-100%)

- [ ] Criar `backend/tests/workers/test_retry_manager.py`
  - [ ] Teste retry estratégias (conservative, aggressive, etc.)
  - [ ] Verificar backoff exponencial
  - [ ] Verificar retry_history

- [ ] Criar `backend/tests/workers/test_file_downloader.py`
  - [ ] Mock httpx
  - [ ] Teste download paralelo
  - [ ] Teste retry automático
  - [ ] Teste concorrência (semaphore)

### Integration Tests
- [ ] Criar `backend/tests/integration/test_crawler_full_flow.py`
  - [ ] Teste fluxo completo (CreateCrawlerJob → Execute → MinIO):
    - [ ] Criar crawler via use case
    - [ ] Executar crawler via use case
    - [ ] Aguardar conclusão
    - [ ] Verificar arquivos no MinIO
    - [ ] Verificar dados no MySQL
    - [ ] Verificar métricas no Elasticsearch

### Coverage
- [ ] Coverage >= 80% nos workers
- [ ] Rodar: `pytest backend/tests/workers/ -v --cov=backend/workers`

---

## 🎯 Entregável Sprint 4

- [ ] ✅ Tasks Celery implementadas:
  - [ ] execute_crawler
  - [ ] schedule_crawler
- [ ] ✅ Worker logic implementada:
  - [ ] CrawlerScraper (orquestração completa)
  - [ ] RetryManager (fallback de engines)
  - [ ] FileDownloader (download paralelo)
  - [ ] PDFProcessor (merge de PDFs)
  - [ ] ProgressTracker (rastreamento tempo real)
- [ ] ✅ Celery Beat integration:
  - [ ] Dynamic schedule registration
  - [ ] Startup script para carregar crawlers ativos
- [ ] ✅ Filas dedicadas (`crawler`, `beat`)
- [ ] ✅ Docker Compose atualizado (crawler-worker, beat)
- [ ] ✅ Testes end-to-end funcionando
- [ ] ✅ Crawls executando com sucesso (HTML + assets + PDFs)
- [ ] ✅ Retry inteligente funcionando (fallback de engines)
- [ ] ✅ Progresso rastreado em tempo real
- [ ] ✅ Documentação atualizada (workers layer)

---

## 📚 Referências

- [CRAWLER_INTEGRATION_PLAN.md](./CRAWLER_INTEGRATION_PLAN.md) - Seção 7 (Workers Layer)
- [backend/workers/tasks.py](../../backend/workers/tasks.py) - Exemplo de tasks existentes
- Celery docs: https://docs.celeryq.dev/
- Celery Beat docs: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
