# Sprint 2: Infrastructure & Repositories
**Duração:** Semanas 3-4
**Objetivo:** Camada de infraestrutura completa

---

## 🗄️ MySQL Repositories

### MySQLCrawlerJobRepository
- [ ] Criar `backend/infrastructure/repositories/mysql_crawler_job_repository.py`
- [ ] Implementar interface `CrawlerJobRepository`
- [ ] Método `save(crawler_job)`:
  - [ ] Criar novo registro ou atualizar existente
  - [ ] Usar SQLAlchemy ORM
  - [ ] Tratar exceções (IntegrityError, etc.)
- [ ] Método `find_by_id(id)`:
  - [ ] Retornar CrawlerJob entity ou None
  - [ ] Converter de model SQLAlchemy para entity
- [ ] Método `find_by_user_id(user_id)`:
  - [ ] Filtrar por user_id
  - [ ] Suporte a paginação (limit, offset)
  - [ ] Ordenar por created_at DESC
- [ ] Método `find_by_url_pattern(pattern)`:
  - [ ] Buscar por url_pattern (fuzzy)
  - [ ] LIKE query
- [ ] Método `find_active()`:
  - [ ] Filtrar is_active=True
  - [ ] Para Celery Beat scheduler
- [ ] Método `delete(id)`:
  - [ ] Soft delete (opcional) ou hard delete
  - [ ] Cascade para executions e files
- [ ] Testes de integração com MySQL

### MySQLCrawlerExecutionRepository
- [ ] Criar `backend/infrastructure/repositories/mysql_crawler_execution_repository.py`
- [ ] Implementar interface `CrawlerExecutionRepository`
- [ ] Método `save(execution)`:
  - [ ] Criar novo registro
  - [ ] Gerar UUID se não existir
- [ ] Método `update(execution)`:
  - [ ] Atualizar campos (progress, status, etc.)
  - [ ] Otimização: update apenas campos modificados
- [ ] Método `find_by_id(id)`:
  - [ ] Retornar CrawlerExecution entity ou None
  - [ ] Eager loading de relacionamentos (crawled_files)
- [ ] Método `find_by_crawler_job_id(job_id)`:
  - [ ] Filtrar por crawler_job_id
  - [ ] Ordenar por started_at DESC
  - [ ] Paginação
- [ ] Método `find_running()`:
  - [ ] Filtrar status IN (PENDING, PROCESSING)
  - [ ] Para monitoramento
- [ ] Testes de integração

### MySQLCrawledFileRepository
- [ ] Criar `backend/infrastructure/repositories/mysql_crawled_file_repository.py`
- [ ] Implementar interface `CrawledFileRepository`
- [ ] Método `save(file)`:
  - [ ] Criar novo registro
  - [ ] Gerar UUID
- [ ] Método `find_by_execution_id(execution_id)`:
  - [ ] Filtrar por execution_id
  - [ ] Ordenar por downloaded_at
- [ ] Método `count_by_type(execution_id)`:
  - [ ] Agregação: GROUP BY file_type
  - [ ] Retornar dict {"pdf": 10, "xlsx": 5}
- [ ] Testes de integração

---

## 🔍 Elasticsearch Adapters

### CrawlerJobIndex
- [ ] Criar `backend/infrastructure/elasticsearch/crawler_job_index.py`
- [ ] Método `index_crawler_job(job)`:
  - [ ] Serializar CrawlerJob entity para JSON
  - [ ] Indexar no Elasticsearch
  - [ ] Index name: `crawler-jobs-{timestamp}`
  - [ ] Document ID: job.id
- [ ] Método `update_crawler_job(job)`:
  - [ ] Update doc parcial
  - [ ] Campos: status, is_active, total_executions, etc.
- [ ] Método `search_by_url_pattern(pattern)`:
  - [ ] Query com fuzzy matching
  - [ ] Match em campo `url_pattern`
  - [ ] Fuzziness: AUTO
  - [ ] Retornar lista de job IDs
- [ ] Método `find_active_jobs()`:
  - [ ] Term query: is_active=true
  - [ ] Agregações: count por status
- [ ] Método `delete_job(job_id)`:
  - [ ] Delete documento
- [ ] Testes de integração com Elasticsearch

### CrawlerExecutionIndex
- [ ] Criar `backend/infrastructure/elasticsearch/crawler_execution_index.py`
- [ ] Método `index_execution(execution)`:
  - [ ] Serializar CrawlerExecution para JSON
  - [ ] Index: `crawler-executions-{YYYY.MM.DD}`
  - [ ] Time-series index
  - [ ] Calcular `duration_seconds`, `average_download_speed_mbps`
- [ ] Método `search_executions(filters)`:
  - [ ] Filtros: status, crawler_job_id, date_range
  - [ ] Ordenação por started_at
  - [ ] Agregações: count por status, avg duration
