# Especificações Técnicas - Doc2MD API

> **Documento histórico (out/2025, ainda "Doc2MD").** Não reflete o sistema atual: descreve `/convert` com corpo JSON (hoje é `multipart/form-data`), endpoints sem autenticação (hoje todos exigem JWT ou API key), progresso 20→80→100 e uma arquitetura só com Redis (faltam MySQL, MinIO e Elasticsearch). Referência atual: [README.md](README.md) e [features/](features/). Mantido apenas como registro.

## 1. Visão Geral da Arquitetura

### 1.1 Componentes do Sistema

```
┌──────────────────────────────────────────────────────────────┐
│                         CLIENTE                              │
│  (HTTP/REST - curl, Postman, Frontend App, etc.)            │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    API GATEWAY (FastAPI)                     │
│  - Validação de entrada                                      │
│  - Autenticação/Autorização                                  │
│  - Rate limiting                                             │
│  - Geração de job_id (UUID)                                  │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                   MESSAGE BROKER (Redis)                     │
│  - Fila de tarefas (Celery Queue)                           │
│  - Cache de resultados (TTL configurável)                    │
│  - Armazenamento temporário de status                        │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                  WORKERS POOL (Celery)                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │  Worker 1  │  │  Worker 2  │  │  Worker N  │            │
│  └────────────┘  └────────────┘  └────────────┘            │
│                                                              │
│  Cada worker:                                                │
│  1. Pega job da fila                                         │
│  2. Baixa documento (source handler)                         │
│  3. Converte com Docling                                     │
│  4. Armazena resultado no Redis                              │
│  5. Executa callback (se configurado)                        │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 Fluxo de Dados Detalhado

#### Cenário 1: Upload Direto de Arquivo
```
1. Cliente → POST /convert (multipart/form-data)
2. API valida tamanho, tipo MIME
3. Arquivo salvo temporariamente em /tmp/doc2md/uploads/{job_id}/
4. Job criado e enfileirado no Redis
5. API retorna job_id imediatamente
6. Worker pega job da fila
7. Worker processa arquivo com Docling
8. Resultado salvo no Redis com TTL
9. Arquivo temporário deletado
10. Cliente consulta GET /jobs/{job_id}/result
```

#### Cenário 2: Conversão de URL
```
1. Cliente → POST /convert (JSON com URL)
2. API valida URL (formato, domínio permitido)
3. Job criado e enfileirado
4. API retorna job_id
5. Worker faz download do arquivo (com timeout)
6. Worker processa com Docling
7. Resultado salvo no Redis
8. Arquivo temporário deletado
```

#### Cenário 3: Google Drive
```
1. Cliente → POST /convert (JSON com file_id + Bearer token)
2. API valida token com Google OAuth
3. Job criado e enfileirado
4. Worker usa Google Drive API para baixar
5. Worker processa com Docling
6. Resultado salvo no Redis
7. Arquivo temporário deletado
```

#### Cenário 4: Dropbox
```
1. Cliente → POST /convert (JSON com path + Bearer token)
2. API valida token com Dropbox API
3. Job criado e enfileirado
4. Worker usa Dropbox API para baixar
5. Worker processa com Docling
6. Resultado salvo no Redis
7. Arquivo temporário deletado
```

## 2. Schemas de Dados (Pydantic)

### 2.1 Request Schema

```python
class ConversionOptions(BaseModel):
    format: str = "markdown"
    include_images: bool = True
    preserve_tables: bool = True
    extract_metadata: bool = True
    chunk_size: Optional[int] = None  # Para documentos grandes

class ConvertRequest(BaseModel):
    source_type: Literal["file", "url", "gdrive", "dropbox"]
    source: Optional[str] = None  # URL, file_id ou path
    options: ConversionOptions = ConversionOptions()
    callback_url: Optional[HttpUrl] = None

    @validator('source')
    def validate_source(cls, v, values):
        if values.get('source_type') != 'file' and not v:
            raise ValueError('source é obrigatório para este source_type')
        return v
```

### 2.2 Response Schemas

```python
class JobCreatedResponse(BaseModel):
    job_id: UUID
    status: Literal["queued"]
    created_at: datetime
    message: str

class JobStatusResponse(BaseModel):
    job_id: UUID
    status: Literal["queued", "processing", "completed", "failed"]
    progress: int  # 0-100
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error: Optional[str]

class DocumentMetadata(BaseModel):
    pages: Optional[int]
    words: Optional[int]
    format: str
    size_bytes: int
    title: Optional[str]
    author: Optional[str]

