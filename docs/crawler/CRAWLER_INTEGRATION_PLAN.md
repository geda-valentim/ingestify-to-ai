# Plano de Integração: Web Crawler Agendado

> **Planejado, não implementado.** Só partes das sprints 1–2 viraram código, e esse código está dormente (não é importado pela API nem pelos workers e não entra nas imagens Docker). Estado real: [../features/crawler.md](../features/crawler.md).

**Sistema Ingestify - Módulo Crawler**

**Versão:** 1.3 (Atualizado)
**Data:** 2025-01-13
**Status:** Planejamento - Arquitetura STI (Single Table Inheritance)
**Changelog:**
- v1.3: Mudança arquitetural para STI - reuso da tabela jobs existente
- v1.2: Adicionado sistema de retry com fallback progressivo de engines
- v1.1: Múltiplas engines e download granular de assets
- v1.0: Plano inicial

---

## 1. Visão Geral

### 1.1 Objetivo

Integrar funcionalidade completa de **web crawler agendado** ao sistema Ingestify, permitindo:

- ✅ Agendamento de crawls com frequência flexível (one-time, hourly, daily, weekly, monthly, custom cron)
- ✅ **Múltiplas engines de crawling:**
  - BeautifulSoup (bs4) - rápido, leve, para sites estáticos
  - BeautifulSoup + Proxy - para sites com restrição geográfica
  - Playwright - para sites com JavaScript/SPA
  - Playwright + Proxy - para sites JS com restrição geográfica
- ✅ **Download flexível de assets:**
  - HTML only (sem assets)
  - HTML + Assets selecionados (CSS, JS, Images, Fonts, Videos, Documents)
- ✅ Download de páginas HTML + arquivos específicos (PDF, XLSX, CSV, imagens, etc.)
- ✅ Merge de PDFs (individual, combinado ou ambos)
- ✅ Detecção inteligente de duplicatas via padrão de URL
- ✅ Rastreamento de progresso em tempo real
- ✅ Histórico completo de execuções com métricas
- ✅ Armazenamento em Min.io com URLs públicas
- ✅ Busca e analytics via Elasticsearch

---

### 1.2 Features Principais (Novo na v1.1)

#### 🔧 Múltiplas Engines de Crawling

| Engine | Descrição | Use Case |
|--------|-----------|----------|
| **BeautifulSoup** | Rápido, leve, para HTML estático | Blogs, documentação, sites simples |
| **BeautifulSoup + Proxy** | BeautifulSoup com proxy | Sites estáticos com geo-blocking |
| **Playwright** | JavaScript rendering, SPAs | React, Vue, Angular, dashboards |
| **Playwright + Proxy** | Playwright com proxy | Sites JS com geo-blocking |

#### 📦 Download Granular de Assets

Controle preciso sobre o que baixar além do HTML:

- **HTML Only** - Apenas o código HTML (rápido, leve)
- **HTML + CSS** - HTML + estilos (visualização básica)
- **HTML + CSS + Images** - Página completa sem interatividade
- **HTML + CSS + JS + Images** - Página funcional offline
- **Full (CSS + JS + Images + Fonts + Videos)** - Arquivamento completo

**Asset Types disponíveis:**
- `css` - Arquivos .css
- `js` - Arquivos .js
- `images` - .jpg, .png, .gif, .svg, .webp, .ico
- `fonts` - .woff, .woff2, .ttf, .otf
- `videos` - .mp4, .webm, .ogg
- `documents` - .pdf, .docx, .xlsx (linkados na página)

#### 🌐 Suporte a Proxies

- **Protocolos:** HTTP, HTTPS, SOCKS5
- **Autenticação:** Username/password
- **Configuração por job** (cada crawler pode ter seu proxy)
- **Rotação de proxies** (future: pool de proxies)

#### 🔄 Sistema de Retry Inteligente (Novo na v1.2)

**Fallback progressivo de engines** - Aumenta a "potência" a cada retry até obter sucesso:

```
Tentativa 0: BeautifulSoup (rápido, leve)
     ↓ FALHOU (timeout)
Retry 1: BeautifulSoup + Proxy (bypassa bloqueio)
     ↓ FALHOU (403)
Retry 2: Playwright (renderiza JavaScript)
     ↓ FALHOU (erro JS)
Retry 3: Playwright + Proxy (máxima compatibilidade)
     ↓ SUCESSO ✅
```

**Estratégias pré-definidas:**
- **Conservative** - BS4 → BS4+Proxy → Playwright → Playwright+Proxy
- **Aggressive** - Playwright → Playwright+Proxy (para sites JS conhecidos)
- **Proxy First** - Sempre com proxy (geo-blocking conhecido)
- **Balanced** - Mix de todas as combinações

**Features:**
- ✅ Backoff exponencial (delays crescentes)
- ✅ Histórico completo de tentativas (`retry_history`)
- ✅ Métricas de retry em Elasticsearch
- ✅ Configurável por crawler

---

### 1.3 Infraestrutura Existente (Reuso 100%)

O sistema Ingestify **já possui toda a infraestrutura necessária**:

| Componente | Uso no Crawler |
|------------|----------------|
| **Celery + Celery Beat** | Agendamento e execução de crawls |
| **MySQL** | Persistência de configurações e histórico |
| **Elasticsearch** | Metadados, busca fuzzy, métricas time-series |
| **Min.io** | Armazenamento de arquivos crawleados |
| **Redis** | Filas Celery e cache de progresso |
| **Clean Architecture** | Estrutura modular para novos módulos |
| **Auth (JWT + API Keys)** | Segurança e controle de acesso |

**Conclusão:** Zero infraestrutura nova. Apenas novos módulos integrados.

---

## 2. Arquitetura de Alto Nível

