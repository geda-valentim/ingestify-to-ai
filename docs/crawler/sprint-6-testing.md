# Sprint 6: Testing, Monitoring & Documentation

> **Plano de sprint (crawler) — não concluído.** Estado real do crawler no código: [../features/crawler.md](../features/crawler.md).

**Duração:** Semanas 11-12
**Objetivo:** Qualidade e observabilidade - produção pronta

---

## 🧪 Testes End-to-End

### E2E Test Suite
- [ ] Criar `backend/tests/e2e/test_crawler_complete_flow.py`
- [ ] Setup:
  - [ ] Docker Compose completo (MySQL, Redis, Elasticsearch, MinIO, Worker, Beat)
  - [ ] Database limpa (fixtures)
  - [ ] MinIO bucket criado
  - [ ] Elasticsearch indices criados
- [ ] **Teste 1: Fluxo completo - HTML only**:
  1. [ ] Criar usuário via API
  2. [ ] Criar crawler via POST /crawlers:
     - [ ] crawl_type: PAGE_WITH_FILTERED
     - [ ] file_extensions: ["pdf"]
     - [ ] download_assets: false
     - [ ] schedule_type: ONE_TIME
  3. [ ] Executar crawler via POST /crawlers/{id}/execute
  4. [ ] Aguardar conclusão (polling GET /crawlers/{id}/executions/{exec_id})
  5. [ ] Verificar status == COMPLETED
  6. [ ] Verificar arquivos no MinIO (GET /crawlers/{id}/executions/{exec_id}/files)
  7. [ ] Verificar public_url acessível
  8. [ ] Verificar dados no MySQL (crawler_jobs, crawler_executions, crawled_files)
  9. [ ] Verificar métricas no Elasticsearch
- [ ] **Teste 2: Fluxo com assets (CSS, JS, images)**:
  1. [ ] Criar crawler com download_assets=true, asset_types=["css", "js", "images"]
  2. [ ] Executar e aguardar
  3. [ ] Verificar estrutura de pastas no MinIO:
     - [ ] /pages/
     - [ ] /assets/css/
     - [ ] /assets/js/
     - [ ] /assets/images/
  4. [ ] Verificar contagem de assets (files_by_type)
- [ ] **Teste 3: Fluxo com merge de PDFs**:
  1. [ ] Criar crawler com pdf_handling=BOTH
  2. [ ] Executar
  3. [ ] Verificar PDFs individuais no MinIO
  4. [ ] Verificar merged PDF no MinIO (/merged/)
- [ ] **Teste 4: Retry com fallback de engines**:
  1. [ ] Mock site que falha com BeautifulSoup
  2. [ ] Criar crawler com retry_enabled=true, retry_strategy=conservative
  3. [ ] Executar
  4. [ ] Verificar retry_history (tentativas BS4, BS4+proxy, Playwright)
  5. [ ] Verificar engine_used=PLAYWRIGHT
- [ ] **Teste 5: Agendamento recurring (Celery Beat)**:
  1. [ ] Criar crawler com schedule_type=RECURRING, cron="* * * * *" (every minute)
  2. [ ] Aguardar 2 minutos
  3. [ ] Verificar >= 2 execuções criadas
  4. [ ] Pausar crawler (PATCH /crawlers/{id}/pause)
  5. [ ] Aguardar 1 minuto
  6. [ ] Verificar que nenhuma nova execução foi criada
- [ ] **Teste 6: Cancelamento de execução**:
  1. [ ] Criar crawler
  2. [ ] Executar
  3. [ ] Cancelar via POST /crawlers/{id}/executions/{exec_id}/cancel
  4. [ ] Verificar status == CANCELLED
  5. [ ] Verificar Celery task revogada
- [ ] **Teste 7: Detecção de duplicatas**:
  1. [ ] Criar crawler com URL "https://example.com/page?id=1"
  2. [ ] Tentar criar outro com URL "https://example.com/page?id=2"
  3. [ ] Verificar warning de duplicata na resposta
- [ ] **Teste 8: Proxy usage**:
  1. [ ] Criar crawler com use_proxy=true, proxy_config={...}
  2. [ ] Executar
  3. [ ] Verificar proxy_used=true na execution
- [ ] Teardown:
  - [ ] Limpar database
  - [ ] Limpar MinIO
  - [ ] Limpar Elasticsearch