- [ ] Método `get_execution_stats(execution_id)`:
  - [ ] Retornar métricas de uma execução
- [ ] Testes de integração

### CrawlerMetricsIndex
- [ ] Criar `backend/infrastructure/elasticsearch/crawler_metrics_index.py`
- [ ] Método `bulk_index_metrics(metrics)`:
  - [ ] Bulk insert de métricas
  - [ ] Index: `crawler-metrics-{YYYY.MM.DD}`
  - [ ] Batch size: 100 docs
  - [ ] Refresh: 5s
- [ ] Método `get_real_time_progress(execution_id)`:
  - [ ] Query: term execution_id + sort by timestamp DESC
  - [ ] Limit 1 (última métrica)
  - [ ] Retornar progress_percentage, download_speed_bps
- [ ] Método `get_metrics_history(execution_id, time_range)`:
  - [ ] Range query: timestamp
  - [ ] Para gráficos de progresso
- [ ] Testes de integração

---

## 🕷️ Crawler Adapters

### BeautifulSoupCrawlerAdapter
- [ ] Criar `backend/infrastructure/adapters/beautifulsoup_crawler_adapter.py`
- [ ] Implementar interface `CrawlerPort`
- [ ] Inicialização:
  - [ ] httpx.AsyncClient com timeout, headers (User-Agent)
  - [ ] Opcional: ProxyConfig
- [ ] Método `crawl_page(url, file_extensions)`:
  - [ ] HTTP GET request (httpx)
  - [ ] Parse HTML (BeautifulSoup)
  - [ ] Extrair links via `<a href>`, `<link>`, etc.
  - [ ] Filtrar links por extensão (file_extensions)
  - [ ] Retornar lista de URLs
- [ ] Método `download_file(url, destination)`:
  - [ ] HTTP GET request
  - [ ] Stream para arquivo em /tmp
  - [ ] Progress tracking (opcional)
  - [ ] Retry automático (3 tentativas)
- [ ] Método `extract_assets(html, asset_types)`:
  - [ ] Parse HTML
  - [ ] Extrair URLs de assets:
    - [ ] CSS: `<link rel="stylesheet">`
    - [ ] JS: `<script src>`
    - [ ] Images: `<img src>`, CSS background-image
    - [ ] Fonts: `@font-face` em CSS
    - [ ] Videos: `<video>`, `<source>`
  - [ ] Resolver URLs relativas para absolutas
  - [ ] Retornar dict por tipo: {"css": [...], "js": [...]}
- [ ] Método `download_assets(asset_urls, destination_folder)`:
  - [ ] Download paralelo (max 10 simultâneos)
  - [ ] httpx AsyncClient
  - [ ] Salvar em subpastas por tipo
  - [ ] Error handling (skip em falha)
- [ ] Método `close()`:
  - [ ] Fechar httpx.AsyncClient
- [ ] Respeitar rate limits (delay entre requests)
- [ ] Respeitar robots.txt (opcional)
- [ ] Testes unitários e de integração

### PlaywrightCrawlerAdapter
- [ ] Criar `backend/infrastructure/adapters/playwright_crawler_adapter.py`
- [ ] Implementar interface `CrawlerPort`
- [ ] Inicialização:
  - [ ] Playwright browser (chromium)
  - [ ] Headless mode
  - [ ] Opcional: ProxyConfig
- [ ] Método `crawl_page(url, file_extensions)`:
  - [ ] Abrir browser page
  - [ ] Navegar para URL
  - [ ] Esperar JS rendering (wait_for_load_state)
  - [ ] Extrair links via page.evaluate()
  - [ ] Filtrar por extensão
  - [ ] Retornar lista de URLs
- [ ] Método `download_file(url, destination)`:
  - [ ] Navegar para URL
  - [ ] Esperar download
  - [ ] Salvar arquivo
- [ ] Método `extract_assets(html, asset_types)`:
  - [ ] Similar a BeautifulSoup mas com JS rendering
  - [ ] Capturar network requests (page.on('request'))
  - [ ] Filtrar por tipo (CSS, JS, images, etc.)
- [ ] Método `download_assets(asset_urls, destination_folder)`:
  - [ ] Download via browser context
- [ ] Método `close()`:
  - [ ] Fechar browser
- [ ] Timeout configurável (playwright_timeout_seconds)
- [ ] Testes de integração (requer Playwright instalado)

### ProxyManager
- [ ] Criar `backend/infrastructure/adapters/proxy_manager.py`
- [ ] Método `get_proxy_config(proxy_config)`:
  - [ ] Converter ProxyConfig VO para dict httpx/playwright
  - [ ] Suporte a HTTP, HTTPS, SOCKS5
  - [ ] Autenticação (username/password)
- [ ] Método `test_proxy(proxy_config)`:
  - [ ] Testar conectividade do proxy
  - [ ] Retornar True/False