### 2.1 Camadas da Clean Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  PRESENTATION LAYER                      │
│  API Controllers: /crawlers/* (REST endpoints)           │
│  Schemas: Requests e Responses (Pydantic)                │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  APPLICATION LAYER                       │
│  Use Cases:                                              │
│   - CreateCrawlerJobUseCase                              │
│   - ExecuteCrawlerJobUseCase                             │
│   - ListCrawlerJobsUseCase                               │
│   - UpdateCrawlerJobUseCase                              │
│   - GetCrawlerExecutionHistoryUseCase                    │
│   - PauseCrawlerJobUseCase                               │
│  DTOs: CrawlerJobDTO, CrawlerExecutionDTO                │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    DOMAIN LAYER                          │
│  Entities:                                               │
│   - CrawlerJob (configuração do crawler)                 │
│   - CrawlerExecution (execução individual)               │
│   - CrawledFile (arquivo baixado)                        │
│  Value Objects:                                          │
│   - URLPattern (normalização para duplicatas)            │
│   - CrawlerSchedule (configuração de agendamento)        │
│   - CrawlerEngine (bs4/playwright + proxy)              │
│   - ProxyConfig (host, port, auth, protocol)            │
│   - AssetTypes (tipos de assets a baixar)               │
│   - DownloadConfig (filtros de arquivo, PDFs)           │
│  Services:                                               │
│   - URLNormalizerService (normalizar URLs)               │
│   - DuplicateDetectorService (detectar duplicatas)       │
│   - CrawlerProgressService (calcular progresso)          │
│  Repositories (interfaces):                              │
│   - CrawlerJobRepository                                 │
│   - CrawlerExecutionRepository                           │
│   - CrawledFileRepository                                │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                INFRASTRUCTURE LAYER                      │
│  Repositories (MySQL):                                   │
│   - MySQLCrawlerJobRepository                            │
│   - MySQLCrawlerExecutionRepository                      │
│   - MySQLCrawledFileRepository                           │
│  Adapters:                                               │
│   - BeautifulSoupCrawlerAdapter (scraping estático)      │
│   - PlaywrightCrawlerAdapter (scraping JS/SPA)          │
│   - ProxyManager (gestão de proxies)                    │
│   - PyPDFMergerAdapter (merge de PDFs)                   │
│   - MinioCrawlerStorageAdapter (storage)                 │
│  Elasticsearch:                                          │
│   - CrawlerJobIndex                                      │
│   - CrawlerExecutionIndex (time-series)                  │
│   - CrawlerMetricsIndex (métricas tempo real)            │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                      WORKERS LAYER                       │
│  Celery Tasks:                                           │
│   - execute_crawler (task principal)                     │
│   - schedule_crawler (Celery Beat trigger)               │
│  Worker Logic:                                           │
│   - CrawlerScraper (orquestração do crawl)               │
│   - RetryManager (gerenciamento de retries)              │
│   - FileDownloader (download paralelo)                   │
│   - PDFProcessor (merge de PDFs)                         │
│   - ProgressTracker (atualização tempo real)             │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Fluxo de Dados

```
USER → API → Use Case → Domain → Infrastructure → Workers
                                       ↓
                                MySQL + Elasticsearch + Min.io
                                       ↓
                                Celery Beat (agendamento)
                                       ↓
                                Celery Workers (execução)
```

---

## 3. Modelos de Dados

### 3.1 MySQL (Persistência) - STI Pattern

#### 🎯 Decisão Arquitetural: Single Table Inheritance (STI)

**Estratégia:** Reutilizar tabela `jobs` existente ao invés de criar novas tabelas.

**Por que STI?**
- ✅ **DRY**: Reusa 95% da infraestrutura existente (tabela, repositórios, use cases)
- ✅ **Performance**: Zero JOINs - queries rápidas em tabela única
- ✅ **Flexibilidade**: JSON permite evoluir schema sem migrations complexas
- ✅ **Integração Natural**: Crawler pode criar ConversionJobs para páginas baixadas
- ✅ **Simplicidade**: 1 migration vs 3 migrations

**Trade-off Aceito:**
- ⚠️ Validação JSON no application layer (Pydantic resolve isso)
- ⚠️ 2 colunas JSON novas (ambas nullable, zero impacto em jobs existentes)

---

#### Schema Changes - Apenas 2 Colunas JSON

**Tabela `jobs` (EXISTING) - Adicionar:**

```sql
ALTER TABLE jobs
ADD COLUMN crawler_config JSON DEFAULT NULL,
ADD COLUMN crawler_schedule JSON DEFAULT NULL,
ADD INDEX idx_job_type_status (job_type, status);
```

**Campos Existentes Reutilizados para Crawler:**

| Campo Existente | Uso no Crawler |
|----------------|----------------|
| `job_type` | Discriminador polimórfico ("crawler") |
| `source_url` | URL a crawlear |
| `status` | Status da execução (pending, processing, completed, failed) |
| `progress` | Progresso do download (0-100%) |
| `user_id` | Dono do crawler |
| `name` | Nome amigável do crawler |
| `parent_job_id` | Histórico de execuções (cada run = child job) |
| `created_at`, `started_at`, `completed_at` | Timestamps |
| `error_message` | Mensagens de erro |
| `total_pages` | Total de páginas descobertas (reutilizado) |
| `pages_completed` | Páginas baixadas com sucesso |
| `pages_failed` | Páginas com erro |

**Novos Campos JSON:**

| Campo JSON | Tipo | Descrição |
|------------|------|-----------|
| `crawler_config` | JSON | Configuração de download (mode, extensions, PDF handling, etc.) |
| `crawler_schedule` | JSON | Configuração de agendamento (frequency, cron, timezone, etc.) |

---

#### Estrutura crawler_config (JSON)

```json
{
  "mode": "page_only|page_with_all|page_with_filtered|full_website",
  "extension_selection_mode": "quick_select|individual|custom",
  "file_extensions": ["pdf", "xlsx", "csv"],
  "extension_categories": ["documents", "images"],
  "pdf_handling": "individual|combined|both",
  "max_depth": 3,
  "follow_external_links": false,
  "crawler_engine": "BEAUTIFULSOUP|PLAYWRIGHT",
  "use_proxy": false,
  "proxy_config": {
    "host": "proxy.example.com",
    "port": 8080,
    "username": "user",
    "password": "pass",
    "protocol": "http"
  },
  "download_assets": true,
  "asset_types": ["css", "js", "images", "fonts", "videos"],
  "retry_enabled": true,
  "max_retries": 3,
  "retry_strategy": [
    {"attempt": 0, "engine": "BEAUTIFULSOUP", "use_proxy": false, "delay_seconds": 0},
    {"attempt": 1, "engine": "BEAUTIFULSOUP", "use_proxy": true, "delay_seconds": 5},
    {"attempt": 2, "engine": "PLAYWRIGHT", "use_proxy": false, "delay_seconds": 10},
    {"attempt": 3, "engine": "PLAYWRIGHT", "use_proxy": true, "delay_seconds": 15}
  ]
}
```

#### Estrutura crawler_schedule (JSON)

```json
{
  "type": "one_time|recurring",
  "run_immediately": true,
  "scheduled_datetime": "2025-10-25T14:30:00Z",
  "frequency": "hourly|daily|weekly|monthly|custom",
  "days_of_week": [1, 3, 5],
  "days_of_month": [1, 15],
  "times": ["07:00", "09:00", "12:00"],
  "cron_expression": "0 7,9,12 * * 1,3,5",
  "timezone": "America/Sao_Paulo",
  "next_runs": ["2025-01-20T09:00:00Z", "2025-01-21T09:00:00Z"],
  "last_run": "2025-01-19T09:00:00Z",
  "execution_count": 5,
  "max_executions": 100,
  "expires_at": "2025-12-31T23:59:59Z"
}
```

---

#### Histórico de Execuções via parent_job_id

**Padrão:** Cada execução é um child job do crawler principal

```
CrawlerJob (id=crawler-1, job_type=CRAWLER)
  ├── Execution 1 (id=exec-1, parent_job_id=crawler-1, created_at=2025-01-20)
  ├── Execution 2 (id=exec-2, parent_job_id=crawler-1, created_at=2025-01-21)
  └── Execution 3 (id=exec-3, parent_job_id=crawler-1, created_at=2025-01-22)
```

**Consulta de histórico:**
```sql
SELECT * FROM jobs
WHERE parent_job_id = 'crawler-1'
ORDER BY created_at DESC;
```

---

#### SQLAlchemy Models (Polymorphic)

```python
from sqlalchemy import Column, String, Enum, JSON
from sqlalchemy.orm import declared_attr
from shared.database import Base


class JobTypeEnum(str, enum.Enum):
    MAIN = "main"
    SPLIT = "split"
    PAGE = "page"
    MERGE = "merge"
    DOWNLOAD = "download"
    CRAWLER = "crawler"  # Novo tipo


class Job(Base):
    """Base Job model - Single Table Inheritance root"""
    __tablename__ = "jobs"

    # Polymorphic configuration
    __mapper_args__ = {
        "polymorphic_on": "job_type",
        "polymorphic_identity": "main",
        "with_polymorphic": "*",
    }

    # ... campos existentes ...

    # Novos campos JSON para crawler
    crawler_config = Column(JSON, nullable=True)
    crawler_schedule = Column(JSON, nullable=True)


class ConversionJob(Job):
    """Conversion Job - documentos (MAIN, SPLIT, PAGE, MERGE, DOWNLOAD)"""
    __mapper_args__ = {
        "polymorphic_identity": "main",
    }
    # Sem colunas adicionais - usa apenas campos do Job


class CrawlerJob(Job):
    """Crawler Job - web scraping"""
    __mapper_args__ = {
        "polymorphic_identity": "crawler",
    }
    # Usa crawler_config e crawler_schedule JSON
```

**Queries Automáticas:**

```python
# Query all jobs (mixed types)
all_jobs = session.query(Job).all()
# Returns: [ConversionJob(...), CrawlerJob(...), ...]

# Query only crawler jobs (automatic filter)
crawler_jobs = session.query(CrawlerJob).all()
# Automatically adds: WHERE job_type = 'crawler'

# Query by JSON field (MySQL 8.0+ JSON support)
from sqlalchemy import func

scheduled_crawlers = session.query(CrawlerJob).filter(
    func.json_extract(CrawlerJob.crawler_schedule, '$.type') == 'recurring',
    func.json_extract(CrawlerJob.crawler_schedule, '$.next_runs[0]') <= datetime.now().isoformat()
).all()
```

---

#### Arquivos Crawleados: Reutiliza Tabela `pages`

**Tabela `pages` existente** será reutilizada para armazenar páginas HTML crawleadas.

| Campo Existente | Uso no Crawler |
|----------------|----------------|
| `job_id` | FK para CrawlerJob execution |
| `page_number` | Ordem de descoberta da página |
| `url` | URL da página crawleada |
| `status` | Status do download (completed, failed) |
| `error_message` | Erros no download |
| `minio_path` | Path do HTML no MinIO |
| `created_at` | Timestamp |

**Para assets (CSS, JS, images):** Usar MinIO apenas, sem tabela (opcional indexar em Elasticsearch)

---

### 3.2 Elasticsearch (Busca + Analytics) - ⚠️ OPCIONAL

**🎯 Com STI:** Elasticsearch torna-se **opcional** - não é necessário para funcionalidade básica.

**Uso recomendado:**
- **Projeções/Views** dos dados MySQL para queries complexas
- Não é source of truth (MySQL é a fonte primária)
- Adicionar apenas se necessário para performance de busca/analytics

---

#### Index: `crawler-jobs-*` (OPCIONAL)
**Jobs de crawler indexados para busca avançada**

**Propósito:** Busca fuzzy de URLs, filtros, agregações (se necessário)

**Campos principais:**
- `job_id` (keyword)
- `user_id` (keyword)
- `name` (text + keyword)
- `url` (keyword)
- `url_pattern` (text com analyzer 'standard' para fuzzy match)
- `crawl_type` (keyword)
- `schedule_type`, `schedule_frequency` (keyword)
- `is_active`, `status` (keyword)
- `total_executions`, `successful_executions`, `failed_executions` (integer)
- `last_execution_at`, `next_run_at`, `created_at`, `updated_at` (date)
- `tags` (keyword multi-valued para filtros)

**Uso:**
- Buscar crawlers por URL similar (fuzzy matching)
- Detectar duplicatas via `url_pattern`
- Filtrar por status, tipo, usuário
- Agregações (crawlers por domínio, por status, etc.)

---

#### Index: `crawler-executions-*` (time-series)
**Histórico de execuções (time-series para analytics)**

**Propósito:** Análise histórica, métricas, dashboards

**Campos principais:**
- `execution_id` (keyword)
- `crawler_job_id` (keyword)
- `status` (keyword)
- `progress` (integer)
- `pages_discovered`, `pages_downloaded`, `pages_failed` (integer)
- `files_downloaded`, `files_failed`, `total_size_bytes` (integer)
- `files_by_type` (nested)
- `duration_seconds` (integer)
- `average_download_speed_mbps` (float)
- `started_at`, `completed_at` (date)

**Uso:**
- Análise de performance (velocidade, taxa de sucesso)
- Dashboards de métricas
- Queries temporais (últimas 24h, 7d, 30d)
- Agregações (execuções por status, por crawler, por período)

---

#### Index: `crawler-metrics-YYYY.MM.DD` (métricas tempo real)
**Métricas em tempo real de execução**

**Propósito:** Monitoramento ao vivo, troubleshooting

**Campos principais:**
- `execution_id` (keyword)
- `timestamp` (date)
- `progress_percentage` (float)
- `pages_processed`, `files_processed`, `bytes_downloaded` (integer)
- `download_speed_bps`, `response_time_ms` (float)
- `memory_mb`, `cpu_percent` (float)
- `error_count` (integer)
- `errors` (text multi-valued)

**Uso:**
- Rastreamento de progresso em tempo real
- Detecção de problemas (lentidão, erros)
- Análise de performance por execução
- Índices com TTL (deletar após N dias)

**Configuração:**
- `refresh_interval: 5s` (near real-time)
- `number_of_shards: 1` (baixo volume)
- ILM para rollover diário e deleção automática

---

### 3.3 Min.io (Storage)

#### Bucket: `ingestify-crawled`

**Estrutura de pastas:**
```
ingestify-crawled/
├── crawled/
│   ├── {execution_id_1}/
│   │   ├── pages/
│   │   │   ├── example.com_page1.html
│   │   │   └── example.com_page2.html
│   │   ├── assets/
│   │   │   ├── css/
│   │   │   │   └── style.css
│   │   │   ├── js/
│   │   │   │   └── app.js
│   │   │   ├── images/
│   │   │   │   ├── logo.png
│   │   │   │   └── banner.jpg
│   │   │   ├── fonts/
│   │   │   │   └── roboto.woff2
│   │   │   └── videos/
│   │   │       └── demo.mp4
│   │   ├── files/
│   │   │   ├── document1.pdf
│   │   │   ├── report.xlsx
│   │   │   └── data.csv
│   │   └── merged/
│   │       └── merged_{execution_id_1}.pdf
│   ├── {execution_id_2}/
│   │   ├── ...
```

**Políticas:**
- Public read para facilitar acesso (URLs públicas)
- Presigned URLs com expiração para segurança adicional (opcional)

**URLs públicas:**
- Formato: `http://minio_host:9000/ingestify-crawled/crawled/{execution_id}/files/{filename}`
- Armazenadas em `crawled_files.public_url`

---

### 3.4 Opções de Crawler Engine e Assets

#### 3.4.1 Crawler Engines

**Objetivo:** Permitir escolha da engine de crawling baseada nas necessidades do site.

| Engine | Quando Usar | Vantagens | Desvantagens |
|--------|-------------|-----------|--------------|
| **BeautifulSoup** | Sites estáticos, HTML puro | Rápido, leve, baixo consumo de recursos | Não executa JavaScript |
| **BeautifulSoup + Proxy** | Sites estáticos com restrição geográfica | Bypassa bloqueios regionais | Custo de proxy |
| **Playwright** | Sites com JavaScript, SPAs (React, Vue, Angular) | Renderiza JS, suporta interações complexas | Mais lento, maior consumo de recursos |
| **Playwright + Proxy** | Sites JS com restrição geográfica | Combina JS rendering + proxy | Mais lento, maior custo |

**Configuração:**
```json
{
  "crawler_engine": "BEAUTIFULSOUP",  // ou "PLAYWRIGHT"
  "use_proxy": false,
  "proxy_config": {
    "host": "proxy.example.com",
    "port": 8080,
    "username": "user",
    "password": "pass",
    "protocol": "http"  // ou "https", "socks5"
  }
}
```

**Casos de uso:**
- **Blog estático:** BeautifulSoup
- **Site React/Vue:** Playwright
- **Site bloqueado no BR:** BeautifulSoup + Proxy
- **Dashboard JS bloqueado:** Playwright + Proxy

---

#### 3.4.2 Asset Types (Download de Recursos)

**Objetivo:** Controlar quais recursos da página são baixados além do HTML.

**Opções:**

| Asset Type | Extensões | Exemplos | Uso |
|------------|-----------|----------|-----|
| **css** | .css | style.css, bootstrap.css | Estilos da página |
| **js** | .js | app.js, jquery.min.js | Scripts |
| **images** | .jpg, .jpeg, .png, .gif, .svg, .webp, .ico | logo.png, banner.jpg | Imagens |
| **fonts** | .woff, .woff2, .ttf, .otf, .eot | roboto.woff2 | Fontes customizadas |
| **videos** | .mp4, .webm, .ogg | demo.mp4, tutorial.webm | Vídeos embarcados |
| **documents** | .pdf, .docx, .xlsx, .pptx | manual.pdf, report.xlsx | Documentos linkados |

**Modos de configuração:**

**1. HTML Only (sem assets):**
```json
{
  "download_assets": false,
  "asset_types": []
}
```
- Baixa apenas o HTML
- Mais rápido
- Menor uso de storage
- Ideal para extração de texto

**2. HTML + Assets Selecionados:**
```json
{
  "download_assets": true,
  "asset_types": ["css", "images"]
}
```
- Baixa HTML + CSS + imagens
- Página pode ser visualizada offline (sem JS)
- Tamanho médio

**3. HTML + Todos os Assets:**
```json
{
  "download_assets": true,
  "asset_types": ["css", "js", "images", "fonts", "videos"]
}
```
- Download completo para navegação offline
- Maior tempo de download
- Maior uso de storage

**Lógica de download:**
- Assets são detectados via parsing de tags HTML: `<link>`, `<script>`, `<img>`, `<video>`, `@font-face`, etc.
- URLs são resolvidas para absolutos
- Downloads em paralelo (max: 10 simultâneos)
- Assets organizados por tipo em Min.io

**Estatísticas por tipo:**
```json
{
  "assets_downloaded": {
    "css": 5,
    "js": 12,
    "images": 34,
    "fonts": 3,
    "videos": 1
  },
  "total_assets_size_bytes": 15728640
}
```

---

### 3.5 Sistema de Retry com Fallback de Engines

#### 3.5.1 Objetivo

**Problema:** Sites podem falhar por diversos motivos (timeout, bloqueio, JavaScript não carregado, etc.)

**Solução:** Sistema inteligente de retry com **fallback progressivo de engines**, aumentando gradualmente a "potência" da engine até obter sucesso.

---

#### 3.5.2 Estratégia de Retry

**Conceito:** Cada retry usa uma engine diferente e mais robusta que a anterior.

**Exemplo prático:**
```
Tentativa 0 (inicial): BeautifulSoup (rápido, leve)
   ↓ FALHOU
Retry 1: BeautifulSoup + Proxy (bypassa geo-blocking)
   ↓ FALHOU
Retry 2: Playwright (renderiza JavaScript)
   ↓ FALHOU
Retry 3: Playwright + Proxy (máxima compatibilidade)
   ↓ SUCESSO ✅
```

---

#### 3.5.3 Configuração de Retry Strategy

**Estrutura JSON:**
```json
{
  "retry_enabled": true,
  "max_retries": 3,
  "retry_strategy": [
    {
      "attempt": 0,
      "engine": "BEAUTIFULSOUP",
      "use_proxy": false,
      "delay_seconds": 0
    },
    {
      "attempt": 1,
      "engine": "BEAUTIFULSOUP",
      "use_proxy": true,
      "delay_seconds": 5
    },
    {
      "attempt": 2,
      "engine": "PLAYWRIGHT",
      "use_proxy": false,
      "delay_seconds": 10
    },
    {
      "attempt": 3,
      "engine": "PLAYWRIGHT",
      "use_proxy": true,
      "delay_seconds": 15
    }
  ]
}
```

**Campos:**
- `attempt` - Número da tentativa (0 = primeira, 1 = retry 1, etc.)
- `engine` - Engine a usar (BEAUTIFULSOUP / PLAYWRIGHT)
- `use_proxy` - Se deve usar proxy nesta tentativa
- `delay_seconds` - Delay antes de executar (backoff exponencial)

---

#### 3.5.4 Estratégias Pré-definidas (Templates)

**1. Conservative (BeautifulSoup First)**
```json
{
  "name": "conservative",
  "max_retries": 3,
  "strategy": [
    {"attempt": 0, "engine": "BEAUTIFULSOUP", "use_proxy": false, "delay_seconds": 0},
    {"attempt": 1, "engine": "BEAUTIFULSOUP", "use_proxy": true, "delay_seconds": 5},
    {"attempt": 2, "engine": "PLAYWRIGHT", "use_proxy": false, "delay_seconds": 10},
    {"attempt": 3, "engine": "PLAYWRIGHT", "use_proxy": true, "delay_seconds": 15}
  ]
}
```
**Quando usar:** Sites com alta probabilidade de serem estáticos, proxy como fallback

---

**2. Aggressive (Playwright First)**
```json
{
  "name": "aggressive",
  "max_retries": 2,
  "strategy": [
    {"attempt": 0, "engine": "PLAYWRIGHT", "use_proxy": false, "delay_seconds": 0},
    {"attempt": 1, "engine": "PLAYWRIGHT", "use_proxy": true, "delay_seconds": 10},
    {"attempt": 2, "engine": "PLAYWRIGHT", "use_proxy": true, "delay_seconds": 20}
  ]
}
```
**Quando usar:** Sites JavaScript conhecidos (SPAs, dashboards)

---

**3. Proxy First**
```json
{
  "name": "proxy_first",
  "max_retries": 3,
  "strategy": [
    {"attempt": 0, "engine": "BEAUTIFULSOUP", "use_proxy": true, "delay_seconds": 0},
    {"attempt": 1, "engine": "BEAUTIFULSOUP", "use_proxy": true, "delay_seconds": 5},
    {"attempt": 2, "engine": "PLAYWRIGHT", "use_proxy": true, "delay_seconds": 10},
    {"attempt": 3, "engine": "PLAYWRIGHT", "use_proxy": true, "delay_seconds": 20}
  ]
}
```
**Quando usar:** Sites com geo-blocking conhecido

---

**4. Balanced (Mix)**
```json
{
  "name": "balanced",
  "max_retries": 4,
  "strategy": [
    {"attempt": 0, "engine": "BEAUTIFULSOUP", "use_proxy": false, "delay_seconds": 0},
    {"attempt": 1, "engine": "BEAUTIFULSOUP", "use_proxy": true, "delay_seconds": 3},
    {"attempt": 2, "engine": "PLAYWRIGHT", "use_proxy": false, "delay_seconds": 8},
    {"attempt": 3, "engine": "PLAYWRIGHT", "use_proxy": true, "delay_seconds": 15},
    {"attempt": 4, "engine": "PLAYWRIGHT", "use_proxy": true, "delay_seconds": 30}
  ]
}
```
**Quando usar:** Sites desconhecidos, máxima cobertura

---

#### 3.5.5 Histórico de Retry

**Rastreamento de tentativas:**

Cada tentativa é registrada em `retry_history`:

```json
{
  "retry_history": [
    {
      "attempt": 0,
      "engine": "BEAUTIFULSOUP",
      "use_proxy": false,
      "started_at": "2025-01-13T10:00:00Z",
      "completed_at": "2025-01-13T10:00:05Z",
      "status": "FAILED",
      "error_type": "TIMEOUT",
      "error_message": "Request timeout after 30s",
      "duration_seconds": 5
    },
    {
      "attempt": 1,
      "engine": "BEAUTIFULSOUP",
      "use_proxy": true,
      "started_at": "2025-01-13T10:00:10Z",
      "completed_at": "2025-01-13T10:00:12Z",
      "status": "FAILED",
      "error_type": "HTTP_ERROR",
      "error_message": "403 Forbidden",
      "duration_seconds": 2
    },
    {
      "attempt": 2,
      "engine": "PLAYWRIGHT",
      "use_proxy": false,
      "started_at": "2025-01-13T10:00:22Z",
      "completed_at": "2025-01-13T10:00:35Z",
      "status": "SUCCESS",
      "duration_seconds": 13
    }
  ],
  "retry_count": 2,
  "engine_used": "PLAYWRIGHT",
  "proxy_used": false,
  "total_duration_seconds": 20
}
```

---

#### 3.5.6 Lógica de Retry (Worker)

**Pseudocódigo:**

```
def execute_crawler_with_retry(crawler_job, execution):
    retry_strategy = crawler_job.retry_strategy

    for attempt_config in retry_strategy:
        attempt_num = attempt_config['attempt']
        engine = attempt_config['engine']
        use_proxy = attempt_config['use_proxy']
        delay = attempt_config['delay_seconds']

        # Wait delay (backoff)
        if delay > 0:
            sleep(delay)

        # Update execution
        execution.current_retry_attempt = attempt_num

        try:
            # Select engine adapter
            if engine == "BEAUTIFULSOUP":
                adapter = BeautifulSoupCrawlerAdapter(use_proxy=use_proxy)
            else:
                adapter = PlaywrightCrawlerAdapter(use_proxy=use_proxy)

            # Execute crawl
            result = adapter.crawl(crawler_job.url)

            # SUCCESS
            execution.engine_used = engine
            execution.proxy_used = use_proxy
            execution.status = "COMPLETED"
            log_retry_attempt(execution, attempt_num, "SUCCESS")
            return result

        except Exception as e:
            # FAILED
            log_retry_attempt(execution, attempt_num, "FAILED", error=e)
            execution.retry_count += 1

            # Last attempt?
            if attempt_num >= crawler_job.max_retries:
                execution.status = "FAILED"
                execution.error_message = f"All retries exhausted: {e}"
                raise

            # Continue to next retry
            continue
```

---

#### 3.5.7 Métricas de Retry

**Analytics em Elasticsearch:**

```json
{
  "retry_metrics": {
    "total_executions": 1000,
    "executions_with_retries": 250,
    "retry_rate": 25.0,
    "success_by_attempt": {
      "0": 750,
      "1": 150,
      "2": 75,
      "3": 25
    },
    "success_by_engine": {
      "BEAUTIFULSOUP": 800,
      "PLAYWRIGHT": 200
    },
    "average_retries_per_execution": 0.5,
    "most_common_errors": [
      {"type": "TIMEOUT", "count": 120},
      {"type": "HTTP_403", "count": 80},
      {"type": "JAVASCRIPT_ERROR", "count": 50}
    ]
  }
}
```

**Queries úteis:**

```
# Taxa de sucesso por tentativa
GET /crawler-executions-*/_search
{
  "aggs": {
    "by_attempt": {
      "terms": { "field": "current_retry_attempt" },
      "aggs": {
        "success_rate": {
          "filters": {
            "filters": {
              "success": { "term": { "status": "COMPLETED" } }
            }
          }
        }
      }
    }
  }
}