### Coverage Total
- [ ] Rodar coverage em todo o projeto:
  ```bash
  pytest backend/tests/ -v --cov=backend --cov-report=html --cov-report=term
  ```
- [ ] Meta: Coverage >= 85% total
- [ ] Revisar arquivos sem coverage
- [ ] Adicionar testes faltantes

---

## 📊 Elasticsearch Queries & Dashboards

### Queries Úteis

#### Query 1: Total de crawlers ativos
- [ ] Criar query:
  ```json
  GET /crawler-jobs-*/_search
  {
    "query": { "term": { "is_active": true } },
    "size": 0
  }
  ```
- [ ] Documentar em `docs/crawler/ELASTICSEARCH_QUERIES.md`

#### Query 2: Execuções por status (últimas 24h)
- [ ] Criar query:
  ```json
  GET /crawler-executions-*/_search
  {
    "query": {
      "range": { "started_at": { "gte": "now-24h" } }
    },
    "aggs": {
      "by_status": { "terms": { "field": "status" } }
    }
  }
  ```

#### Query 3: Taxa de sucesso (últimos 7 dias)
- [ ] Criar query com aggregations (COMPLETED vs FAILED)
- [ ] Calcular success_rate

#### Query 4: Progresso de execução em tempo real
- [ ] Criar query:
  ```json
  GET /crawler-metrics-*/_search
  {
    "query": { "term": { "execution_id": "exec-456" } },
    "sort": [{ "timestamp": "desc" }],
    "size": 1
  }
  ```

#### Query 5: Top 10 crawlers por volume de downloads
- [ ] Agregação por crawler_job_id + sum(files_downloaded)

#### Query 6: Métricas de retry
- [ ] Taxa de execuções que precisaram de retry
- [ ] Success rate por attempt (0, 1, 2, 3)
- [ ] Engine mais efetiva (BeautifulSoup vs Playwright)

#### Query 7: Performance por domínio
- [ ] Group by domain (extrair de URL)
- [ ] Avg duration_seconds
- [ ] Avg download_speed_mbps

### Dashboards (Kibana ou Custom)
- [ ] **Dashboard 1: Overview**
  - [ ] Total crawlers (ativos, pausados, stopped)
  - [ ] Total execuções (24h, 7d, 30d)
  - [ ] Success rate (gráfico de linha)
  - [ ] Volume de downloads (arquivos, bytes)
- [ ] **Dashboard 2: Execution Monitoring**
  - [ ] Execuções em andamento (real-time)
  - [ ] Progresso por execução (progress_percentage)
  - [ ] Erros recentes (últimas 24h)
  - [ ] Download speed (gráfico)
- [ ] **Dashboard 3: Retry Analytics**
  - [ ] Taxa de retry por crawler
  - [ ] Success by attempt (0, 1, 2, 3)
  - [ ] Engine usado (BS4 vs Playwright)
  - [ ] Tipos de erro mais comuns
- [ ] **Dashboard 4: Performance**
  - [ ] Avg duration por crawler
  - [ ] Download speed trends
  - [ ] Storage usage (total_size_bytes)
  - [ ] Worker utilization
- [ ] Exportar dashboards (JSON)
- [ ] Documentar em `docs/crawler/DASHBOARDS.md`

---

## 📝 Logs Estruturados

### Structured Logging (structlog)
- [ ] Instalar: `pip install structlog`
- [ ] Configurar `backend/shared/logging_config.py`:
  ```python
  import structlog

  structlog.configure(
      processors=[
          structlog.stdlib.add_log_level,
          structlog.stdlib.add_logger_name,
          structlog.processors.TimeStamper(fmt="iso"),
          structlog.processors.StackInfoRenderer(),
          structlog.processors.format_exc_info,
          structlog.processors.JSONRenderer()
      ],
      context_class=dict,
      logger_factory=structlog.stdlib.LoggerFactory(),
      cache_logger_on_first_use=True,
  )
  ```
- [ ] Substituir logging padrão por structlog:
  ```python
  import structlog
  logger = structlog.get_logger(__name__)

  logger.info(
      "crawler_execution_started",
      crawler_job_id=job.id,
      execution_id=execution.id,
      url=job.url,
      engine=job.crawler_engine
  )
  ```