class ConversionResult(BaseModel):
    markdown: str
    metadata: DocumentMetadata

class JobResultResponse(BaseModel):
    job_id: UUID
    status: Literal["completed"]
    result: ConversionResult
    completed_at: datetime
```

## 3. Source Handlers

### 3.1 Interface Base

```python
class SourceHandler(ABC):
    @abstractmethod
    async def download(self, source: str, temp_path: Path, **kwargs) -> Path:
        """Baixa arquivo e retorna caminho local"""
        pass

    @abstractmethod
    def validate(self, source: str, **kwargs) -> bool:
        """Valida se a source é acessível"""
        pass
```

### 3.2 Implementações

#### FileHandler
- Já recebe arquivo em memória (UploadFile)
- Salva diretamente em temp_path
- Validação: tamanho, tipo MIME

#### URLHandler
- Usa `httpx.AsyncClient` para download
- Timeout configurável (30s default)
- Validação: formato URL, domínios permitidos
- Suporte a redirecionamentos (max 5)
- Verifica Content-Length antes do download

#### GoogleDriveHandler
- Usa `google-auth` + `google-api-python-client`
- Autenticação via Bearer token (OAuth2)
- API: `drive.files().get_media(fileId=...)`
- Validação: token válido, arquivo acessível

#### DropboxHandler
- Usa SDK oficial `dropbox`
- Autenticação via Bearer token
- API: `files_download(path)`
- Validação: token válido, arquivo existe

## 4. Conversão com Docling

### 4.1 Configuração do Docling

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter(
    format_options={
        "pdf": {
            "ocr_enabled": True,
            "extract_images": True,
        },
        "docx": {
            "extract_images": True,
        }
    }
)
```

### 4.2 Processo de Conversão

```python
async def convert_to_markdown(file_path: Path, options: ConversionOptions) -> ConversionResult:
    # 1. Detectar formato
    format_type = detect_format(file_path)

    # 2. Converter com Docling
    result = converter.convert(str(file_path))

    # 3. Extrair markdown
    markdown_content = result.document.export_to_markdown()

    # 4. Extrair metadata
    metadata = DocumentMetadata(
        pages=result.document.page_count,
        words=count_words(markdown_content),
        format=format_type,
        size_bytes=file_path.stat().st_size,
        title=result.document.metadata.get('title'),
        author=result.document.metadata.get('author'),
    )

    return ConversionResult(
        markdown=markdown_content,
        metadata=metadata
    )
```

## 5. Celery Tasks

### 5.1 Task Principal

```python
@celery_app.task(bind=True, max_retries=3)
def process_conversion(
    self,
    job_id: str,
    source_type: str,
    source: str,
    options: dict,
    callback_url: Optional[str] = None,
    auth_token: Optional[str] = None
):
    try:
        # Update status: processing
        update_job_status(job_id, "processing", progress=0)

        # 1. Download (20% progress)
        handler = get_source_handler(source_type)
        file_path = handler.download(source, auth_token=auth_token)
        update_job_status(job_id, "processing", progress=20)

        # 2. Convert (80% progress)
        result = convert_to_markdown(file_path, options)
        update_job_status(job_id, "processing", progress=80)

        # 3. Store result
        store_result(job_id, result)
        update_job_status(job_id, "completed", progress=100)

        # 4. Cleanup
        cleanup_temp_files(job_id)

        # 5. Callback (if configured)
        if callback_url:
            send_callback(callback_url, job_id, result)

    except Exception as exc:
        update_job_status(job_id, "failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)
```

## 6. Storage (Redis)

### 6.1 Estrutura de Chaves

```
# Job status
job:{job_id}:status = {
    "status": "processing",
    "progress": 50,
    "created_at": "...",
    "started_at": "...",
    "error": null
}

# Job result (TTL: 1 hora)
job:{job_id}:result = {
    "markdown": "...",
    "metadata": {...}
}

# Active jobs set
jobs:active = {job_id1, job_id2, ...}
```

### 6.2 TTL Configuration

- Status: 24 horas
- Result: 1 hora (configurável)
- Após TTL, resultado não disponível (cliente deve processar novamente)

## 7. API Endpoints Detalhados

### 7.1 POST /convert

**Headers:**
- `Content-Type: multipart/form-data` (para upload)
- `Content-Type: application/json` (para url/gdrive/dropbox)
- `Authorization: Bearer {token}` (opcional, para gdrive/dropbox)

**Rate Limit:** 10 requests/minuto por IP