# Engine mais efetiva
GET /crawler-executions-*/_search
{
  "query": { "term": { "status": "COMPLETED" } },
  "aggs": {
    "by_engine": { "terms": { "field": "engine_used" } }
  }
}
```

---

#### 3.5.8 Benefícios do Sistema

✅ **Resiliência:** Não falha imediatamente, tenta múltiplas abordagens
✅ **Economia:** Começa com engine leve (BeautifulSoup) antes de usar Playwright
✅ **Flexibilidade:** Configurável por crawler (cada site tem suas particularidades)
✅ **Observabilidade:** Histórico completo de tentativas para análise
✅ **Smart Fallback:** Aumenta "potência" progressivamente (bs4 → bs4+proxy → pw → pw+proxy)
✅ **Backoff Exponencial:** Delays crescentes evitam sobrecarga

---

## 4. Domain Layer (Entidades e Serviços) - STI Pattern

### 4.1 Entities

#### CrawlerJob (extends Job)
**Especialização da entidade Job para crawlers agendados**

**🎯 Herança STI:**
```python
class CrawlerJob(Job):
    """
    Extends Job entity with crawler-specific behavior.
    Uses job_type='crawler' discriminator.
    """
    __mapper_args__ = {"polymorphic_identity": "crawler"}
```

**Campos herdados de Job:**
- `id` - UUID do crawler job
- `user_id` - Dono do crawler
- `source_url` - URL a ser crawleada
- `status` - Status atual (pending, running, completed, failed)
- `created_at`, `updated_at` - Timestamps
- `parent_job_id` - Para execuções, aponta para crawler principal

**Campos específicos (JSON):**
- `crawler_config` - Configuração de crawl (modo, engine, retry)
- `crawler_schedule` - Agendamento (tipo, cron, próximas execuções)

**Métodos específicos:**
- `activate()` - Ativar crawler (status = active)
- `pause()` - Pausar crawler (is_active = False, não executa)
- `stop()` - Parar permanentemente
- `update_schedule(schedule: CrawlerSchedule)` - Atualizar agendamento
- `schedule_next_execution()` - Criar próxima execução agendada
- `get_execution_history()` - Buscar jobs filhos (parent_job_id = self.id)

**Métodos herdados:**
- `is_running()` - Verificar se está em execução
- `is_completed()` - Verificar se finalizou
- `mark_failed(error)` - Marcar como falho
- `update_progress(percentage)` - Atualizar progresso

---

#### ⚠️ Execuções e Arquivos: Reuso de Jobs/Pages

**Crawler Executions:**
- São **Jobs normais** com `parent_job_id` apontando para o CrawlerJob
- Cada execução cria um novo Job filho
- Query: `SELECT * FROM jobs WHERE parent_job_id = 'crawler-uuid'`

**Crawled Files:**
- HTML pages são armazenados na tabela **pages** existente
- Assets (CSS, JS, images) são armazenados apenas no **MinIO**
- Não há necessidade de tabela separada

---

### 4.2 Value Objects (Immutable Dataclasses)

#### CrawlerConfig
**Configuração de crawl (armazenado em JSON)**

```python
@dataclass(frozen=True)
class CrawlerConfig:
    mode: CrawlerMode  # page_only, page_with_all, page_with_filtered, full_website
    crawler_engine: CrawlerEngine  # BEAUTIFULSOUP, PLAYWRIGHT
    asset_types: List[AssetType]  # [CSS, JS, IMAGES, etc.]
    retry_strategy: List[RetryStep]

    def to_json(self) -> dict:
        """Serialize to store in jobs.crawler_config"""

    @classmethod
    def from_json(cls, data: dict) -> "CrawlerConfig":
        """Deserialize from jobs.crawler_config"""