- [ ] Eventos importantes para logar:
  - [ ] `crawler_job_created`
  - [ ] `crawler_execution_started`
  - [ ] `crawler_execution_completed`
  - [ ] `crawler_execution_failed`
  - [ ] `crawler_page_downloaded`
  - [ ] `crawler_file_downloaded`
  - [ ] `crawler_retry_attempt`
  - [ ] `crawler_pdf_merged`
  - [ ] `crawler_assets_downloaded`

### Log Aggregation
- [ ] (Opcional) Configurar Filebeat/Fluentd para enviar logs para Elasticsearch
- [ ] Index pattern: `crawler-logs-*`
- [ ] Queries úteis:
  - [ ] Todos os erros: `{"query": {"term": {"level": "ERROR"}}}`
  - [ ] Execuções de um crawler: `{"query": {"term": {"crawler_job_id": "..."}}}`

---

## 🔔 Alertas e Monitoramento

### Health Checks
- [ ] Criar endpoint `GET /crawlers/health`:
  ```python
  @router.get("/health", response_model=CrawlerHealthResponse)
  async def crawler_health():
      return {
          "mysql": check_mysql_connection(),
          "redis": check_redis_connection(),
          "elasticsearch": check_elasticsearch_connection(),
          "minio": check_minio_connection(),
          "celery_workers": count_active_workers(),
          "celery_beat": check_beat_running()
      }
  ```
- [ ] Health check periódico (Celery Beat task):
  ```python
  @celery_app.task
  def crawler_health_check():
      # Verificar workers ativos
      # Verificar execuções stuck (>1h em PROCESSING)
      # Alertar se problemas
  ```

### Alertas
- [ ] **Alerta 1: Crawler com falhas recorrentes**
  - [ ] Query: crawlers com failed_executions >= 3 (consecutivas)
  - [ ] Ação: Email para usuário + webhook
- [ ] **Alerta 2: Execução stuck**
  - [ ] Query: execuções em PROCESSING há mais de 1h
  - [ ] Ação: Auto-cancelar + notificar
- [ ] **Alerta 3: Workers offline**
  - [ ] Verificar workers ativos via Celery inspect
  - [ ] Ação: Alertar admin
- [ ] **Alerta 4: Storage usage alto**
  - [ ] Verificar total_size_bytes por usuário
  - [ ] Ação: Notificar quando > 10GB

### Monitoring Tasks (Celery Beat)
- [ ] Task: `detect_stuck_executions`
  - [ ] Executar a cada 15 minutos
  - [ ] Query: status=PROCESSING AND started_at < now()-1h
  - [ ] Marcar como FAILED + logar
- [ ] Task: `cleanup_old_executions`
  - [ ] Executar diariamente
  - [ ] Deletar execuções > 90 dias do MySQL
  - [ ] Deletar arquivos do MinIO
- [ ] Task: `calculate_daily_stats`
  - [ ] Executar diariamente
  - [ ] Agregar estatísticas do dia
  - [ ] Indexar no Elasticsearch

---

## 📚 Documentação

### README do Módulo Crawler
- [ ] Criar `docs/crawler/README.md`:
  - [ ] Visão geral do módulo
  - [ ] Features principais
  - [ ] Arquitetura (Clean Architecture)
  - [ ] Como usar (exemplos de API)
  - [ ] Configuração (environment variables)
  - [ ] Deployment (Docker Compose)

### Guia de Uso (User Documentation)
- [ ] Criar `docs/crawler/USER_GUIDE.md`:
  - [ ] Como criar crawler
  - [ ] Tipos de crawl (PAGE_ONLY, PAGE_WITH_ALL, etc.)
  - [ ] Como escolher engine (BeautifulSoup vs Playwright)
  - [ ] Quando usar proxy
  - [ ] Como configurar retry strategy
  - [ ] Como agendar crawls (cron)
  - [ ] Como monitorar execuções
  - [ ] Como baixar arquivos (MinIO URLs)
  - [ ] Troubleshooting comum

### API Documentation
- [ ] Criar `docs/crawler/API.md`:
  - [ ] Todos os endpoints (já criado no Sprint 5)
  - [ ] Autenticação
  - [ ] Rate limiting
  - [ ] Códigos de erro
  - [ ] Exemplos de requests (curl, httpx, Postman)