**Validações:**
- Tamanho máximo: 50MB
- Formatos permitidos: pdf, docx, doc, html, pptx, xlsx, rtf, odt
- URL: apenas HTTPS (exceto localhost em dev)
- Google Drive: token válido e file_id acessível
- Dropbox: token válido e path existe

### 7.2 GET /jobs/{job_id}

**Headers:** Nenhum obrigatório

**Cache:** 5 segundos (para evitar consultas excessivas)

### 7.3 GET /jobs/{job_id}/result

**Headers:** Nenhum obrigatório

**Erros:**
- 404: Job não encontrado ou expirado
- 400: Job ainda em processamento
- 500: Job falhou

## 8. Docker Configuration

### 8.1 Dockerfile.api

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY api/ ./api/
COPY shared/ ./shared/

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 8.2 Dockerfile.worker

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for Docling
RUN apt-get update && apt-get install -y \
    libpoppler-cpp-dev \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY workers/ ./workers/
COPY shared/ ./shared/

# Run Celery worker
CMD ["celery", "-A", "workers.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
```

### 8.3 docker-compose.yml

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    ports:
      - "8000:8080"
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - redis
    volumes:
      - ./tmp:/tmp/doc2md

  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - redis
    volumes:
      - ./tmp:/tmp/doc2md
    deploy:
      replicas: 3

volumes:
  redis_data:
```

## 9. Monitoring & Logging

### 9.1 Logs Estruturados

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "conversion_started",
    job_id=job_id,
    source_type=source_type,
    file_size=file_size
)
```

### 9.2 Métricas (Prometheus-compatible)

- `conversions_total{source_type, status}` - Counter
- `conversion_duration_seconds{source_type}` - Histogram
- `active_jobs` - Gauge
- `queue_size` - Gauge

### 9.3 Health Checks

```python
@app.get("/health")
async def health_check():
    # Check Redis connection
    redis_ok = await ping_redis()

    # Check Celery workers
    workers = celery_app.control.inspect().active()
    worker_count = len(workers) if workers else 0

    return {
        "status": "healthy" if redis_ok and worker_count > 0 else "degraded",
        "redis": redis_ok,
        "workers": {
            "active": worker_count,
            "available": worker_count
        }
    }
```

## 10. Segurança

### 10.1 Validação de Input

- Sanitização de filenames
- Validação de MIME types
- Limite de tamanho de arquivo
- Validação de URLs (whitelist de domínios em produção)

### 10.2 Autenticação

- Bearer tokens para Google Drive e Dropbox
- Tokens nunca logados ou armazenados
- Validação de tokens antes de enfileirar job

### 10.3 Rate Limiting

- 10 requests/minuto por IP (configurable)
- 100 jobs ativos por usuário (se autenticado)

### 10.4 Isolamento

- Workers executam em containers separados
- Arquivos temporários isolados por job_id
- Cleanup automático após processamento

## 11. Error Handling

### 11.1 Códigos de Erro HTTP

- `400` - Bad Request (validação falhou)
- `401` - Unauthorized (token inválido)
- `404` - Not Found (job não existe)
- `413` - Payload Too Large (arquivo muito grande)
- `422` - Unprocessable Entity (formato não suportado)
- `429` - Too Many Requests (rate limit)
- `500` - Internal Server Error
- `503` - Service Unavailable (workers offline)

### 11.2 Job Errors

```python
class JobError(BaseModel):
    code: str
    message: str
    details: Optional[dict]

# Exemplos:
# - DOWNLOAD_FAILED
# - CONVERSION_FAILED
# - TIMEOUT
# - INVALID_FORMAT
# - AUTHENTICATION_FAILED
```

## 12. Performance Optimization

### 12.1 Caching

- Resultados cacheados por 1 hora
- Status cacheados por 5 segundos
- ETags para resultados não modificados

### 12.2 Async Processing

- API totalmente assíncrona (FastAPI)
- Downloads assíncronos (httpx)
- Conexões pool para Redis

### 12.3 Worker Optimization

- Concurrency: 2 por worker (CPU-bound)
- Prefetch: 1 (para evitar timeout)
- Task timeout: 5 minutos
- Retry: 3x com backoff exponencial

## 13. Cleanup & Maintenance

### 13.1 Automatic Cleanup

```python
# Celery beat task (runs hourly)
@celery_app.task
def cleanup_expired_jobs():
    # Remove arquivos temporários > 24h
    # Remove jobs expirados do Redis
    # Log estatísticas
```

### 13.2 Manual Cleanup

```bash
# Script de manutenção
docker-compose exec api python -m scripts.cleanup --older-than 24h
```