```

**Validações:**
- mode: Enum válido
- asset_types: Lista não vazia se mode != page_only
- retry_strategy: Lista ordenada por priority

---

#### CrawlerSchedule
**Configuração de agendamento (armazenado em JSON)**

```python
@dataclass(frozen=True)
class CrawlerSchedule:
    type: ScheduleType  # one_time, recurring
    cron_expression: Optional[str]  # Required if recurring
    timezone: str  # Default: UTC
    next_runs: List[datetime]  # Próximas 5 execuções

    def calculate_next_run(self) -> datetime:
        """Calculate next execution time from cron"""

    def to_json(self) -> dict:
        """Serialize to store in jobs.crawler_schedule"""

    @classmethod
    def from_json(cls, data: dict) -> "CrawlerSchedule":
        """Deserialize from jobs.crawler_schedule"""
```

**Validações:**
- Validar cron expression (croniter)
- type=recurring requires cron_expression
- timezone válido (pytz)

---

### 4.3 Domain Services

#### URLNormalizerService
**Normalização de URLs**

**Métodos:**
- `normalize_url(url)` - Normalizar para comparação exata
- `generate_pattern(url)` - Gerar padrão para fuzzy matching

---

#### DuplicateDetectorService
**Detecção de crawlers duplicados**

**Métodos:**
- `find_duplicates(url)` - Buscar crawlers com URL similar
- `has_duplicate(url)` - Verificar se existe duplicata

**Lógica:**
1. Normalizar URL
2. Gerar padrão
3. Query Elasticsearch com fuzzy match em `url_pattern`
4. Retornar lista de crawlers similares

---

#### CrawlerProgressService
**Cálculo de progresso**

**Métodos:**
- `calculate_progress(execution)` - Calcular progresso baseado em:
  - Páginas processadas
  - Arquivos baixados
  - Etapa atual (crawling, downloading, merging, uploading)

**Lógica:**
- Crawling: 0-20%
- Downloading: 20-80% (distribuído pelos arquivos)
- Merging PDFs: 80-90%
- Uploading Min.io: 90-100%

---

## 5. Application Layer (Use Cases)

### 5.1 CreateCrawlerJobUseCase
**Criar novo crawler agendado**

**Input:** CreateCrawlerJobDTO
- user_id, name, url
- crawl_type, file_extensions, pdf_handling
- schedule_type, cron_expression, timezone

**Fluxo:**
1. Validar URL (não permitir IPs internos, localhost)
2. Normalizar URL e gerar padrão
3. Verificar duplicatas (DuplicateDetectorService)
4. Criar entidade CrawlerJob
5. Salvar no MySQL (CrawlerJobRepository)
6. Indexar no Elasticsearch
7. Se recurring: Registrar no Celery Beat
8. Retornar CrawlerJobDTO

**Output:** CrawlerJobDTO

---

### 5.2 ExecuteCrawlerJobUseCase
**Executar crawler manualmente (run now)**

**Input:** crawler_job_id

**Fluxo:**
1. Buscar CrawlerJob no repositório
2. Validar se está ativo
3. Criar CrawlerExecution
4. Salvar no MySQL
5. Disparar task Celery (execute_crawler)
6. Atualizar execution com celery_task_id
7. Retornar CrawlerExecutionDTO

**Output:** CrawlerExecutionDTO

---

### 5.3 ListCrawlerJobsUseCase
**Listar crawlers do usuário**

**Input:** user_id, filters (status, type, search)

**Fluxo:**
1. Query no repositório com filtros
2. Ordenar por created_at DESC
3. Paginação (limit, offset)
4. Converter para DTOs

**Output:** List[CrawlerJobDTO]

---

### 5.4 UpdateCrawlerJobUseCase
**Atualizar configuração de crawler**

**Input:** crawler_job_id, UpdateCrawlerJobDTO
- name, cron_expression, file_extensions, is_active

**Fluxo:**
1. Buscar CrawlerJob
2. Validar permissões (user_id)
3. Atualizar campos
4. Atualizar no MySQL
5. Atualizar índice Elasticsearch
6. Se mudou cron: Atualizar Celery Beat schedule
7. Retornar CrawlerJobDTO atualizado

**Output:** CrawlerJobDTO

---

### 5.5 GetCrawlerExecutionHistoryUseCase
**Obter histórico de execuções**

**Input:** crawler_job_id, filters (status, date_range)

**Fluxo:**
1. Buscar execuções no repositório
2. Ordenar por started_at DESC
3. Paginação
4. Enriquecer com estatísticas (success_rate, avg_duration)
5. Converter para DTOs

**Output:** List[CrawlerExecutionDTO]

---

### 5.6 PauseCrawlerJobUseCase
**Pausar crawler (não executa, mas mantém config)**

**Input:** crawler_job_id

**Fluxo:**
1. Buscar CrawlerJob
2. Validar permissões
3. `crawler_job.pause()` - altera is_active=False, status=PAUSED
4. Atualizar no MySQL
5. Remover do Celery Beat schedule (se recurring)
6. Cancelar execuções em andamento (opcional)

**Output:** CrawlerJobDTO

---

## 6. Infrastructure Layer - STI Pattern (Reuso)

### 6.1 Repositories (MySQL) - ✅ Reuso Total

#### ✅ Reuso: MySQLJobRepository (Existente)
**Já suporta polimorfismo via STI - nenhuma mudança necessária**

**Métodos existentes que funcionam para CrawlerJob:**
- `save(job)` - Criar/atualizar (funciona para CrawlerJob automaticamente)
- `find_by_id(id)` - Buscar por ID (retorna CrawlerJob se job_type='crawler')
- `find_by_user_id(user_id)` - Buscar por usuário
- `delete(id)` - Deletar

**Métodos novos específicos para crawler:**
```python
class MySQLJobRepository(JobRepository):
    # ... métodos existentes ...

    def find_crawler_jobs(self, user_id: str, filters: dict) -> List[CrawlerJob]:
        """Find crawler jobs with optional filters"""
        query = self.session.query(Job).filter(
            Job.user_id == user_id,
            Job.job_type == "crawler"
        )
        # Apply filters (status, search, etc.)
        return query.all()

    def find_active_crawlers(self) -> List[CrawlerJob]:
        """Find active crawlers for Celery Beat scheduling"""
        return self.session.query(Job).filter(
            Job.job_type == "crawler",
            Job.status == "active"
        ).all()

    def find_crawler_executions(self, crawler_job_id: str) -> List[Job]:
        """Find execution history (jobs with parent_job_id = crawler_job_id)"""
        return self.session.query(Job).filter(
            Job.parent_job_id == crawler_job_id
        ).order_by(Job.created_at.desc()).all()