### Elasticsearch Queries
- [ ] Criar `docs/crawler/ELASTICSEARCH_QUERIES.md`:
  - [ ] Queries úteis (já listadas acima)
  - [ ] Como criar dashboards
  - [ ] Análise de métricas

### Troubleshooting Guide
- [ ] Criar `docs/crawler/TROUBLESHOOTING.md`:
  - [ ] **Problema 1: Crawler não executa no horário agendado**
    - [ ] Verificar Celery Beat está rodando
    - [ ] Verificar cron expression
    - [ ] Verificar is_active=true
  - [ ] **Problema 2: Execução falha com timeout**
    - [ ] Aumentar crawler_download_timeout_seconds
    - [ ] Verificar site está acessível
    - [ ] Usar proxy
  - [ ] **Problema 3: Site retorna 403**
    - [ ] Usar Playwright (JS rendering)
    - [ ] Usar proxy
    - [ ] Verificar User-Agent
  - [ ] **Problema 4: PDFs não são merged**
    - [ ] Verificar pdf_handling config
    - [ ] Verificar PDFs válidos (não corrompidos)
    - [ ] Verificar logs do worker
  - [ ] **Problema 5: Assets não são baixados**
    - [ ] Verificar download_assets=true
    - [ ] Verificar asset_types config
    - [ ] Verificar parsing de HTML
  - [ ] **Problema 6: Workers não processam tasks**
    - [ ] Verificar workers ativos: `celery -A workers.celery_app inspect active`
    - [ ] Verificar Redis connection
    - [ ] Verificar logs do worker

### Architecture Documentation
- [ ] Atualizar `backend/docs/CLEAN_ARCHITECTURE.md`:
  - [ ] Adicionar seção sobre crawler module
  - [ ] Diagrams (domain, application, infrastructure, workers)
- [ ] Criar `docs/crawler/ARCHITECTURE.md`:
  - [ ] Diagrama de alto nível
  - [ ] Fluxo de dados (User → API → Workers → MinIO)
  - [ ] Camadas (domain, application, infrastructure, presentation, workers)
  - [ ] Decisões arquiteturais (por que Celery, por que Elasticsearch, etc.)

### Changelog
- [ ] Criar `docs/crawler/CHANGELOG.md`:
  - [ ] v1.0.0 - Initial release
  - [ ] Features implementadas
  - [ ] Sprints concluídas

---

## 🚀 Performance Tuning

### Celery Optimization
- [ ] Configurar concurrency por worker:
  ```bash
  celery -A workers.celery_app worker -Q crawler --concurrency=4
  ```
- [ ] Configurar prefetch multiplier:
  ```python
  worker_prefetch_multiplier = 1  # Evitar starving
  ```
- [ ] Configurar acks_late:
  ```python
  task_acks_late = True  # Reprocessar se worker crashar
  ```
- [ ] Benchmark: tempo médio de execução por crawler
- [ ] Meta: < 5 minutos para 100 arquivos

### Elasticsearch Optimization
- [ ] Configurar sharding adequado:
  ```json
  {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1
    }
  }
  ```
- [ ] Configurar refresh_interval:
  - [ ] crawler-jobs-*: 30s (não precisa real-time)
  - [ ] crawler-executions-*: 10s
  - [ ] crawler-metrics-*: 5s (real-time)
- [ ] Configurar ILM (Index Lifecycle Management):
  - [ ] crawler-executions-*: rollover diário, delete após 90 dias
  - [ ] crawler-metrics-*: rollover diário, delete após 7 dias
- [ ] Benchmark: latência de queries
- [ ] Meta: < 100ms para queries simples

### MySQL Optimization
- [ ] Verificar índices criados (Sprint 1)
- [ ] Adicionar índices compostos se necessário:
  ```sql
  CREATE INDEX idx_crawler_jobs_user_status ON crawler_jobs(user_id, status);
  CREATE INDEX idx_crawler_executions_job_status ON crawler_executions(crawler_job_id, status);
  ```
- [ ] Configurar connection pool:
  ```python
  engine = create_engine(
      database_url,
      pool_size=10,
      max_overflow=20,
      pool_pre_ping=True
  )
  ```
- [ ] Benchmark: tempo de queries
- [ ] Meta: < 50ms para queries simples