- [ ] (Future) Método `get_next_proxy()`:
  - [ ] Rotação de proxies (round-robin, random)
  - [ ] Pool de proxies
- [ ] Testes unitários

---

## 📄 PDF Processing

### PyPDFMergerAdapter
- [ ] Criar `backend/infrastructure/adapters/pypdf_merger_adapter.py`
- [ ] Implementar interface `PDFMergerPort`
- [ ] Método `merge_pdfs(pdf_files, output_path)`:
  - [ ] Usar PyPDF2.PdfMerger
  - [ ] Iterar por arquivos e adicionar páginas
  - [ ] Salvar merged PDF
  - [ ] Validar PDFs (não corrompidos)
- [ ] Método `add_bookmarks(pdf, bookmarks)`:
  - [ ] Adicionar TOC (Table of Contents)
  - [ ] Bookmarks por arquivo original
- [ ] Método `validate_pdf(file_path)`:
  - [ ] Verificar se PDF é válido
  - [ ] Try/catch em PdfReader
  - [ ] Retornar True/False
- [ ] (Opcional) Método `compress_pdf(file_path)`:
  - [ ] Reduzir tamanho do PDF
  - [ ] Remove metadados desnecessários
- [ ] Testes unitários

---

## 🗃️ MinIO Storage

### MinioCrawlerStorageAdapter
- [ ] Criar `backend/infrastructure/adapters/minio_crawler_storage_adapter.py`
- [ ] Criar novo bucket `ingestify-crawled` (se não existir)
- [ ] Método `upload_crawled_file(execution_id, filename, file_path)`:
  - [ ] Object path: `crawled/{execution_id}/files/{filename}`
  - [ ] Upload para MinIO
  - [ ] Gerar public URL
  - [ ] Retornar dict: {"minio_path": "...", "public_url": "..."}
- [ ] Método `upload_html_page(execution_id, url, html_content)`:
  - [ ] Sanitizar URL para nome de arquivo
  - [ ] Object path: `crawled/{execution_id}/pages/{sanitized_url}.html`
  - [ ] Upload HTML
- [ ] Método `upload_asset(execution_id, asset_type, filename, file_path)`:
  - [ ] Object path: `crawled/{execution_id}/assets/{asset_type}/{filename}`
  - [ ] Tipos: css, js, images, fonts, videos
  - [ ] Upload para MinIO
- [ ] Método `upload_merged_pdf(execution_id, file_path)`:
  - [ ] Object path: `crawled/{execution_id}/merged/merged_{execution_id}.pdf`
  - [ ] Upload PDF merged
- [ ] Método `get_execution_folder(execution_id)`:
  - [ ] Retornar base path: `crawled/{execution_id}/`
- [ ] Método `list_execution_files(execution_id)`:
  - [ ] Listar todos os arquivos de uma execução
  - [ ] Retornar lista de objetos MinIO
- [ ] Método `delete_execution_folder(execution_id)`:
  - [ ] Deletar todos os arquivos de uma execução
  - [ ] Cleanup
- [ ] Configurar bucket policy (public read)
- [ ] Testes de integração com MinIO

---

## ✅ Testes de Integração

### Repository Tests
- [ ] Criar `backend/tests/infrastructure/repositories/test_mysql_crawler_job_repository.py`
  - [ ] Setup: criar database de teste
  - [ ] Teste `save()` - inserir e atualizar
  - [ ] Teste `find_by_id()` - buscar existente e não existente
  - [ ] Teste `find_by_user_id()` - filtrar por usuário
  - [ ] Teste `find_by_url_pattern()` - busca fuzzy
  - [ ] Teste `find_active()` - filtrar ativos
  - [ ] Teste `delete()` - deletar com cascade
  - [ ] Teardown: limpar database
- [ ] Criar `backend/tests/infrastructure/repositories/test_mysql_crawler_execution_repository.py`
- [ ] Criar `backend/tests/infrastructure/repositories/test_mysql_crawled_file_repository.py`

### Elasticsearch Tests
- [ ] Criar `backend/tests/infrastructure/elasticsearch/test_crawler_job_index.py`
  - [ ] Setup: criar índice de teste
  - [ ] Teste `index_crawler_job()` - indexar documento
  - [ ] Teste `search_by_url_pattern()` - fuzzy search
  - [ ] Teste `find_active_jobs()` - filtrar ativos
  - [ ] Teardown: deletar índice
- [ ] Criar `backend/tests/infrastructure/elasticsearch/test_crawler_execution_index.py`
- [ ] Criar `backend/tests/infrastructure/elasticsearch/test_crawler_metrics_index.py`