```

**🎯 Vantagens STI:**
- Zero novas tabelas
- Zero novos repositórios
- Queries polimórficas automáticas pelo SQLAlchemy
- Todas as operações CRUD reutilizadas

---

#### ✅ Reuso: MySQLPageRepository (Existente)
**Já armazena páginas crawleadas - nenhuma mudança necessária**

**Uso para crawler:**
- HTML pages crawleadas são salvas como **Page** entities
- `job_id` aponta para o CrawlerJob execution
- `page_number` pode ser sequencial (1, 2, 3...) ou URL hash
- `content` armazena HTML source

**Métodos existentes que funcionam:**
- `save(page)` - Salvar página crawleada
- `find_by_job_id(job_id)` - Listar páginas de uma execução
- `count_by_job_id(job_id)` - Contar páginas crawleadas

---

### 6.2 Adapters

#### BeautifulSoupCrawlerAdapter
**Implementação do CrawlerPort (scraping)**

**Responsabilidades:**
- Fazer requests HTTP (httpx)
- Parse HTML (BeautifulSoup)
- Extrair links (com filtro por extensão)
- Download de arquivos binários
- Respeitar rate limits
- Respeitar robots.txt (opcional)

**Métodos:**
- `crawl_page(url, file_extensions)` - Crawl página e extrair links
- `download_file(url, destination)` - Download arquivo binário
- `close()` - Fechar cliente HTTP

---

#### PyPDFMergerAdapter
**Implementação do PDFMergerPort**

**Responsabilidades:**
- Merge de múltiplos PDFs em um único arquivo
- Adicionar bookmarks (TOC)
- Preservar metadados
- Compressão (opcional)

**Métodos:**
- `merge_pdfs(pdf_files, output_path)` - Merge lista de PDFs
- `add_bookmarks(pdf, bookmarks)` - Adicionar TOC

---

#### MinioCrawlerStorageAdapter
**Storage de arquivos crawleados**

**Responsabilidades:**
- Upload de arquivos para Min.io
- Upload de páginas HTML
- Gerar URLs públicas
- Organizar estrutura de pastas

**Métodos:**
- `upload_crawled_file(execution_id, filename, file_path)` - Upload arquivo
- `upload_html_page(execution_id, url, html_content)` - Upload HTML
- `get_execution_folder(execution_id)` - Path da pasta

---

### 6.3 Elasticsearch Storage

#### CrawlerJobIndex
**Indexação de jobs**

**Responsabilidades:**
- Indexar novos jobs
- Atualizar jobs existentes
- Busca fuzzy por url_pattern
- Filtros e agregações

**Métodos:**
- `index_crawler_job(job)` - Indexar
- `update_crawler_job(job)` - Atualizar
- `search_by_url_pattern(pattern)` - Busca fuzzy
- `find_active_jobs()` - Jobs ativos

#### CrawlerExecutionIndex
**Indexação de execuções (time-series)**

**Responsabilidades:**
- Indexar execuções completas
- Queries temporais
- Agregações (sucesso/falha, duration)

#### CrawlerMetricsIndex
**Métricas tempo real**

**Responsabilidades:**
- Indexar métricas durante execução (bulk)
- Queries de progresso
- ILM para deleção automática

---

## 7. Workers Celery

### 7.1 Tasks

#### execute_crawler
**Task principal: Executar crawler**

**Responsabilidades:**
1. Buscar CrawlerJob e CrawlerExecution no MySQL
2. Instanciar CrawlerScraper
3. Executar scraping completo
4. Atualizar status e estatísticas
5. Indexar métricas no Elasticsearch
6. Tratamento de erros e retry

**Fila:** `crawler` (isolada do resto do sistema)

---

#### schedule_crawler
**Task Beat: Agendar execução (triggered por Celery Beat)**

**Responsabilidades:**
1. Buscar CrawlerJob
2. Verificar se está ativo
3. Criar nova CrawlerExecution
4. Disparar execute_crawler task
5. Atualizar next_run_at

**Fila:** `beat` (Celery Beat scheduler)

---

### 7.2 Worker Logic

#### CrawlerScraper
**Orquestração do crawl**

**Fluxo de execução:**
```
1. Crawl página principal (BeautifulSoup)
   - Parse HTML
   - Extrair links
   - Salvar HTML no Min.io (opcional)