### MinIO Optimization
- [ ] Configurar multipart upload para arquivos grandes:
  ```python
  minio_client.fput_object(
      bucket_name,
      object_name,
      file_path,
      part_size=10*1024*1024  # 10MB parts
  )
  ```
- [ ] Configurar compressão (opcional)
- [ ] Benchmark: velocidade de upload/download
- [ ] Meta: > 10 MB/s

### Load Testing
- [ ] Criar script de load testing:
  ```python
  # backend/tests/load/test_crawler_load.py
  from locust import HttpUser, task, between

  class CrawlerUser(HttpUser):
      wait_time = between(1, 3)

      @task
      def create_crawler(self):
          self.client.post("/crawlers", json={...})

      @task
      def list_crawlers(self):
          self.client.get("/crawlers")
  ```
- [ ] Rodar load test: `locust -f backend/tests/load/test_crawler_load.py`
- [ ] Medir:
  - [ ] Requests/second
  - [ ] Latência média
  - [ ] Latência p95, p99
  - [ ] Taxa de erro
- [ ] Meta:
  - [ ] 100 req/s sem degradação
  - [ ] Latência p95 < 500ms
  - [ ] Taxa de erro < 1%

---

## 🎯 Entregável Sprint 6

- [ ] ✅ Testes E2E completos (8 cenários)
- [ ] ✅ Coverage total >= 85%
- [ ] ✅ Elasticsearch queries documentadas (7 queries)
- [ ] ✅ Dashboards criados (4 dashboards)
- [ ] ✅ Logs estruturados (structlog)
- [ ] ✅ Health checks implementados
- [ ] ✅ Alertas configurados (4 alertas)
- [ ] ✅ Monitoring tasks (Celery Beat)
- [ ] ✅ Documentação completa:
  - [ ] README.md
  - [ ] USER_GUIDE.md
  - [ ] API.md
  - [ ] ELASTICSEARCH_QUERIES.md
  - [ ] TROUBLESHOOTING.md
  - [ ] ARCHITECTURE.md
  - [ ] CHANGELOG.md
- [ ] ✅ Performance tuning (Celery, Elasticsearch, MySQL, MinIO)
- [ ] ✅ Load testing executado
- [ ] ✅ Sistema pronto para produção 🚀

---

## 🚀 Production Checklist

### Pré-Deploy
- [ ] Todos os testes passando (unit, integration, e2e)
- [ ] Coverage >= 85%
- [ ] Load testing executado
- [ ] Documentação completa
- [ ] Environment variables configuradas (production)
- [ ] Secrets seguros (JWT key, database passwords, API keys)
- [ ] Backups configurados (MySQL, Elasticsearch)

### Deploy
- [ ] Docker Compose para produção:
  - [ ] Build images
  - [ ] Scale workers: `docker compose up -d --scale crawler-worker=5`
  - [ ] Verificar services rodando
- [ ] Rodar migrations: `alembic upgrade head`
- [ ] Criar índices Elasticsearch
- [ ] Criar bucket MinIO
- [ ] Carregar crawlers ativos no Celery Beat
- [ ] Verificar health checks: `curl http://api/crawlers/health`
- [ ] Monitorar logs (primeiras execuções)

### Pós-Deploy
- [ ] Verificar métricas no Elasticsearch
- [ ] Verificar execuções bem-sucedidas
- [ ] Configurar alertas
- [ ] Configurar backup automático
- [ ] Documentar procedimentos de rollback

---

## 📚 Referências

- [CRAWLER_INTEGRATION_PLAN.md](./CRAWLER_INTEGRATION_PLAN.md) - Plano completo
- [backend/docs/CLEAN_ARCHITECTURE.md](../../backend/docs/CLEAN_ARCHITECTURE.md)
- Structlog docs: https://www.structlog.org/
- Kibana docs: https://www.elastic.co/kibana
- Locust docs: https://docs.locust.io/

---

## 🎉 Conclusão Sprint 6

Após completar este sprint, o módulo Crawler estará **100% pronto para produção** com:

✅ Cobertura de testes >= 85%
✅ Monitoramento completo (Elasticsearch dashboards)
✅ Logs estruturados para troubleshooting
✅ Alertas configurados
✅ Documentação completa
✅ Performance otimizada
✅ Load testing validado

**Sistema pronto para processar crawls em escala de produção! 🚀**