### Adapter Tests
- [ ] Criar `backend/tests/infrastructure/adapters/test_beautifulsoup_crawler_adapter.py`
  - [ ] Mock httpx.AsyncClient
  - [ ] Teste `crawl_page()` - extrair links
  - [ ] Teste `download_file()` - download com retry
  - [ ] Teste `extract_assets()` - parse HTML
  - [ ] Teste rate limiting
- [ ] Criar `backend/tests/infrastructure/adapters/test_playwright_crawler_adapter.py`
  - [ ] Requer Playwright instalado
  - [ ] Teste JS rendering
- [ ] Criar `backend/tests/infrastructure/adapters/test_pypdf_merger_adapter.py`
  - [ ] Teste merge de 2+ PDFs
  - [ ] Teste validação de PDF corrompido
  - [ ] Teste bookmarks
- [ ] Criar `backend/tests/infrastructure/adapters/test_minio_crawler_storage_adapter.py`
  - [ ] Mock MinIO client ou usar MinIO test container
  - [ ] Teste upload de arquivo
  - [ ] Teste geração de public URL
  - [ ] Teste delete folder

### Coverage
- [ ] Coverage >= 85% na infrastructure layer
- [ ] Rodar: `pytest backend/tests/infrastructure/ -v --cov=backend/infrastructure`

---

## 🔧 Configuração

### Backend Config
- [ ] Adicionar settings em `backend/shared/config.py`:
  ```python
  # Crawler Configuration
  crawler_enabled: bool = True
  crawler_max_concurrent_downloads: int = 5
  crawler_max_concurrent_assets: int = 10
  crawler_download_timeout_seconds: int = 60
  crawler_user_agent: str = "IngestifyBot/1.0"
  crawler_respect_robots_txt: bool = True
  crawler_rate_limit_per_second: int = 2

  # Crawler Engine Defaults
  crawler_default_engine: str = "beautifulsoup"

  # Playwright Configuration
  playwright_headless: bool = True
  playwright_timeout_seconds: int = 30
  playwright_wait_for_selector: str = ""
  playwright_browser_type: str = "chromium"

  # Proxy Configuration
  proxy_enabled: bool = False
  proxy_pool_enabled: bool = False
  proxy_rotation_strategy: str = "round_robin"

  # Retry Configuration
  crawler_retry_enabled: bool = True
  crawler_max_retries: int = 3
  crawler_retry_delay_base_seconds: int = 5
  crawler_retry_strategy_default: str = "conservative"

  # MinIO Buckets
  minio_bucket_crawled: str = "ingestify-crawled"
  ```

### Dependencies
- [ ] Adicionar ao `backend/requirements.txt`:
  ```txt
  # Web Scraping - BeautifulSoup
  beautifulsoup4>=4.12.0
  httpx>=0.27.0
  lxml>=5.0.0

  # Web Scraping - Playwright
  playwright>=1.40.0

  # Proxy Support
  httpx[socks]>=0.27.0
  python-socks>=2.4.0

  # PDF Processing
  PyPDF2>=3.0.0

  # Cron Parsing
  croniter>=2.0.0
  ```
- [ ] Instalar dependências: `pip install -r backend/requirements.txt`
- [ ] Instalar Playwright browsers: `python -m playwright install chromium`

### MinIO Bucket
- [ ] Criar bucket `ingestify-crawled` via:
  - [ ] MinIO client inicialização
  - [ ] Ou manualmente via MinIO Console
- [ ] Configurar bucket policy (public read):
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"AWS": "*"},
        "Action": ["s3:GetObject"],
        "Resource": ["arn:aws:s3:::ingestify-crawled/*"]
      }
    ]
  }
  ```

---

## 🎯 Entregável Sprint 2

- [ ] ✅ Todos os repositories MySQL implementados e testados
- [ ] ✅ Todos os adapters Elasticsearch implementados e testados
- [ ] ✅ BeautifulSoup crawler adapter funcionando
- [ ] ✅ Playwright crawler adapter funcionando
- [ ] ✅ PyPDF merger adapter funcionando
- [ ] ✅ MinIO crawler storage adapter funcionando
- [ ] ✅ Bucket `ingestify-crawled` configurado
- [ ] ✅ Dependencies instaladas (beautifulsoup4, playwright, PyPDF2)
- [ ] ✅ Playwright browsers instalados
- [ ] ✅ Coverage >= 85% de testes de integração
- [ ] ✅ Documentação atualizada (infrastructure layer)

---

## 📚 Referências

- [CRAWLER_INTEGRATION_PLAN.md](./CRAWLER_INTEGRATION_PLAN.md) - Seção 6 (Infrastructure Layer)
- [backend/shared/minio_client.py](../../backend/shared/minio_client.py) - Exemplo de MinIO client
- Playwright docs: https://playwright.dev/python/
- BeautifulSoup docs: https://www.crummy.com/software/BeautifulSoup/bs4/doc/
- PyPDF2 docs: https://pypdf2.readthedocs.io/