2. Filtrar links por extensão
   - file_extensions config
   - extension_categories

3. Download arquivos em paralelo
   - httpx async requests
   - Salvar em /tmp temporário
   - Registrar CrawledFile no MySQL

4. Processar PDFs (se pdf_handling != INDIVIDUAL)
   - Merge PDFs com PyPDF2
   - Adicionar bookmarks
   - Comprimir (opcional)

5. Upload para Min.io
   - Upload todos os arquivos
   - Estrutura: crawled/{execution_id}/
   - Gerar URLs públicas
   - Atualizar CrawledFile.public_url

6. Atualizar progresso (0-100%)
   - Atualizar MySQL
   - Indexar métricas no Elasticsearch (bulk)

7. Cleanup
   - Deletar arquivos temporários
   - Marcar como COMPLETED
```

---

#### FileDownloader
**Download paralelo de arquivos**

**Responsabilidades:**
- Download assíncrono (httpx AsyncClient)
- Pool de workers (max_concurrent_downloads)
- Retry automático (3 tentativas)
- Progress tracking
- Error handling

---

#### PDFProcessor
**Processamento de PDFs**

**Responsabilidades:**
- Identificar PDFs baixados
- Merge (se pdf_handling == COMBINED ou BOTH)
- Validar PDFs (não corrompidos)
- Otimização/compressão (opcional)

---

#### ProgressTracker
**Rastreamento de progresso em tempo real**

**Responsabilidades:**
- Calcular progresso baseado em etapas
- Atualizar MySQL (execution.progress)
- Indexar métricas no Elasticsearch (bulk, a cada 5s)
- Publicar no Redis (para WebSocket real-time, opcional)

---

## 8. API Endpoints

### 8.1 Crawlers Management

| Método | Endpoint | Descrição | Auth |
|--------|----------|-----------|------|
| POST | `/crawlers` | Criar novo crawler | JWT/API Key |
| GET | `/crawlers` | Listar crawlers do usuário | JWT/API Key |
| GET | `/crawlers/{id}` | Obter detalhes de um crawler | JWT/API Key |
| PATCH | `/crawlers/{id}` | Atualizar configuração | JWT/API Key |
| DELETE | `/crawlers/{id}` | Deletar crawler | JWT/API Key |
| POST | `/crawlers/{id}/execute` | Executar manualmente (run now) | JWT/API Key |
| PATCH | `/crawlers/{id}/pause` | Pausar crawler | JWT/API Key |
| PATCH | `/crawlers/{id}/resume` | Retomar crawler pausado | JWT/API Key |

### 8.2 Executions & History

| Método | Endpoint | Descrição | Auth |
|--------|----------|-----------|------|
| GET | `/crawlers/{id}/executions` | Listar execuções de um crawler | JWT/API Key |
| GET | `/crawlers/{id}/executions/{exec_id}` | Obter detalhes de uma execução | JWT/API Key |
| GET | `/crawlers/{id}/executions/{exec_id}/files` | Listar arquivos baixados | JWT/API Key |
| GET | `/crawlers/{id}/executions/{exec_id}/progress` | Progresso em tempo real | JWT/API Key |
| POST | `/crawlers/{id}/executions/{exec_id}/cancel` | Cancelar execução em andamento | JWT/API Key |

### 8.3 Analytics & Search

| Método | Endpoint | Descrição | Auth |
|--------|----------|-----------|------|
| GET | `/crawlers/search` | Buscar crawlers por URL/padrão | JWT/API Key |
| GET | `/crawlers/stats` | Estatísticas gerais | JWT/API Key |
| GET | `/crawlers/{id}/stats` | Estatísticas de um crawler | JWT/API Key |

---

## 9. Fluxos de Execução

### 9.1 Criar Crawler Agendado

```
1. Frontend/User → POST /crawlers
   Body: {
     name: "Crawl Example.com PDFs",
     url: "https://example.com/docs",
     crawl_type: "page_with_filtered",
     file_extensions: ["pdf"],
     pdf_handling: "both",
     schedule_type: "recurring",
     schedule_frequency: "daily",
     cron_expression: "0 9 * * *",  // Daily at 9 AM
     timezone: "America/Sao_Paulo"
   }

2. API → CreateCrawlerJobUseCase.execute()
   ├─ Validar URL (não localhost, não IPs internos)
   ├─ Normalizar URL e gerar padrão
   ├─ DuplicateDetectorService.find_duplicates()
   │   └─ Query Elasticsearch (fuzzy match em url_pattern)
   ├─ Criar CrawlerJob entity
   ├─ CrawlerJobRepository.save() → MySQL
   ├─ Elasticsearch.index_crawler_job()
   ├─ Se recurring:
   │   └─ Celery Beat: Registrar schedule
   │       └─ beat_schedule['crawler-{id}'] = {
   │             'task': 'schedule_crawler',
   │             'schedule': crontab(...),
   │             'args': (crawler_job_id,)
   │           }
   └─ Retornar CrawlerJobResponse

3. Frontend ← 201 Created
   Body: {
     id: "crawler-123",
     name: "Crawl Example.com PDFs",
     status: "ACTIVE",
     next_run_at: "2025-01-14T09:00:00-03:00",
     ...
   }
```

---

### 9.2 Execução Automática (Celery Beat)

```
1. Celery Beat → Trigger schedule_crawler task
   (triggered by cron: 0 9 * * *)
   ↓
2. schedule_crawler(crawler_job_id)
   ├─ Buscar CrawlerJob no MySQL
   ├─ Verificar is_active == True
   ├─ Criar CrawlerExecution (status=PENDING)
   ├─ Salvar no MySQL
   └─ Disparar execute_crawler.apply_async()
       └─ Fila: 'crawler'
   ↓
3. Celery Worker pega execute_crawler task
   ↓
4. execute_crawler(crawler_job_id, execution_id)
   ├─ Buscar CrawlerJob e CrawlerExecution no MySQL
   ├─ Atualizar execution.celery_task_id
   ├─ Atualizar execution.status = PROCESSING
   └─ CrawlerScraper(job, execution).run()
       ↓
       ├─ [10%] Crawl página principal
       │   ├─ httpx.get(url)
       │   ├─ BeautifulSoup.parse()
       │   ├─ Extrair links
       │   └─ Salvar HTML no Min.io (opcional)
       ↓
       ├─ [20%] Filtrar links por extensão
       │   └─ file_extensions: ["pdf"]
       ↓
       ├─ [30-80%] Download arquivos em paralelo
       │   ├─ FileDownloader.download_all(urls)
       │   ├─ Para cada arquivo:
       │   │   ├─ httpx.get(url) → /tmp
       │   │   ├─ CrawledFileRepository.save()
       │   │   └─ ProgressTracker.update(%)
       │   └─ Elasticsearch.bulk_index_metrics()
       ↓
       ├─ [80-90%] Processar PDFs (se pdf_handling != INDIVIDUAL)
       │   ├─ PDFProcessor.merge_pdfs()
       │   └─ Salvar merged.pdf em /tmp
       ↓
       ├─ [90-100%] Upload para Min.io
       │   ├─ Para cada arquivo em /tmp:
       │   │   ├─ MinioCrawlerStorageAdapter.upload()
       │   │   │   └─ Path: crawled/{execution_id}/files/{filename}
       │   │   ├─ Gerar public_url
       │   │   └─ Atualizar CrawledFile.public_url
       │   └─ Atualizar execution.minio_folder_path
       ↓
       └─ [100%] Finalizar
           ├─ execution.status = COMPLETED
           ├─ execution.completed_at = now()
           ├─ crawler_job.total_executions += 1
           ├─ crawler_job.successful_executions += 1
           ├─ crawler_job.last_execution_at = now()
           ├─ MySQL: commit()
           ├─ Elasticsearch: index_execution()
           └─ Cleanup /tmp

5. Frontend pode consultar:
   GET /crawlers/{id}/executions/{execution_id}
   ↓
   Response: {
     id: "exec-456",
     status: "COMPLETED",
     progress: 100,
     files_downloaded: 10,
     minio_folder_path: "crawled/exec-456/",
     files: [
       {
         filename: "document1.pdf",
         public_url: "http://minio:9000/ingestify-crawled/crawled/exec-456/files/document1.pdf"
       },
       ...
     ]
   }
```

---

### 9.3 Execução Manual (Run Now)

```
1. Frontend → POST /crawlers/{id}/execute
   ↓
2. ExecuteCrawlerJobUseCase.execute(crawler_job_id)
   ├─ Buscar CrawlerJob
   ├─ Validar is_active == True
   ├─ Criar CrawlerExecution
   ├─ Salvar no MySQL
   └─ Disparar execute_crawler.apply_async()
   ↓
3. Fluxo idêntico ao 9.2 a partir do passo 3
```

---

### 9.4 Pausar Crawler

```
1. Frontend → PATCH /crawlers/{id}/pause
   ↓
2. PauseCrawlerJobUseCase.execute(crawler_job_id)
   ├─ Buscar CrawlerJob
   ├─ crawler_job.pause()
   │   ├─ is_active = False
   │   └─ status = PAUSED
   ├─ CrawlerJobRepository.update()
   ├─ Elasticsearch.update_crawler_job()
   ├─ Se recurring:
   │   └─ Celery Beat: Remover schedule
   │       └─ del beat_schedule['crawler-{id}']
   └─ (Opcional) Cancelar execuções em andamento
       └─ celery_app.control.revoke(task_id)
   ↓
3. Frontend ← 200 OK
   Body: {
     id: "crawler-123",
     status: "PAUSED",
     is_active: false,
     ...
   }
```

---

## 10. Detecção de Duplicatas

### 10.1 Funcionamento

**Objetivo:** Avisar usuário quando tenta criar crawler com URL similar a um existente.

**Fluxo:**
```
1. Usuário tenta criar crawler com URL: https://example.com/docs?page=1

2. URLNormalizerService.generate_pattern(url)
   └─ Output: "example.com/docs?*"

3. DuplicateDetectorService.find_duplicates(url)
   ├─ Query Elasticsearch:
   │   GET /crawler-jobs-*/_search
   │   {
   │     "query": {
   │       "match": {
   │         "url_pattern": {
   │           "query": "example.com/docs?*",
   │           "fuzziness": "AUTO"
   │         }
   │       }
   │     }
   │   }
   └─ Retorna lista de crawlers similares

4. Se duplicatas encontradas:
   └─ Retornar warning na resposta:
       {
         "id": "crawler-new",
         "warnings": [
           {
             "type": "duplicate_detected",
             "message": "Similar crawler already exists",
             "existing_crawlers": [
               {
                 "id": "crawler-123",
                 "name": "Existing Crawler",
                 "url": "https://example.com/docs?page=2",
                 "status": "ACTIVE"
               }
             ]
           }
         ]
       }

5. Frontend exibe aviso e opções:
   - "Ver crawler existente"
   - "Criar mesmo assim"
   - "Cancelar"
```

**Nota:** Não bloqueia criação, apenas avisa.

---

## 11. Monitoramento e Métricas

### 11.1 Métricas em Tempo Real (via Elasticsearch)

**Queries úteis:**

**1. Total de crawlers ativos:**
```
GET /crawler-jobs-*/_search
{
  "query": { "term": { "is_active": true } },
  "size": 0
}
```

**2. Execuções por status (últimas 24h):**
```
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

**3. Taxa de sucesso (últimos 7 dias):**
```
GET /crawler-executions-*/_search
{
  "query": {
    "range": { "started_at": { "gte": "now-7d" } }
  },
  "aggs": {
    "success_rate": {
      "filters": {
        "filters": {
          "successful": { "term": { "status": "COMPLETED" } },
          "failed": { "term": { "status": "FAILED" } }
        }
      }
    }
  }
}
```

**4. Progresso de execução em tempo real:**
```
GET /crawler-metrics-*/_search
{
  "query": {
    "term": { "execution_id": "exec-456" }
  },
  "sort": [{ "timestamp": "desc" }],
  "size": 1
}
```

---

### 11.2 Logs Estruturados

**Formato:** JSON com contexto

**Exemplo:**
```json
{
  "timestamp": "2025-01-14T09:15:23Z",
  "level": "INFO",
  "event": "crawler_execution_completed",
  "crawler_job_id": "crawler-123",
  "execution_id": "exec-456",
  "duration_seconds": 125,
  "files_downloaded": 10,
  "total_size_bytes": 5242880
}
```

---

## 12. Segurança

### 12.1 Validações de URL

**Blacklist (não permitir):**
- `localhost`, `127.0.0.1`, `0.0.0.0`
- IPs privados (10.x, 172.16.x, 192.168.x)
- IPs de metadados cloud (169.254.169.254)
- URLs com usuário:senha (http://user:pass@example.com)

**Validações:**
- Protocolo: apenas http/https
- Domínio: deve ser válido (DNS resolvível)

---

### 12.2 Rate Limiting

**Por crawler:**
- `crawler_rate_limit_per_second`: 2 requests/s (default)
- Delay entre requests: 500ms

**Global:**
- Max concurrent crawlers: ilimitado (controlado por workers Celery)
- Max concurrent downloads per crawler: 5 (config)

---

### 12.3 Autenticação e Autorização

**Todos os endpoints protegidos:**
- JWT Token (user sessions)
- API Key (programmatic access)

**Isolamento de dados:**
- Usuários só veem seus próprios crawlers
- Filtro automático por `user_id` em queries

---

### 12.4 Storage Security

**Min.io:**
- Public read apenas para bucket `ingestify-crawled`
- Presigned URLs com expiração (opcional para segurança extra)
- Isolamento por `execution_id` (cada execução em pasta separada)

---

## 13. Configuração (backend/shared/config.py)

Adicionar ao `Settings`:

```python
# Crawler Configuration
crawler_enabled: bool = True  # Feature flag
crawler_max_concurrent_downloads: int = 5
crawler_max_concurrent_assets: int = 10  # Downloads de assets em paralelo
crawler_download_timeout_seconds: int = 60
crawler_user_agent: str = "IngestifyBot/1.0"
crawler_respect_robots_txt: bool = True
crawler_rate_limit_per_second: int = 2

# Crawler Engine Defaults
crawler_default_engine: str = "beautifulsoup"  # beautifulsoup ou playwright

# Playwright Configuration
playwright_headless: bool = True  # Rodar sem interface gráfica
playwright_timeout_seconds: int = 30  # Timeout para JS rendering
playwright_wait_for_selector: str = ""  # Opcional: esperar por elemento
playwright_browser_type: str = "chromium"  # chromium, firefox, webkit

# Proxy Configuration
proxy_enabled: bool = False  # Feature flag global
proxy_pool_enabled: bool = False  # Usar pool de proxies (rotação)
proxy_rotation_strategy: str = "round_robin"  # round_robin, random, least_used

# Retry Configuration
crawler_retry_enabled: bool = True  # Feature flag para retries
crawler_max_retries: int = 3  # Máximo de retries por execução
crawler_retry_delay_base_seconds: int = 5  # Base para backoff exponencial
crawler_retry_strategy_default: str = "conservative"  # conservative, aggressive, proxy_first, balanced

# MinIO Buckets (novo)
minio_bucket_crawled: str = "ingestify-crawled"
```

---

## 14. Dependências (requirements.txt)

Adicionar:

```txt
# Web Scraping - BeautifulSoup
beautifulsoup4>=4.12.0
httpx>=0.27.0
lxml>=5.0.0

# Web Scraping - Playwright (JavaScript rendering)
playwright>=1.40.0
# Instalar browsers: python -m playwright install chromium

# Proxy Support
httpx[socks]>=0.27.0  # SOCKS proxy support
python-socks>=2.4.0

# PDF Processing
PyPDF2>=3.0.0

# Cron Parsing
croniter>=2.0.0
```

**Notas:**
- Playwright requer instalação de browsers: `python -m playwright install chromium`
- httpx[socks] adiciona suporte a proxies SOCKS5
- Playwright consome ~200MB de espaço (browser Chromium)

---

## 15. Database Migrations (Alembic)

**Comandos:**
```bash
# Gerar migration
alembic revision --autogenerate -m "Add crawler tables"

# Aplicar migration
alembic upgrade head
```

**Migration criará:**
- Tabela `crawler_jobs`
- Tabela `crawler_executions`
- Tabela `crawled_files`
- Índices (user_id, url_pattern, status, created_at, etc.)
- Foreign keys e constraints

---

## 16. Cronograma de Implementação

### Sprint 1 (Semana 1-2): Foundation & Data Models - STI Pattern
**Objetivo:** Estrutura de dados com reuso máximo (STI)

**🎯 Mudança arquitetural:** Single Table Inheritance - reuso da tabela `jobs` existente

**Tarefas:**
- ✅ **Migration Alembic:** Adicionar 2 colunas JSON (crawler_config, crawler_schedule)
- ✅ **Domain entities:** CrawlerJob extends Job (polimorfismo STI)
- ✅ **Value Objects:** CrawlerConfig, CrawlerSchedule (immutable dataclasses)
- ✅ **Extend JobRepository:** Adicionar métodos find_crawler_jobs(), find_active_crawlers()
- ✅ **Configurar Alembic:** target_metadata = Base.metadata (SQLAlchemy)
- ✅ **Testes unitários:** Domain layer (CrawlerJob, value objects)

**Entregável:** STI funcionando + migration aplicada

**📉 Redução de escopo vs plano original:**
- 3 tabelas novas → 0 tabelas novas (apenas 2 colunas JSON)
- 3 repositories novos → 0 repositories novos (extensão do existente)
- 3 indices ES novos → Opcional (projeções/views se necessário)

**Estimativa:** 6-8h (vs 12h do plano original)

---

### Sprint 2 (Semana 3-4): Infrastructure & Repositories
**Objetivo:** Camada de infraestrutura completa

- ✅ Repositories MySQL (CrawlerJob, CrawlerExecution, CrawledFile)
- ✅ Elasticsearch adapters (indexação, busca, métricas)
- ✅ BeautifulSoup crawler adapter (scraping + download)
- ✅ PyPDF merger adapter (merge de PDFs)
- ✅ Min.io crawler storage adapter (upload, public URLs)
- ✅ Bucket `ingestify-crawled` configurado
- ✅ Testes de integração (repositories + adapters)

**Entregável:** Infrastructure layer testada

---

### Sprint 3 (Semana 5-6): Application Layer & Use Cases
**Objetivo:** Lógica de negócio

- ✅ Use Cases:
  - CreateCrawlerJobUseCase
  - ExecuteCrawlerJobUseCase
  - ListCrawlerJobsUseCase
  - UpdateCrawlerJobUseCase
  - PauseCrawlerJobUseCase
  - GetCrawlerExecutionHistoryUseCase
- ✅ DTOs (CrawlerJobDTO, CrawlerExecutionDTO, CrawledFileDTO)
- ✅ Testes unitários (use cases)

**Entregável:** Use cases funcionando com mocks

---

### Sprint 4 (Semana 7-8): Workers Celery
**Objetivo:** Execução de crawls

- ✅ Celery tasks (execute_crawler, schedule_crawler)
- ✅ CrawlerScraper (orquestração do crawl)
- ✅ FileDownloader (download paralelo)
- ✅ PDFProcessor (merge de PDFs)
- ✅ ProgressTracker (atualização tempo real)
- ✅ Celery Beat integration (agendamento recurring)
- ✅ Testes end-to-end (workers)

**Entregável:** Crawls executando com sucesso

---

### Sprint 5 (Semana 9-10): API & Presentation Layer
**Objetivo:** Endpoints REST

- ✅ CrawlerController (todos os endpoints)
- ✅ Request/Response schemas (Pydantic)
- ✅ Dependency injection (use cases)
- ✅ Autenticação (JWT/API Key)
- ✅ Validações e error handling
- ✅ Documentação OpenAPI (Swagger)
- ✅ Testes de API (pytest + httpx)

**Entregável:** API completa e documentada

---

### Sprint 6 (Semana 11-12): Testing, Monitoring & Documentation
**Objetivo:** Qualidade e observabilidade

- ✅ Testes E2E (fluxos completos)
- ✅ Métricas Elasticsearch (queries, dashboards)
- ✅ Logs estruturados (structlog)
- ✅ Alertas (falhas, lentidão)
- ✅ Documentação completa:
  - README do módulo crawler
  - Guia de uso (API docs)
  - Troubleshooting
- ✅ Performance tuning (Celery, Elasticsearch)

**Entregável:** Sistema pronto para produção

---

**Total:** 12 semanas (3 meses)

**Milestones:**
- Semana 2: Data models ✅
- Semana 4: Infrastructure ✅
- Semana 6: Business logic ✅
- Semana 8: Workers funcionando ✅
- Semana 10: API completa ✅
- Semana 12: **Production ready** 🚀

---

## 17. Riscos e Mitigações

| Risco | Impacto | Probabilidade | Mitigação |
|-------|---------|---------------|-----------|
| Website bloqueia scraper | Alto | Médio | User-agent rotation, rate limiting, respeitar robots.txt |
| Crawls muito lentos | Médio | Baixo | Download paralelo, workers escaláveis, timeout configs |
| PDFs corrompidos no merge | Médio | Baixo | Validação antes de merge, try/catch, skip corrupted |
| Disk space (/tmp) cheio | Alto | Baixo | Cleanup after each execution, monitorar disk space |
| Elasticsearch lento | Médio | Baixo | Índices time-series, ILM, sharding adequado |
| Celery Beat não dispara | Alto | Baixo | Health check task, logs, monitorar Beat |

---

## 18. Métricas de Sucesso

### 18.1 KPIs

- **Uptime:** 99.5% dos crawlers agendados executam no horário
- **Success Rate:** 95%+ das execuções completam sem erros
- **Performance:** Média de 10 arquivos/minuto por crawler
- **Latency:** <2s para criação de crawler via API
- **Storage:** <100MB por execução (média)

### 18.2 Monitoramento

- Dashboard Elasticsearch (Kibana ou custom)
- Alertas para falhas recorrentes
- Logs centralizados (structlog + aggregator)
- Health checks periódicos

---

## 19. Melhorias Futuras (Post-MVP)

### Phase 2
- Dashboard visual React (frontend)
- WebSocket para progresso real-time
- Suporte a JavaScript rendering (Playwright)
- Webhooks para notificações
- Export de dados (CSV, JSON, Excel)

### Phase 3
- Crawling distribuído (múltiplos workers em paralelo)
- Change detection (diff entre execuções)
- IA para extração de conteúdo (LLMs)
- Integração com Google Drive/Dropbox (upload de resultados)
- OCR para imagens (Tesseract)

---

## 20. Conclusão

### 20.1 Resumo

Este plano de integração:

✅ **Reutiliza 100% da infraestrutura existente**
✅ **Segue Clean Architecture** (domain, application, infrastructure, presentation)
✅ **Mantém consistência** com sistema de Jobs existente
✅ **Escalável** (workers Celery, Elasticsearch time-series)
✅ **Testável** (unit, integration, e2e)
✅ **Observável** (métricas Elasticsearch, logs estruturados)
✅ **Seguro** (auth, rate limiting, validações)
✅ **Flexível**:
  - **4 engines de crawling** (BeautifulSoup, BeautifulSoup+Proxy, Playwright, Playwright+Proxy)
  - **Download granular de assets** (HTML only ou por tipo: CSS, JS, images, fonts, videos)
  - **Suporte a proxies** (HTTP, HTTPS, SOCKS5) com autenticação
  - **JavaScript rendering** (Playwright para SPAs e sites dinâmicos)
✅ **Resiliente**:
  - **Sistema de retry inteligente** com fallback progressivo de engines
  - **4 estratégias pré-definidas** (conservative, aggressive, proxy_first, balanced)
  - **Backoff exponencial** com delays crescentes
  - **Histórico completo** de tentativas para análise e otimização

### 20.2 Próximos Passos

1. ✅ **Aprovar este plano** (revisar e validar arquitetura)
2. 🔲 Criar branch `feature/crawler-integration`
3. 🔲 Implementar Sprint 1 (Foundation)
4. 🔲 Iterar com feedback e ajustes
5. 🔲 Deploy em produção após Sprint 6

---

**Documento criado por:** Claude Code
**Data:** 2025-01-13
**Última atualização:** 2025-01-13
**Status:** ✅ Aguardando aprovação
**Versão:** 1.2

---

## Changelog

### v1.2 (2025-01-13) - Sistema de Retry Inteligente
- ✅ **Sistema de retry com fallback de engines**
  - Retry progressivo: BS4 → BS4+Proxy → Playwright → Playwright+Proxy
  - Configurável via `retry_strategy` JSON
  - Backoff exponencial com delays crescentes
- ✅ **4 estratégias pré-definidas (templates)**
  - Conservative (BS4 first)
  - Aggressive (Playwright first)
  - Proxy First (sempre com proxy)
  - Balanced (mix de todas)
- ✅ **Rastreamento completo de retries**
  - Campo `retry_history` com histórico JSON
  - Campos `retry_count`, `current_retry_attempt`, `engine_used`, `proxy_used`
  - Métricas de retry em Elasticsearch
- ✅ **Configurações de retry**
  - `crawler_retry_enabled`, `crawler_max_retries`, `crawler_retry_strategy_default`
- ✅ **Documentação completa**
  - Seção 3.5 - Sistema de Retry com Fallback
  - Pseudocódigo de implementação
  - Queries de analytics

### v1.1 (2025-01-13) - Engines e Assets Flexíveis
- ✅ Adicionado suporte a múltiplas engines (BeautifulSoup/Playwright)
- ✅ Adicionado suporte a proxies (HTTP, HTTPS, SOCKS5)
- ✅ Adicionado download granular de assets (CSS, JS, images, fonts, videos)
- ✅ Adicionado modo "HTML only" (sem assets)
- ✅ Atualizado modelo de dados com novos campos
- ✅ Atualizado dependências (playwright, httpx[socks], python-socks)
- ✅ Atualizado configuração com settings de Playwright e proxies

### v1.0 (2025-01-13) - Plano Inicial
- ✅ Arquitetura Clean Architecture completa
- ✅ Modelos de dados (MySQL + Elasticsearch + Min.io)
- ✅ Domain Layer, Application Layer, Infrastructure Layer
- ✅ Workers Celery com agendamento
- ✅ API REST endpoints
- ✅ Cronograma de 12 semanas (6 sprints)
